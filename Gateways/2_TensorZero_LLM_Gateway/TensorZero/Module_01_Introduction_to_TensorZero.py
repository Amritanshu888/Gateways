#!/usr/bin/env python
# coding: utf-8

# # 🚀 Module 1 — Introduction to TensorZero Gateways
# 
# ---
# 
# **Course:** TensorZero LLM Gateways — Basic to Advanced  
# **Module:** 1 
# ---

# ---
# # 📚 Part 1 — Theory: What is an LLM Gateway?
# 
# ---

# ![image.png](attachment:image.png)

# ![image.png](attachment:image.png)

# ![image.png](attachment:image.png)

# ---
# # 🐳 Part 2 — Spinning Up TensorZero with Docker Compose
# 
# ---

# ## 2.1 — Prerequisites
# 
# Before running any code in this section, make sure you have:
# 
# | Requirement | How to check | Install |
# |-------------|-------------|---------|  
# | Docker Desktop | `docker --version` | https://www.docker.com/products/docker-desktop |
# | Docker Compose | `docker compose version` | Included with Docker Desktop |
# | Python 3.9+ | `python --version` | https://www.python.org |
# | OpenAI API Key | — | https://platform.openai.com |
# | Groq API Key | — | https://console.groq.com |
# 
# ⚠️ **Make sure Docker Desktop is running before proceeding!**

# In[1]:


# ─────────────────────────────────────────────────────────────────
# CELL 1: Prerequisites Check
# Run this to verify Docker and Python are set up correctly
# ─────────────────────────────────────────────────────────────────
import subprocess
import sys

