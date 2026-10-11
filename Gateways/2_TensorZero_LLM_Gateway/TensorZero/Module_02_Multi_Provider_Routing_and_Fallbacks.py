#!/usr/bin/env python
# coding: utf-8

# # Module 2 -- Multi-Provider Routing and Fallbacks

# ## Before You Start
# 
# Make sure your Module 1 Docker stack is still running:
# 
# ```powershell
# cd tensorzero-demo
# docker compose ps
# ```
# 
# You should see `gateway`, `postgres`, and `ui` all in `Up (healthy)` state.  
# If not, run `docker compose up -d --wait` to start it again.
# 
# In this module we will **only edit `tensorzero.toml`** and restart the gateway.  
# No changes to `docker-compose.yml` or `.env`.
# 
# ---

# ---
# # Part 1 -- Theory: Why Multi-Provider Routing?
# 
# ---

# ![image.png](attachment:image.png)

# ## 1.2 -- TensorZero's Routing Architecture
# 
# TensorZero has **two levels** where routing decisions happen:
# 
# 

# ![image.png](attachment:image.png)

# ## 1.3 -- A Note on Azure vs Groq
# 
# In many production setups, the fallback pattern is **OpenAI --> Azure OpenAI**:  
# same GPT model, different hosting, same output quality.
# 
# Since we are using OpenAI + Groq in this course (no Azure account needed),  
# we will demonstrate: **OpenAI --> Groq**.
# 
# ---

# ---
# # Part 2 -- Provider-Level Routing: OpenAI -> Groq Fallback
# 
# ---

# ## 2.1 -- Updating tensorzero.toml
# 
# We will add two new models to `tensorzero.toml`:
# 
# **Model 1: `resilient_gpt`** -- OpenAI primary, Groq fallback (normal use)
# ```toml
# [models.resilient_gpt]
# routing = ["openai_primary", "groq_fallback"]
# ```
# 
# **Model 2: `demo_failover`** -- Broken provider primary, Groq rescue (failure demo)  
# The broken provider points to `http://localhost:9999` -- nothing is listening there.  
# This guarantees a connection failure, forcing fallback to Groq.
# 
# ```toml
# [models.demo_failover]
# routing = ["broken_provider", "groq_rescue"]
# 
# [models.demo_failover.providers.broken_provider]
# type = "openai"
# model_name = "gpt-4o-mini"
# api_base = "http://localhost:9999/v1"   # <-- nothing here, guaranteed failure
# ```
# 
# When a request hits `demo_failover`:
# 1. Gateway tries `broken_provider` --> connection refused (instant)
# 2. Gateway logs the failure internally
# 3. Gateway tries `groq_rescue` --> succeeds
# 4. Response returned to user -- they see no error

# In[1]:


# ─────────────────────────────────────────────────────────────────
# CELL 1: Setup -- point to our existing project from Module 1
# ─────────────────────────────────────────────────────────────────
from pathlib import Path
import os

project_dir = Path("tensorzero-demo")
config_dir  = project_dir / "config"

# Verify Module 1 stack exists
assert (project_dir / "docker-compose.yml").exists(), "Run Module 1 first!"
assert (config_dir  / "tensorzero.toml").exists(),    "Run Module 1 first!"

print("Module 1 project found:")
for f in sorted(config_dir.iterdir()):
    print(f"  config/{f.name}")

GATEWAY_URL = "http://localhost:3000"


# In[2]:


# ─────────────────────────────────────────────────────────────────
# CELL 2: Write updated tensorzero.toml
# Adds multi-provider routing on top of Module 1 config.
# ─────────────────────────────────────────────────────────────────