def check_tool(name, cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        version = result.stdout.strip() or result.stderr.strip()
        print(f"✅ {name}: {version.splitlines()[0]}")
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print(f"❌ {name}: NOT FOUND — please install it before continuing")
        return False

print("=" * 50)
print("    Prerequisites Check")
print("=" * 50)

check_tool("Python",         [sys.executable, "--version"])
check_tool("Docker",         ["docker", "--version"])
check_tool("Docker Compose", ["docker", "compose", "version"])

print("=" * 50)
print("\nIf everything shows ✅ you're ready to go!")


# ## 2.2 — Project Directory Structure
# 
# We'll create this folder layout for our TensorZero project:
# 
# ```
# tensorzero-demo/
# ├── docker-compose.yml     ← defines the services to run
# ├── .env                   ← stores API keys (never commit this!)
# └── config/
#     └── tensorzero.toml    ← TensorZero configuration (functions & variants)
# ```
# 
# The `config/` folder is **mounted into the gateway container** at `/app/config/`.  
# This means you can edit `tensorzero.toml` and restart the gateway — no rebuilding Docker images.

# In[2]:


# ─────────────────────────────────────────────────────────────────
# CELL 2: Create Project Directory Structure
# ─────────────────────────────────────────────────────────────────
import os
from pathlib import Path

# Create the project folder and config subfolder
project_dir = Path("tensorzero-demo")
config_dir  = project_dir / "config"

config_dir.mkdir(parents=True, exist_ok=True)

print("📁 Project structure created:")
print(f"   {project_dir}/")
print(f"   └── config/")
print()
print(f"   Absolute path: {project_dir.resolve()}")


# ## 2.3 — Writing `docker-compose.yml`
# 
# ### What is Docker Compose?
# 
# Docker Compose lets you define **multiple containers** that work together as a single application stack using one YAML file.
# 
# ### Our TensorZero Stack Has 4 Services:
# 
# ```
# ┌──────────────────────────────────────────────────────────┐
# │ Service 1: postgres                                      │
# │   Image: tensorzero/postgres:17                          │
# │   Port:  5432                                            │
# │   Role:  Stores inference logs, feedback, metrics        │
# │          (Uses PostgreSQL + pg_cron extension)           │
# ├──────────────────────────────────────────────────────────┤
# │ Service 2: gateway-run-postgres-migrations               │
# │   Image: tensorzero/gateway                              │
# │   Role:  One-time job — creates DB tables/schema         │
# │          Runs BEFORE the gateway starts                  │
# ├──────────────────────────────────────────────────────────┤
# │ Service 3: gateway  ← THE MAIN SERVICE                  │
# │   Image: tensorzero/gateway                              │
# │   Port:  3000                                            │
# │   Role:  The LLM proxy — receives your API calls,        │
# │          routes to OpenAI/Groq, logs to Postgres         │
# ├──────────────────────────────────────────────────────────┤
# │ Service 4: ui (optional but useful)                      │
# │   Image: tensorzero/ui                                   │
# │   Port:  4000                                            │
# │   Role:  Web dashboard — see all inferences visually     │
# └──────────────────────────────────────────────────────────┘
# ```
# 
# ### Startup Order (managed by `depends_on`):
# ```
# postgres (healthy) → migrations (completed) → gateway (healthy) → ui
# ```
# Docker Compose ensures services start in the right order automatically.

# In[3]:


# ─────────────────────────────────────────────────────────────────
# CELL 3: Write docker-compose.yml
# ─────────────────────────────────────────────────────────────────

docker_compose_content = """\
# TensorZero Docker Compose -- Module 1
# Services: gateway, ui, postgres, migrations

services:

  # 1. PostgreSQL Database
  # TensorZero uses a custom postgres image that includes
  # the pg_cron extension for background data maintenance tasks.
  postgres:
    image: tensorzero/postgres:17
    command: ["postgres", "-c", "cron.database_name=tensorzero"]
    environment:
      POSTGRES_DB:       tensorzero
      POSTGRES_USER:     postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d tensorzero"]
      start_period:    30s
      start_interval:  1s
      timeout:         1s

  # 2. Database Migrations
  # One-shot service: runs, creates DB schema, then exits.
  # The gateway will NOT start until this completes successfully.
  gateway-run-postgres-migrations:
    image: tensorzero/gateway
    environment:
      TENSORZERO_POSTGRES_URL: postgres://postgres:postgres@postgres:5432/tensorzero
    command: ["--run-postgres-migrations"]
    depends_on:
      postgres:
        condition: service_healthy

  # 3. TensorZero Gateway (THE MAIN SERVICE)
  # The LLM proxy your Python code will talk to on port 3000.
  # Reads tensorzero.toml for function/variant config.
  gateway:
    image: tensorzero/gateway
    volumes:
      - ./config:/app/config:ro
    command: --config-file /app/config/tensorzero.toml
    environment:
      TENSORZERO_POSTGRES_URL: postgres://postgres:postgres@postgres:5432/tensorzero
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      GROQ_API_KEY:   ${GROQ_API_KEY}
    ports:
      - "3000:3000"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    healthcheck:
      test:
        ["CMD", "wget", "--no-verbose", "--tries=1",
         "--spider", "http://localhost:3000/health"]
      start_period:   10s
      start_interval:  1s
      timeout:         1s
    depends_on:
      postgres:
        condition: service_healthy
      gateway-run-postgres-migrations:
        condition: service_completed_successfully

  # 4. TensorZero UI (Dashboard)
  # Visit http://localhost:4000 to see all your inferences visually.
  ui:
    image: tensorzero/ui
    environment:
      TENSORZERO_GATEWAY_URL: http://gateway:3000
    ports:
      - "4000:4000"
    depends_on:
      gateway:
        condition: service_healthy

volumes:
  postgres-data:
"""

compose_file = project_dir / "docker-compose.yml"
compose_file.write_text(docker_compose_content, encoding="utf-8")

print(f"Written: {compose_file.resolve()}")
print(f"   File size: {compose_file.stat().st_size} bytes")


# ## 2.4 — Writing `tensorzero.toml` — Functions & Variants
# 
# ### What is TOML?
# 
# TOML (Tom's Obvious Minimal Language) is a configuration file format — similar to `.ini` files but more structured. TensorZero uses it for all configuration.
# 
# ```toml
# # This is a TOML comment
# [section]         # square brackets = section header
# key = "value"     # key-value pairs
# number = 42
# flag = true
# 
# [section.subsection]   # nested sections use dots
# another_key = "hello"
# ```
# 
# ### The `tensorzero.toml` Structure:
# 
# ```
# tensorzero.toml
# │
# ├── [gateway]                    ← optional global settings
# │
# ├── [models.model_name]          ← define model + provider details
# │   └── [models.model_name.providers.provider_name]
# │
# └── [functions.function_name]    ← define a task
#     └── [functions.function_name.variants.variant_name]  ← implementation
# ```
# 
# ### Model Shorthand Syntax
# 
# TensorZero supports a shorthand for well-known providers — no explicit `[models.*]` section needed:
# 
# ```toml
# model = "openai::gpt-4o-mini"   # shorthand for OpenAI
# model = "groq::llama-3.1-8b-instant"  # shorthand for Groq
# ```
# 
# Just set the `OPENAI_API_KEY` / `GROQ_API_KEY` environment variables and it works automatically.
# 
# ### The `weight` Field for A/B Testing:
# 
# ```toml
# weight = 1   # 100% traffic (default if omitted in a single-variant setup)
# weight = 0   # disabled — no traffic sent to this variant
# weight = 0.2 # 20% of traffic goes here (the rest goes to other variants)
# ```
# 
# We'll set `groq_variant` to `weight = 0` now to disable it.  
# In later modules we'll enable both and run real A/B experiments.

# In[4]:


# ─────────────────────────────────────────────────────────────────
# CELL 4: Write tensorzero.toml -- Your First TensorZero Config
#
# IMPORTANT: system_template must be a PATH to a .minijinja file,
# not an inline string. The next cell creates those template files.
# ─────────────────────────────────────────────────────────────────

tensorzero_toml = """\

# ── FUNCTION: summarize ──────────────────────────────────────────

[functions.summarize]
type = "chat"

# Variant 1: OpenAI gpt-4o-mini
[functions.summarize.variants.gpt_variant]
type            = "chat_completion"
model           = "openai::gpt-4o-mini"
system_template = "summarize_system.minijinja"
weight          = 1

# Variant 2: Groq Llama-3.1-8B 
[functions.summarize.variants.groq_variant]
type            = "chat_completion"
model           = "groq::llama-3.1-8b-instant"
system_template = "summarize_system.minijinja"
weight          = 0


# ── FUNCTION: chat ───────────────────────────────────────────────
# General-purpose chat function -- no system template (open-ended).

[functions.chat]
type = "chat"

[functions.chat.variants.gpt_mini]
type   = "chat_completion"
model  = "openai::gpt-4o-mini"
weight = 1

[functions.chat.variants.groq_llama]
type   = "chat_completion"
model  = "groq::llama-3.3-70b-versatile"
weight = 0
"""

toml_file = config_dir / "tensorzero.toml"
toml_file.write_text(tensorzero_toml, encoding="utf-8")

print(f"Written: {toml_file.resolve()}")
print()
print("Functions defined:")
print("  - summarize  -> gpt_variant (active), groq_variant (disabled)")
print("  - chat       -> gpt_mini (active), groq_llama (disabled)")


# In[5]:


# ─────────────────────────────────────────────────────────────────
# CELL 4b: Create Minijinja Prompt Template Files
#
# TensorZero uses Minijinja (.minijinja) files for prompt templates.
# system_template in tensorzero.toml is a PATH to one of these files,
# not an inline string. The gateway resolves the path relative to the
# config/ directory (i.e. the same folder as tensorzero.toml).
#
# Minijinja is a templating language -- in later modules we'll use
# variables like {{ user_name }} inside these templates. For now we
# just write a plain static system prompt.
# ─────────────────────────────────────────────────────────────────

# Template used by both gpt_variant and groq_variant of "summarize"
summarize_system = (
    "You are an expert summarizer. "
    "Summarize the given text in 2-3 concise sentences. "
    "Preserve key facts and maintain a neutral tone."
)

template_file = config_dir / "summarize_system.minijinja"
template_file.write_text(summarize_system, encoding="utf-8")

print(f"Written: {template_file.resolve()}")
print()
print("Config directory now contains:")
for f in sorted(config_dir.iterdir()):
    print(f"  {f.name}")


# ## 2.5 — Creating the `.env` File
# 
# Docker Compose automatically reads a `.env` file in the same directory and substitutes `${VARIABLE}` references in `docker-compose.yml`.
# 
# **Security note:** The `.env` file contains your secret API keys.  
# - ✅ Add `.env` to your `.gitignore` — never commit it to git
# - ✅ Use environment variables in CI/CD instead of `.env` files
# - ❌ Never hardcode API keys directly in source files

# ## Create the `.env` File Manually
# 
# 1. In the VS Code Explorer panel, navigate to the `tensorzero-demo/` folder.
# 2. Right-click the folder and select **New File**.
# 3. Name the file `.env`.
# 4. Paste the following content into the file and replace the placeholder values with your actual API keys:
# 
# ```env
# OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
# GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx
# ```
# 
# 5. Save the file.
# 
# That's it! Your `.env` file is now configured.

# In[8]:


# ─────────────────────────────────────────────────────────────────
# CELL 6: Verify Project Structure Before Starting
# ─────────────────────────────────────────────────────────────────

print("📁 Project structure:")
print()

for path in sorted(project_dir.rglob("*")):
    indent  = "    " * (len(path.relative_to(project_dir).parts) - 1)
    prefix  = "└── " if path.is_file() else "├── "
    size    = f"  ({path.stat().st_size} bytes)" if path.is_file() else "/"
    print(f"   {indent}{prefix}{path.name}{size}")

print()
print("All files present ✅ — ready to start Docker Compose!")


# ## 2.6 — Starting the Stack
# 
# ### Key Docker Compose Commands
# 
# | Command | What it does |
# |---------|-------------|
# | `docker compose up -d` | Start all services in the background |
# | `docker compose down` | Stop and remove containers |
# | `docker compose ps` | Show running services |
# | `docker compose logs -f gateway` | Stream gateway logs |
# | `docker compose restart gateway` | Restart just the gateway (useful after config changes) |
# 
# ### The `-d` Flag
# The `-d` flag means **detached mode** — services run in the background, and you get your terminal back.  
# Without `-d`, logs stream to your terminal and Ctrl+C stops everything.
# 
# ### What Happens During `docker compose up`:
# ```
# 1. Docker pulls images (first time only — may take a few minutes)
# 2. postgres container starts → runs health check
# 3. migrations container starts → creates DB tables → exits
# 4. gateway container starts → reads tensorzero.toml → listens on :3000
# 5. ui container starts → connects to gateway → listens on :4000
# ```
# 
# ⚠️ **Important:** The first run downloads Docker images (~500MB total). Subsequent starts are instant.

# In[9]:


# ─────────────────────────────────────────────────────────────────
# CELL 7: Start TensorZero with Docker Compose
# ─────────────────────────────────────────────────────────────────
import subprocess
import time

print("🚀 Starting TensorZero stack...")
print("   (First run may take a few minutes to download Docker images)")
print()

result = subprocess.run(
    ["docker", "compose", "up", "-d", "--wait"],
    cwd=str(project_dir.resolve()),
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print("✅ Stack started successfully!")
    print()
    print(result.stdout)
else:
    print("❌ Failed to start stack:")
    print(result.stderr)
    print()


# In[10]:


# ─────────────────────────────────────────────────────────────────
# CELL 8: Check Running Services
# ─────────────────────────────────────────────────────────────────

result = subprocess.run(
    ["docker", "compose", "ps"],
    cwd=str(project_dir.resolve()),
    capture_output=True,
    text=True
)

print("Docker Compose Services:")
print("=" * 70)
print(result.stdout)



# ## 2.7 — Verifying the Health Endpoint
# 
# ### What is a Health Endpoint?
# 
# A health endpoint is a simple HTTP route (`GET /health`) that returns whether the service is ready to accept requests.  
# It's a standard pattern in production systems for:
# - **Load balancers** — only send traffic to healthy instances
# - **Docker Compose** — `depends_on: condition: service_healthy` waits for it
# - **Kubernetes** — liveness and readiness probes
# - **Monitoring** — uptime alerts
# 
# ### TensorZero's Health Endpoint:
# ```
# GET http://localhost:3000/health
# → 200 OK  (gateway is running and ready)
# → 503     (gateway is still starting up)
# ```
# 
# We also have the UI at `http://localhost:4000` once the gateway is healthy.

# In[11]:


# ─────────────────────────────────────────────────────────────────
# CELL 9: Health Check — Verify Gateway is Running
# ─────────────────────────────────────────────────────────────────
import urllib.request
import json
import time

GATEWAY_URL = "http://localhost:3000"

def check_health(url, retries=10, delay=3):
    """Poll the health endpoint until the service is ready."""
    for attempt in range(1, retries + 1):
        try:
            response = urllib.request.urlopen(f"{url}/health", timeout=5)
            body = json.loads(response.read().decode())
            return True, response.status, body
        except Exception as e:
            print(f"  Attempt {attempt}/{retries} — not ready yet ({type(e).__name__}), waiting {delay}s...")
            time.sleep(delay)
    return False, None, None

print(f"🔍 Checking TensorZero gateway health at {GATEWAY_URL}/health")
print()

success, status_code, body = check_health(GATEWAY_URL)

if success:
    print(f"✅ Gateway is HEALTHY!")
    print(f"   HTTP Status: {status_code}")
    print(f"   Response:    {body}")
    print()
    print(f"🌐 Gateway API:   {GATEWAY_URL}")
    print(f"📊 UI Dashboard:  http://localhost:4000")
else:
    print("❌ Gateway did not respond. Check docker compose logs.")
    print("   Run: docker compose -f tensorzero-demo/docker-compose.yml logs gateway")


# ---
# # 🐍 Part 3 — Making API Calls via the OpenAI SDK
# 
# ---

# ## 3.1 — OpenAI SDK Compatibility
# 
# ### The Key Insight
# 
# TensorZero implements the **OpenAI API protocol** — which means any code that works with the OpenAI SDK can talk to TensorZero with **only 2 changes**:
# 
# ```python
# # ── BEFORE (talking directly to OpenAI) ─────────────────────────
# from openai import OpenAI
# 
# client = OpenAI(
#     api_key="sk-your-real-key"
#     # base_url defaults to https://api.openai.com/v1
# )
# 
# response = client.chat.completions.create(
#     model="gpt-4o-mini",    # ← model name
#     messages=[...]
# )
# 
# # ── AFTER (talking to TensorZero) ────────────────────────────────
# from openai import OpenAI
# 
# client = OpenAI(
#     api_key="not-used",                              # ← change 1: dummy key
#     base_url="http://localhost:3000/openai/v1"       # ← change 2: point to gateway
# )
# 
# response = client.chat.completions.create(
#     model="tensorzero::function_name::summarize",    # ← change 3: function reference
#     messages=[...]
# )
# ```
# 
# ### The Model String Format
# 
# When using TensorZero via the OpenAI SDK, the `model` parameter is special:
# 
# ```
# tensorzero::function_name::<your_function_name>
# │           │              │
# │           │              └── name you defined in tensorzero.toml
# │           └── literal keyword (always "function_name")
# └── tells TensorZero this is a function call, not a direct model call
# ```
# 
# Example for our `summarize` function:
# ```python
# model = "tensorzero::function_name::summarize"
# ```
# 
# ### Why Does This Work?
# 
# TensorZero's gateway listens on `/openai/v1/chat/completions` — the same path as OpenAI's API.  
# When the model string starts with `tensorzero::`, it knows to route via the function/variant system.  
# Otherwise it can also accept plain model names for simple passthrough.

# In[12]:


# ─────────────────────────────────────────────────────────────────
# CELL 10: Install Python Dependencies
# ─────────────────────────────────────────────────────────────────
import subprocess
import sys

packages = ["openai", "tensorzero", "requests"]

print("📦 Installing packages...")
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q"] + packages,
    capture_output=True, text=True
)

if result.returncode == 0:
    for pkg in packages:
        print(f"  ✅ {pkg}")
else:
    print(result.stderr)

print()
print("All packages ready!")


# In[13]:


import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "python-dotenv"], capture_output=True)
print("Done")


# In[14]:


# ─────────────────────────────────────────────────────────────────
# CELL 11: Direct OpenAI API Call (for comparison)
# We'll compare this response with the TensorZero response next.
# ─────────────────────────────────────────────────────────────────
import os
from openai import OpenAI
from pathlib import Path
from dotenv import load_dotenv  # pip install python-dotenv

# Load API key from .env file
load_dotenv(project_dir / ".env")

# ── Direct OpenAI client ─────────────────────────────────────────
openai_direct = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"]  # real key, real endpoint
)

TEXT_TO_SUMMARIZE = """
Artificial intelligence has experienced remarkable growth over the past decade,
fundamentally changing how software systems are built and deployed. Large Language
Models (LLMs) like GPT-4 and Llama have demonstrated capabilities ranging from
writing code to complex reasoning. However, managing these models in production
presents new challenges: teams need to monitor performance, control costs, run
experiments, and continuously improve their AI features. LLM gateways have emerged
as a solution, acting as an intelligent middleware layer between applications and
the underlying model providers.
"""

print("📤 Sending request DIRECTLY to OpenAI...")
print()

direct_response = openai_direct.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "system",
            "content": "You are an expert summarizer. Summarize the given text in 2-3 concise sentences."
        },
        {
            "role": "user",
            "content": TEXT_TO_SUMMARIZE
        }
    ]
)