tensorzero_toml = """\
# ================================================================
# tensorzero.toml -- Module 2: Multi-Provider Routing
# ================================================================


# ================================================================
# MODULE 1 FUNCTIONS (kept from previous module)
# ================================================================

[functions.summarize]
type = "chat"

[functions.summarize.variants.gpt_variant]
type            = "chat_completion"
model           = "openai::gpt-4o-mini"
system_template = "summarize_system.minijinja"
weight          = 1

[functions.summarize.variants.groq_variant]
type            = "chat_completion"
model           = "groq::llama-3.1-8b-instant"
system_template = "summarize_system.minijinja"
weight          = 0

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


# ================================================================
# MODULE 2: MULTI-PROVIDER ROUTING
# ================================================================

# ── Model 1: resilient_gpt ──────────────────────────────────────
# OpenAI as primary, Groq as fallback.
# routing = [...] defines the ORDER providers are tried.
# If openai_primary fails for any reason (outage, rate limit,
# timeout), TensorZero AUTOMATICALLY tries groq_fallback next.
# Your application code never knows a fallback happened.

[models.resilient_gpt]
routing = ["openai_primary", "groq_fallback"]

[models.resilient_gpt.providers.openai_primary]
type       = "openai"
model_name = "gpt-4o-mini"

[models.resilient_gpt.providers.groq_fallback]
type       = "groq"
model_name = "llama-3.1-8b-instant"


# ── Model 2: demo_failover ──────────────────────────────────────
# Used ONLY to demonstrate fallback behavior in this notebook.
# broken_provider points to localhost:9999 -- nothing is there.
# This causes an immediate connection failure, forcing fallback
# to groq_rescue. In real life this simulates OpenAI being down.

[models.demo_failover]
routing = ["broken_provider", "groq_rescue"]

[models.demo_failover.providers.broken_provider]
type       = "openai"
model_name = "gpt-4o-mini"
api_base   = "http://localhost:9999/v1"

[models.demo_failover.providers.groq_rescue]
type       = "groq"
model_name = "llama-3.1-8b-instant"


# ── Function: routed_chat ───────────────────────────────────────
# Normal function using the resilient_gpt model.
# Under normal conditions: served by OpenAI.
# If OpenAI is down: transparently served by Groq.

[functions.routed_chat]
type = "chat"

[functions.routed_chat.variants.resilient_variant]
type   = "chat_completion"
model  = "resilient_gpt"
weight = 1


# ── Function: failover_demo ─────────────────────────────────────
# Demo function for observing fallback behavior.
# Primary provider is intentionally broken.

[functions.failover_demo]
type = "chat"

[functions.failover_demo.variants.with_fallback]
type   = "chat_completion"
model  = "demo_failover"
weight = 1
"""

toml_file = config_dir / "tensorzero.toml"
toml_file.write_text(tensorzero_toml, encoding="utf-8")

print(f"Written: {toml_file.resolve()}")
print()
print("New models added:")
print("  resilient_gpt  -> openai_primary -> groq_fallback")
print("  demo_failover  -> broken_provider (port 9999) -> groq_rescue")
print()
print("New functions added:")
print("  routed_chat    -> resilient_variant (uses resilient_gpt)")
print("  failover_demo  -> with_fallback (uses demo_failover)")


# In[3]:


# ─────────────────────────────────────────────────────────────────
# CELL 3: Restart gateway to pick up new config
# Only the gateway needs restart -- postgres and ui stay running.
# ─────────────────────────────────────────────────────────────────
import subprocess
import time
import urllib.request

print("Restarting gateway...")
result = subprocess.run(
    ["docker", "compose", "restart", "gateway"],
    cwd=str(project_dir.resolve()),
    capture_output=True, text=True
)
print(result.stdout.strip() or result.stderr.strip())

# Wait for gateway to be healthy again
print("Waiting for gateway to be healthy...")
for attempt in range(20):
    try:
        urllib.request.urlopen("http://localhost:3000/health", timeout=3)
        print(f"Gateway healthy after {attempt + 1} attempts")
        break
    except Exception:
        time.sleep(2)
else:
    print("Gateway did not come back healthy. Check logs.")