print("📥 Direct OpenAI Response Fields:")
print(f"   id:            {direct_response.id}")
print(f"   model:         {direct_response.model}")
print(f"   created:       {direct_response.created}")
print(f"   usage.tokens:  prompt={direct_response.usage.prompt_tokens}, "
      f"completion={direct_response.usage.completion_tokens}")
print()
print("📝 Summary:")
print(direct_response.choices[0].message.content)


# In[15]:


# ─────────────────────────────────────────────────────────────────
# CELL 12: Same Call Through TensorZero Gateway
# Only 2 changes from the direct OpenAI call:
#   1. base_url points to localhost:3000
#   2. model string uses tensorzero::function_name::summarize
# ─────────────────────────────────────────────────────────────────
from openai import OpenAI

# ── TensorZero-compatible OpenAI client ──────────────────────────
openai_via_tz = OpenAI(
    api_key="not-used",                        # TensorZero handles auth with providers
    base_url="http://localhost:3000/openai/v1" # ← point to TensorZero gateway
)

print("📤 Sending request through TensorZero gateway...")
print()

tz_response = openai_via_tz.chat.completions.create(
    model="tensorzero::function_name::summarize",  # ← function defined in tensorzero.toml
    messages=[
        {
            "role": "user",                  # Note: system prompt comes from tensorzero.toml!
            "content": TEXT_TO_SUMMARIZE     # We only send the user message
        }
    ]
)

print("📥 TensorZero Response Fields:")
print(f"   id:            {tz_response.id}")
print(f"   model:         {tz_response.model}")
print(f"   created:       {tz_response.created}")
print(f"   usage.tokens:  prompt={tz_response.usage.prompt_tokens}, "
      f"completion={tz_response.usage.completion_tokens}")

# The episode_id is a TensorZero extension — check the raw response object
# It may appear in response headers or as a custom field
if hasattr(tz_response, 'episode_id'):
    print(f"   episode_id:    {tz_response.episode_id}  ← UNIQUE TO TENSORZERO")

print()
print("📝 Summary:")
print(tz_response.choices[0].message.content)


# ## Key Differences Between Direct OpenAI and TensorZero
# 
# ### `id` Field
# 
# - **Direct OpenAI:** `chatcmpl-DnM6S16L...`
#   - OpenAI's own request ID.
#   - Generally not useful for application-level tracking.
# 
# - **TensorZero:** `019e9755-a05d...`
#   - A UUID generated by TensorZero.
#   - Can be used to look up this inference in your database.
# 
# ### `model` Field
# 
# - **Direct OpenAI:** `gpt-4o-mini-2024-07-18`
#   - Only contains the model name.
# 
# - **TensorZero:** `tensorzero::function_name::summarize::variant_name::gpt_variant`
#   - Shows exactly which **function** handled the request.
#   - Shows which **variant** was selected.
#   - Provides full routing visibility.
# 
# ### `episode_id` Field
# 
# - **Direct OpenAI:** ❌ Not available.
# 
# - **TensorZero:** `019e9755-a05e...`
#   - ✅ Present.
#   - Links the inference to a conversation/session.
#   - Useful for tracking multi-turn interactions.
# 
# ### Token Usage Difference
# 
# - **Direct OpenAI:** `prompt_tokens = 142`
# - **TensorZero:** `prompt_tokens = 151`
# 
# TensorZero used **9 additional tokens** because it automatically injected the `summarize_system.minijinja` system prompt defined in your configuration.
# 
# Your application code sent **no system message**, but TensorZero added one behind the scenes.
# 
# ### What Did *Not* Change
# 
# - The generated summary quality remains the same.
# - You still access the response with:
# 
# ```python
# response.choices[0].message.content
# ```
# 
# - You still use the OpenAI SDK.
# - The only code change is switching the `base_url`.
# 
# ### The Invisible but Important Difference
# 
# Every TensorZero inference is automatically logged to your PostgreSQL database.
# 
# Open:
# 
# ```text
# http://localhost:4000
# ```
# 
# and you'll see the inference recorded in the TensorZero UI.