# ## 2.2 -- Demo: Normal Routing (OpenAI Handles Request)
# 
# When everything is working, `routed_chat` routes to `openai_primary` (first in the list).  
# We can confirm this by checking which provider served the request in the gateway logs  
# and in the TensorZero UI at `http://localhost:4000`.
# 
# The key field to watch: **`variant_name`** tells you which variant handled the call.  
# For provider-level routing within a variant, you inspect the gateway logs.

# In[4]:


# ─────────────────────────────────────────────────────────────────
# CELL 4: Normal Routing -- OpenAI handles the request
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway
import time

QUESTION = "What is a ML model"

print("Calling 'routed_chat' function (OpenAI primary, Groq fallback)")
print("Under normal conditions, OpenAI should handle this request.")
print()

start = time.time()

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:
    result = client.inference(
        function_name="routed_chat",
        input={"messages": [{"role": "user", "content": QUESTION}]}
    )

elapsed = time.time() - start

print(f"inference_id:  {result.inference_id}")
print(f"variant_name:  {result.variant_name}")
print(f"latency:       {elapsed:.2f}s")
print()
print("Response:")
print(result.content[0].text[:400], "...")
print()
print("Check http://localhost:4000 -> Inferences to see which provider was used.")


# ## 2.3 -- Demo: Simulating Provider Failure and Watching Fallback
# 
# Now we call `failover_demo` -- a function whose primary provider is deliberately broken.  
# The broken provider points to `http://localhost:9999` where nothing is listening.
# 
# **What will happen step by step:**
# 
# ```
# 1. Your code calls failover_demo
# 2. Gateway tries broken_provider (localhost:9999)
#    --> Connection refused immediately (no server there)
#    --> Gateway logs this failure internally
# 3. Gateway tries groq_rescue (Groq API)
#    --> Success: 200 OK
# 4. Gateway returns response to your code
#    --> Your code sees a normal successful response
#    --> No exception raised, no error returned
# ```
# 
# **The key point for course students:**  
# Your application code is identical for both demos (Cells 4 and 5).  
# Only the TOML configuration differs. The fallback is completely invisible to your code.

# In[5]:


# ─────────────────────────────────────────────────────────────────
# CELL 5: Failure Demo -- broken provider triggers Groq fallback
# Same code as Cell 4 -- only function_name changes.
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway
import time

print("Calling 'failover_demo' function (broken primary -> Groq rescue)")
print("Primary provider is localhost:9999 -- nothing there, will fail.")
print("Watch TensorZero silently fall back to Groq.")
print()

start = time.time()

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:
    result = client.inference(
        function_name="failover_demo",
        input={"messages": [{"role": "user", "content": QUESTION}]}
    )

elapsed = time.time() - start

print(f"inference_id:  {result.inference_id}")
print(f"variant_name:  {result.variant_name}")
print(f"latency:       {elapsed:.2f}s")
print()
print("Response (served by Groq after OpenAI 'failed'):")
print(result.content[0].text[:400], "...")
print()
print("No exception was raised -- fallback was transparent to this code.")


# ---
# # Part 3 -- Retries: Provider-Level vs Variant-Level
# 
# ---

# ## 3.1 -- How TensorZero Handles Retries
# 
# 

# ![image.png](attachment:image.png)

# ### The Mental Model: routing = your fallback chain
# 
# ```toml
# routing = ["primary", "secondary", "tertiary"]
# ```
# 
# Think of this as: *"try primary, then secondary, then tertiary"*.  
# Each entry is a completely independent provider with its own credentials and endpoint.  

# ## 3.2 -- Provider-Level vs Variant-Level Fallback: The Key Difference
# 

# ![image.png](attachment:image.png)

# In[6]:


# ─────────────────────────────────────────────────────────────────
# CELL 7: Compare -- Single Provider vs Multi-Provider
# Make 3 requests to each function and compare reliability.
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway
import time