# ## 3.2 — Comparing Direct vs. Gateway Responses
# 
# Both calls return the same **OpenAI response structure** — same field names, same `.choices[0].message.content` access pattern.  
# The key differences:
# 
# | Field | Direct OpenAI | Via TensorZero |
# |-------|--------------|----------------|
# | `id` | `chatcmpl-abc123...` | `xyz789...` |
# | `model` | `gpt-4o-mini-2024-07-18` | `gpt-4o-mini` |
# | `episode_id` | ❌ not present | ✅ TensorZero UUID |
# | `inference_id` | ❌ not present | ✅ TensorZero UUID |
# | Logged to DB | ❌ | ✅ stored in Postgres |
# | A/B routing | ❌ | ✅ based on variant weights |
# 
# ### What is `episode_id`?
# 
# ```
# Episode = a single conversation or workflow session
#   └── Inference 1 (first message)
#   └── Inference 2 (second message, same episode_id)
#   └── Inference 3 (third message, same episode_id)
# ```
# 
# - The `episode_id` groups multiple inferences that belong to the **same conversation**
# - It's how TensorZero tracks multi-turn conversations
# - Later you can attach feedback (thumbs up/down, scores) to an episode
# - TensorZero uses episodes to optimize prompts across a full conversation, not just single turns
# 
# You can pass the same `episode_id` in subsequent calls to group them:

# ---
# # 🧩 Part 4 — Using the TensorZero Native Python Client
# 
# ---

# ## 4.1 — Why Use the Native Client?
# 
# The OpenAI SDK works, but it was designed for OpenAI's API — not TensorZero's extended features.  
# The native TensorZero Python client gives you:
# 
# | Feature | OpenAI SDK | Native TensorZero Client |
# |---------|-----------|------------------------|
# | Basic inference | ✅ | ✅ |
# | `inference_id` easily accessible | ⚠️ | ✅ |
# | `episode_id` easily accessible | ⚠️ | ✅ |
# | **Feedback API** (thumbs up/down) | ❌ | ✅ |
# | **Structured outputs** (JSON) | ⚠️ | ✅ |
# | Embedded gateway mode | ❌ | ✅ |
# | Async support | ✅ | ✅ |
# 
# ### Two Modes of the Native Client:
# 
# ```python
# # Mode 1: HTTP — connects to a running gateway (what we'll use)
# TensorZeroGateway.build_http(gateway_url="http://localhost:3000")
# 
# # Mode 2: Embedded — spins up an in-process gateway (no Docker needed!)
# TensorZeroGateway.build_embedded(config_file="./config/tensorzero.toml",
#                                   clickhouse_url="...")
# ```
# 
# For this module we'll use **Mode 1 (HTTP)** since our gateway is already running in Docker.
# 
# ### Sync vs Async Client:
# 
# ```python
# from tensorzero import TensorZeroGateway        # synchronous (simpler)
# from tensorzero import AsyncTensorZeroGateway   # async (for FastAPI, async apps)
# ```

# In[16]:


# ─────────────────────────────────────────────────────────────────
# CELL 14: TensorZero Native Client — Synchronous
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway

# Connect to our running gateway
# The 'with' statement ensures the client is properly closed when done
with TensorZeroGateway.build_http(gateway_url="http://localhost:3000") as client:

    print("📤 Making inference via TensorZero native client...")
    print()

    result = client.inference(
        function_name="summarize",         # function defined in tensorzero.toml
        input={
            "messages": [
                {
                    "role": "user",
                    "content": TEXT_TO_SUMMARIZE
                }
            ]
        }
    )

    print("📥 Native Client Response:")
    print(f"   Type:           {type(result).__name__}")
    print(f"   inference_id:   {result.inference_id}  ← direct attribute access!")
    print(f"   episode_id:     {result.episode_id}")
    print(f"   variant_name:   {result.variant_name}  ← which variant was used")
    print()

    # Access the content — no .choices[0].message needed!
    summary_text = result.content[0].text
    print("📝 Summary:")
    print(summary_text)

    # Save IDs for feedback demo in later modules
    saved_inference_id = result.inference_id
    saved_episode_id   = result.episode_id