PROMPTS = [
    "What is ML",
    "What is DL in AI field",
    "What is SQL ?",
]

print("Sending 3 requests to each function")
print()

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:

    # Single provider: direct OpenAI (from Module 1)
    print("--- chat (single provider: OpenAI only) ---")
    for i, prompt in enumerate(PROMPTS, 1):
        t = time.time()
        r = client.inference(
            function_name="chat",
            input={"messages": [{"role": "user", "content": prompt}]}
        )
        print(f"  Request {i}: OK in {time.time()-t:.2f}s -- {r.content[0].text[:60]}...")

    print()

    # Multi-provider: OpenAI primary, Groq fallback
    print("--- routed_chat (OpenAI primary, Groq fallback) ---")
    for i, prompt in enumerate(PROMPTS, 1):
        t = time.time()
        r = client.inference(
            function_name="routed_chat",
            input={"messages": [{"role": "user", "content": prompt}]}
        )
        print(f"  Request {i}: OK in {time.time()-t:.2f}s -- {r.content[0].text[:60]}...")

print()
print("Both work identically under normal conditions.")
print("The difference only shows when OpenAI has a problem.")


# ## The Real Lesson: Reliability, Not the Output
# 
# This lesson is not about what you **see**. It's about what you **don't see**.
# 
# ### With `chat` (Single Provider)
# 
# All 3 requests worked ✅
# 
# But that happened because OpenAI was available at the time.
# 
# If OpenAI experiences an outage:
# 
# - Request 1 ❌ Fails
# - Request 2 ❌ Fails
# - Request 3 ❌ Fails
# 
# Your application has no backup provider, so every request depends entirely on OpenAI.
# 
# ### With `routed_chat` (Multi-Provider)
# 
# All 3 requests worked ✅
# 
# However, the important difference is that you now have **failover protection**.
# 
# OpenAI is still your primary provider, but Groq is standing by as a backup.
# 
# If OpenAI experiences an outage:
# 
# - Request 1 ✅ Automatically routed to Groq
# - Request 2 ✅ Automatically routed to Groq
# - Request 3 ✅ Automatically routed to Groq
# 
# From the user's perspective, the requests continue to succeed.

# In[7]:


## FAILURE SECANRIO WHEN OPENAI is Down midway


import subprocess, time, urllib.request

extra_config = """
[models.broken_only]
routing = ["dead_provider"]

[models.broken_only.providers.dead_provider]
type       = "openai"
model_name = "gpt-4o-mini"
api_base   = "http://localhost:9999/v1"

[functions.chat_no_fallback]
type = "chat"

[functions.chat_no_fallback.variants.single_broken]
type   = "chat_completion"
model  = "broken_only"
weight = 1
"""

existing = (config_dir / "tensorzero.toml").read_text(encoding="utf-8")
(config_dir / "tensorzero.toml").write_text(existing + extra_config, encoding="utf-8")

subprocess.run(["docker", "compose", "restart", "gateway"],
               cwd=str(project_dir.resolve()), capture_output=True)

for _ in range(15):
    try:
        urllib.request.urlopen("http://localhost:3000/health", timeout=2)
        print("Gateway ready.")
        break
    except Exception:
        time.sleep(1)


# In[8]:


from tensorzero import TensorZeroGateway
import time