# In[18]:


# ─────────────────────────────────────────────────────────────────
# CELL 15: Native Client — Passing episode_id Explicitly
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway

with TensorZeroGateway.build_http(gateway_url="http://localhost:3000") as client:

    # Turn 1 — no episode_id passed, TensorZero generates a UUID v7
    r1 = client.inference(
        function_name="chat",
        input={
            "messages": [
                {"role": "user", "content": "Name 3 benefits of using an LLM gateway."}
            ]
        }
    )

    episode_id = r1.episode_id   # grab the UUID v7 TensorZero generated
    print(f"Episode ID: {episode_id}")
    print(f"Turn 1 [inference_id={r1.inference_id}]:")
    print(r1.content[0].text[:250], "...")
    print()

    # Turn 2 — pass the same episode_id to group them together
    r2 = client.inference(
        function_name="chat",
        input={
            "messages": [
                {"role": "user",      "content": "Which of these is most important for startups?"}
            ]
        },
        episode_id=episode_id
    )

    print(f"Turn 2 [inference_id={r2.inference_id}]:")
    print(r2.content[0].text[:250], "...")
    print()

    print(f"Both turns share episode_id: {r1.episode_id}")
    assert r1.episode_id == r2.episode_id == episode_id, "Episode IDs should match!"
    print("Assertion passed: episode grouping works correctly")


# In[19]:


# ─────────────────────────────────────────────────────────────────
# CELL 16: TensorZero Native Client — Async Version
# Use this in FastAPI apps, async scripts, or when running
# multiple inferences in parallel.
# ─────────────────────────────────────────────────────────────────
import asyncio
from tensorzero import AsyncTensorZeroGateway

async def run_parallel_inferences():

    async with await AsyncTensorZeroGateway.build_http(
        gateway_url="http://localhost:3000"
    ) as client:

        print("Launching 2 inferences in parallel...")

        task1 = client.inference(
            function_name="summarize",
            input={"messages": [{"role": "user",
                                 "content": "Machine learning is a subset of AI..."}]}
        )
        task2 = client.inference(
            function_name="summarize",
            input={"messages": [{"role": "user",
                                 "content": "Docker containers provide isolated environments..."}]}
        )

        result1, result2 = await asyncio.gather(task1, task2)

        print(f"Result 1 [variant={result1.variant_name}]:")
        print(f"  {result1.content[0].text}")
        print()
        print(f"Result 2 [variant={result2.variant_name}]:")
        print(f"  {result2.content[0].text}")

await run_parallel_inferences()


# ---
# ## Exploring the TensorZero UI
# 
# Now that you've made several inferences, open the dashboard:  
# **http://localhost:4000**
# 
# You should see:
# 
# ```
# TensorZero UI
# ├── Inferences    ← every API call logged with input/output/latency/cost
# ├── Episodes      ← multi-turn conversations grouped by episode_id
# └── Functions     ← your defined functions (summarize, chat)
# ```
# 
# Each inference is stored in PostgreSQL with:
# - Input messages
# - Output text
# - Which variant was used
# - Token counts and estimated cost
# - Latency (time to first token, total time)
# 
# This observability data is the foundation for everything in the advanced modules — feedback collection, A/B testing analysis, and automated optimization.

# In[ ]:


# ─────────────────────────────────────────────────────────────────
# CELL 17: (Optional) Stop Docker Compose
# Run this when you're done with the module.
# Use 'down -v' to also delete the database volume.
# ─────────────────────────────────────────────────────────────────

# Uncomment to stop services (keep data):
# subprocess.run(["docker", "compose", "down"],
#                cwd=str(project_dir.resolve()))

# Uncomment to stop services AND delete all stored data:
# subprocess.run(["docker", "compose", "down", "-v"],
#                cwd=str(project_dir.resolve()))

print("Services still running. To stop them:")
print(f"  cd {project_dir.resolve()}")
print("  docker compose down       # keep database data")
print("  docker compose down -v    # also delete database data")