print("Simulating: OpenAI goes DOWN mid-session")
print()

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:

    print("--- chat_no_fallback (no safety net) ---")

    # Request 1 -- use real chat function (OpenAI UP)
    t = time.time()
    r = client.inference(
        function_name="chat",
        input={"messages": [{"role": "user", "content": "What is ML"}]}
    )
    print(f"  Request 1: OK in {time.time()-t:.2f}s -- {r.content[0].text[:60]}...")

    # Requests 2 & 3 -- OpenAI "goes down" (switch to broken function)
    for i, prompt in enumerate(["Name one benefit of provider fallback.",
                                  "What does TensorZero store in PostgreSQL?"], 2):
        t = time.time()
        try:
            r = client.inference(
                function_name="chat_no_fallback",
                input={"messages": [{"role": "user", "content": prompt}]}
            )
            print(f"  Request {i}: OK in {time.time()-t:.2f}s -- {r.content[0].text[:60]}...")
        except Exception as e:
            print(f"  Request {i}: FAILED in {time.time()-t:.2f}s -- app crashes here")

    print()

    print("--- failover_demo (Groq rescue) ---")

    # Request 1 -- working (same as above)
    t = time.time()
    r = client.inference(
        function_name="chat",
        input={"messages": [{"role": "user", "content": "What is an LLM gateway?"}]}
    )
    print(f"  Request 1: OK in {time.time()-t:.2f}s -- {r.content[0].text[:60]}...")

    # Requests 2 & 3 -- OpenAI "goes down" but Groq rescues
    for i, prompt in enumerate(["Name one benefit of provider fallback.",
                                  "What does TensorZero store in PostgreSQL?"], 2):
        t = time.time()
        r = client.inference(
            function_name="failover_demo",
            input={"messages": [{"role": "user", "content": prompt}]}
        )
        print(f"  Request {i}: OK in {time.time()-t:.2f}s -- {r.content[0].text[:60]}...")

print()
print("Request 1 passed for both -- OpenAI was up.")
print("Requests 2-3: no fallback = crashed, with fallback = survived.")


# ---
# # Part 4 -- Variant Fallbacks: Swapping the Whole Implementation
# 
# ---

# ## 4.1 -- What Does "Swap the Whole Implementation" Mean?

# ![image.png](attachment:image.png)

# In[9]:


# ─────────────────────────────────────────────────────────────────
# CELL 8: Simulate Emergency Variant Swap
# Step 1: Write config with GPT-4o-mini as primary (normal)
# Step 2: "Emergency" -- switch to Groq by flipping weights
# Step 3: Switch back (rollback)
# ─────────────────────────────────────────────────────────────────
import subprocess
import time
import urllib.request

def write_toml_with_weights(gpt_weight: int, groq_weight: int):
    """Write tensorzero.toml with specified variant weights and restart gateway."""

    toml = f"""\
# Module 2 config -- variant swap demo

[functions.summarize]
type = "chat"

[functions.summarize.variants.gpt_variant]
type            = "chat_completion"
model           = "openai::gpt-4o-mini"
system_template = "summarize_system.minijinja"
weight          = 1

[functions.summarize.variants.groq_variant]
type            = "chat_completion"
model           = "groq::llama-3.1-8b-instant"
system_template = "summarize_system.minijinja"
weight          = 0

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

[models.resilient_gpt]
routing = ["openai_primary", "groq_fallback"]

[models.resilient_gpt.providers.openai_primary]
type       = "openai"
model_name = "gpt-4o-mini"

[models.resilient_gpt.providers.groq_fallback]
type       = "groq"
model_name = "llama-3.1-8b-instant"

[models.demo_failover]
routing = ["broken_provider", "groq_rescue"]

[models.demo_failover.providers.broken_provider]
type       = "openai"
model_name = "gpt-4o-mini"
api_base   = "http://localhost:9999/v1"

[models.demo_failover.providers.groq_rescue]
type       = "groq"
model_name = "llama-3.1-8b-instant"

[functions.routed_chat]
type = "chat"

[functions.routed_chat.variants.resilient_variant]
type   = "chat_completion"
model  = "resilient_gpt"
weight = 1

[functions.failover_demo]
type = "chat"

[functions.failover_demo.variants.with_fallback]
type   = "chat_completion"
model  = "demo_failover"
weight = 1

# Emergency swap function
[functions.emergency_chat]
type = "chat"

[functions.emergency_chat.variants.gpt_primary]
type   = "chat_completion"
model  = "openai::gpt-4o-mini"
weight = {gpt_weight}

[functions.emergency_chat.variants.groq_standby]
type   = "chat_completion"
model  = "groq::llama-3.3-70b-versatile"
weight = {groq_weight}
"""

    (config_dir / "tensorzero.toml").write_text(toml, encoding="utf-8")

    subprocess.run(
        ["docker", "compose", "restart", "gateway"],
        cwd=str(project_dir.resolve()),
        capture_output=True
    )
    for _ in range(15):
        try:
            urllib.request.urlopen("http://localhost:3000/health", timeout=2)
            break
        except Exception:
            time.sleep(1)

print("Helper function defined: write_toml_with_weights(gpt_weight, groq_weight)")
print("We will use this to simulate an emergency variant swap.")


# In[10]:


# ─────────────────────────────────────────────────────────────────
# CELL 9: Normal State -- GPT-4o-mini handles all traffic
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway

print("=== NORMAL STATE: gpt_primary weight=1, groq_standby weight=0 ===")
write_toml_with_weights(gpt_weight=1, groq_weight=0)
print("Config updated. Gateway restarted.")
print()

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:
    r = client.inference(
        function_name="emergency_chat",
        input={"messages": [{"role": "user", "content": "Say 'hello' in one word."}]}
    )
    print(f"variant_name: {r.variant_name}   <-- should be 'gpt_primary'")
    print(f"response:     {r.content[0].text}")


# In[11]:


# ─────────────────────────────────────────────────────────────────
# CELL 10: Emergency Swap -- flip to Groq instantly
# Scenario: GPT-4o-mini costs spiked, switch to Groq to save money.
# Zero code change. Just flip weights in config + restart gateway.
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway

print("=== EMERGENCY SWAP: gpt_primary weight=0, groq_standby weight=1 ===")
write_toml_with_weights(gpt_weight=0, groq_weight=1)
print("Config updated. Gateway restarted.")
print()

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:
    r = client.inference(
        function_name="emergency_chat",
        input={"messages": [{"role": "user", "content": "Say 'hello' in one word."}]}
    )
    print(f"variant_name: {r.variant_name}   <-- should be 'groq_standby'")
    print(f"response:     {r.content[0].text}")
    print()
    print("Application code is IDENTICAL to Cell 9.")
    print("Different model served -- pure config change.")


# In[12]:


# ─────────────────────────────────────────────────────────────────
# CELL 11: Rollback -- restore GPT-4o-mini as primary
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway

print("=== ROLLBACK: restoring gpt_primary weight=1, groq_standby weight=0 ===")
write_toml_with_weights(gpt_weight=1, groq_weight=0)
print("Rolled back. Gateway restarted.")
print()

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:
    r = client.inference(
        function_name="emergency_chat",
        input={"messages": [{"role": "user", "content": "Say 'hello' in one word."}]}
    )
    print(f"variant_name: {r.variant_name}   <-- back to 'gpt_primary'")
    print(f"response:     {r.content[0].text}")


# ---
# # Part 5 -- Benchmarking: Gateway Latency Overhead
# 
# ---

# ## 5.1 -- Why Latency Overhead Matters
# 
# A common objection to using an LLM gateway: *"doesn't it add latency?"*
# 
# The honest answer: **yes, but it is negligible** compared to LLM inference time.
# 
# ### What Adds Latency in an LLM Call:
# 
# ```
# Total latency = Network to provider + LLM inference time + Network back
#                      ~20ms               500ms - 10s            ~20ms
# 
# With gateway:
# Total latency = Network to gateway + Gateway processing + Network to provider + LLM inference + Network back
#                      ~0.1ms (localhost)    <1ms (Rust)          ~20ms              500ms-10s        ~20ms
# ```
# 
# The gateway adds **<1ms** because:
# 1. It runs **locally** (localhost, not over the internet)
# 2. It is written in **Rust** -- a systems language with no garbage collector, no runtime overhead
# 
# ### Why Rust?
# 
# Most Python web servers (Flask, FastAPI) add 2-10ms of overhead per request due to:
# - Python's Global Interpreter Lock (GIL)
# - Garbage collection pauses
# - Dynamic typing overhead
# 
# Rust adds essentially **zero** overhead because:
# - Compiled to native machine code (no interpreter)
# - Memory managed at compile time (no GC pauses)
# - Zero-cost abstractions -- high-level code compiles to as fast as hand-written C
# - Async I/O via Tokio (handles thousands of concurrent requests with minimal CPU)
# 
# TensorZero's p99 latency overhead is documented as **<1ms**.  
# Your LLM call is 500ms-10s. The gateway overhead is literally undetectable.

# In[13]:


# ─────────────────────────────────────────────────────────────────
# CELL 12: Benchmark Setup
# We will make N requests both ways and compare per-request latency.
# Using a short prompt to minimize LLM inference time variance.
# N=10 to keep cost and time reasonable.
# ─────────────────────────────────────────────────────────────────
import time
import statistics
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(project_dir / ".env")

N = 10   # number of requests per method (increase for more accurate results)
BENCH_PROMPT = "Reply with exactly one word: yes"

# Direct OpenAI client
direct_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# TensorZero client (OpenAI SDK pointed at gateway)
tz_client = OpenAI(
    api_key="not-used",
    base_url="http://localhost:3000/openai/v1"
)

print(f"Benchmark setup complete.")
print(f"Will run {N} requests per method.")
print(f"Prompt: '{BENCH_PROMPT}'")


# In[14]:


# ─────────────────────────────────────────────────────────────────
# CELL 13: Benchmark -- Direct OpenAI calls
# ─────────────────────────────────────────────────────────────────

print(f"Running {N} direct OpenAI requests...")
direct_times = []

for i in range(N):
    start = time.perf_counter()
    response = direct_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Be concise."},
            {"role": "user",   "content": BENCH_PROMPT}
        ],
        max_tokens=5
    )
    elapsed = (time.perf_counter() - start) * 1000  # ms
    direct_times.append(elapsed)
    print(f"  [{i+1:2d}/{N}] {elapsed:6.0f}ms  -- '{response.choices[0].message.content.strip()}'")

print()
print(f"Direct OpenAI stats ({N} requests):")
print(f"  Mean:   {statistics.mean(direct_times):.0f}ms")
print(f"  Median: {statistics.median(direct_times):.0f}ms")
print(f"  StdDev: {statistics.stdev(direct_times):.0f}ms")
print(f"  Min:    {min(direct_times):.0f}ms")
print(f"  Max:    {max(direct_times):.0f}ms")


# In[15]:


# ─────────────────────────────────────────────────────────────────
# CELL 14: Benchmark -- Through TensorZero Gateway
# ─────────────────────────────────────────────────────────────────

print(f"Running {N} requests through TensorZero gateway...")
tz_times = []

for i in range(N):
    start = time.perf_counter()
    response = tz_client.chat.completions.create(
        model="tensorzero::function_name::chat",
        messages=[{"role": "user", "content": BENCH_PROMPT}],
        max_tokens=5
    )
    elapsed = (time.perf_counter() - start) * 1000  # ms
    tz_times.append(elapsed)
    print(f"  [{i+1:2d}/{N}] {elapsed:6.0f}ms  -- '{response.choices[0].message.content.strip()}'")

print()
print(f"TensorZero gateway stats ({N} requests):")
print(f"  Mean:   {statistics.mean(tz_times):.0f}ms")
print(f"  Median: {statistics.median(tz_times):.0f}ms")
print(f"  StdDev: {statistics.stdev(tz_times):.0f}ms")
print(f"  Min:    {min(tz_times):.0f}ms")
print(f"  Max:    {max(tz_times):.0f}ms")


# In[ ]:




