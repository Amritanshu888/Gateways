#!/usr/bin/env python
# coding: utf-8

# # Module 3 -- Structured Inference: Prompts, Schemas and JSON
# 

# ---
# # Part 1 -- Theory: Why Structured Inference?
# ---
# 
# ## 1.1 -- The Problem with Raw LLM Output

# ![image.png](attachment:image.png)

# ---
# # Part 2 -- Prompt Templates with Minijinja
# ---
# 
# ## 2.1 -- What is Minijinja?
# 
# Minijinja is a **templating language** -- it lets you write prompt templates with  
# placeholders that get filled in at runtime.
# 
# ```
# Template file (greet_template.minijinja):
#   "Greet the user named {{ name }} in {{ language }}. Be {{ style }}."
# 
# At runtime, variables are substituted:
#   name     = "Alice"
#   language = "French"
#   style    = "formal"
# 
# Result sent to LLM:
#   "Greet the user named Alice in French. Be formal."
# ```
# 
# ### Why Templates Belong in the Gateway (Not Your Code)
# 
# ```
# WITHOUT gateway templates:              WITH gateway templates:
# 
# prompt = f"Greet {name} in           tensorzero.toml holds the template.
#   {language}. Be {style}."           Your code just passes variables:
#                                        {"name": "Alice",
# Every time you change the prompt,       "language": "French",
# you redeploy your app.                  "style": "formal"}
# 
# No history of what prompt was          Full history in Postgres:
# used for which inference.              every inference logs which
#                                        template version was used.
# ```
# 
# ### The New Template Syntax (TensorZero 2026+)
# 
# TensorZero introduced a named-template system. Templates are attached to variants  
# and referenced by name in inference calls:
# 
# ```toml
# [functions.greet_user.variants.gpt_variant]
# type  = "chat_completion"
# model = "openai::gpt-4o-mini"
# templates.greeting.path = "greet_template.minijinja"  # name = greeting
# ```
# 
# ```python
# client.inference(
#     function_name="greet_user",
#     input={
#         "type":      "tensorzero::template",
#         "name":      "greeting",           # matches templates.greeting.path
#         "arguments": {"name": "Alice",     # variables in the template
#                       "language": "French",
#                       "style": "formal"}
#     }
# )
# ```
# 
# ### Input Schema Enforcement
# 
# If you call a template and forget a required variable:
# 
# ```python
# input = {
#     "type":      "tensorzero::template",
#     "name":      "greeting",
#     "arguments": {"name": "Alice"}   # missing: language, style
# }
# # --> TensorZeroError: template variable 'language' not found
# # --> Clear error. Not a silent bad call with a broken prompt.
# ```
# 
# This is the **gateway enforcing input schema** -- one of TensorZero's key safety features.

# In[1]:


# ─────────────────────────────────────────────────────────────────
# CELL 1: Setup
# ─────────────────────────────────────────────────────────────────
from pathlib import Path
import subprocess, time, urllib.request

project_dir = Path("tensorzero-demo")
config_dir  = project_dir / "config"

assert (project_dir / "docker-compose.yml").exists(), "Run Module 1 first!"

GATEWAY_URL = "http://localhost:3000"

def restart_gateway():
    """Restart gateway and wait for healthy."""
    subprocess.run(["docker", "compose", "restart", "gateway"],
                   cwd=str(project_dir.resolve()), capture_output=True)
    for _ in range(20):
        try:
            urllib.request.urlopen(f"{GATEWAY_URL}/health", timeout=2)
            print("Gateway healthy.")
            return
        except Exception:
            time.sleep(1)
    print("Gateway did not come up -- check docker compose logs gateway")

print("Setup complete.")


# In[2]:


# ─────────────────────────────────────────────────────────────────
# CELL 2: Write Minijinja template files
# system_template = static system prompt loaded from config
# This is what actually works reliably with the native Python client.
# ─────────────────────────────────────────────────────────────────

# System prompt for greet_user
# This lives in the gateway config -- not in your application code.
greet_system = (
    "You are a greeting specialist. "
    "The user will tell you a name, a language, and a style. "
    "Generate a personalized greeting exactly matching those requirements. "
    "Reply with ONLY the greeting -- no extra commentary."
)
(config_dir / "greet_system.minijinja").write_text(greet_system, encoding="utf-8")
print("Written: config/greet_system.minijinja")

# Keep summarize system template from Module 1
summarize_system = (
    "You are an expert summarizer. "
    "Summarize the given text in 2-3 concise sentences. "
    "Preserve key facts and maintain a neutral tone."
)
(config_dir / "summarize_system.minijinja").write_text(summarize_system, encoding="utf-8")
print("Written: config/summarize_system.minijinja")

print()
print("Key concept:")
print("  System prompts live in config files -- not scattered in your application code.")
print("  Change the prompt by editing the .minijinja file + restart gateway.")
print("  No application redeployment needed.")


# In[3]:


# ─────────────────────────────────────────────────────────────────
# CELL 3: Write tensorzero.toml
# ─────────────────────────────────────────────────────────────────

tensorzero_toml = """\
# ================================================================
# tensorzero.toml -- Module 3: Structured Inference
# ================================================================


# ── Modules 1 & 2 functions (kept) ──────────────────────────────

[functions.summarize]
type = "chat"

[functions.summarize.variants.gpt_variant]
type            = "chat_completion"
model           = "openai::gpt-4o-mini"
system_template = "summarize_system.minijinja"

[functions.chat]
type = "chat"

[functions.chat.variants.gpt_mini]
type  = "chat_completion"
model = "openai::gpt-4o-mini"


# ================================================================
# MODULE 3 -- PART 2: PROMPT TEMPLATES
# ================================================================

# greet_user demonstrates system_template:
#   - System prompt lives in greet_system.minijinja (gateway config)
#   - User passes name/language/style as a plain message
#   - Changing the prompt = edit the file + restart gateway, no code change

[functions.greet_user]
type = "chat"

[functions.greet_user.variants.gpt_variant]
type            = "chat_completion"
model           = "openai::gpt-4o-mini"
system_template = "greet_system.minijinja"

[functions.greet_user.variants.groq_variant]
type            = "chat_completion"
model           = "groq::llama-3.1-8b-instant"
system_template = "greet_system.minijinja"


# ================================================================
# MODULE 3 -- PART 3: JSON STRUCTURED OUTPUT
# ================================================================

[functions.extract_contact]
type          = "json"
output_schema = "contact_schema.json"

[functions.extract_contact.variants.gpt_variant]
type            = "chat_completion"
model           = "openai::gpt-4o-mini"
system_template = "extract_contact_system.minijinja"
json_mode       = "on"

[functions.extract_contact.variants.groq_variant]
type            = "chat_completion"
model           = "groq::llama-3.3-70b-versatile"
system_template = "extract_contact_system.minijinja"
json_mode       = "on"


# ================================================================
# MODULE 3 -- PART 4: TOOL USE
# ================================================================

[tools.get_current_time]
description = "Returns the current date and time for a given timezone."
parameters  = "get_current_time_params.json"

[tools.calculate]
description = "Evaluates a simple arithmetic expression and returns the result."
parameters  = "calculate_params.json"

[functions.tool_assistant]
type  = "chat"
tools = ["get_current_time", "calculate"]

[functions.tool_assistant.variants.gpt_variant]
type  = "chat_completion"
model = "openai::gpt-4o-mini"

[functions.tool_assistant.variants.groq_variant]
type  = "chat_completion"
model = "groq::llama-3.3-70b-versatile"
"""

(config_dir / "tensorzero.toml").write_text(tensorzero_toml, encoding="utf-8")
print("Written: config/tensorzero.toml")
print()
print("Functions defined:")
print("  greet_user      (chat)  -- system_template from config")
print("  extract_contact (json)  -- structured JSON output")
print("  tool_assistant  (chat)  -- tool use / function calling")


# In[4]:


# ─────────────────────────────────────────────────────────────────
# CELL 4: Write all supporting config files
# ─────────────────────────────────────────────────────────────────
import json

# ── System prompt for extract_contact ───────────────────────────
extract_system = (
    "You are a contact information extractor. "
    "Extract name, email, and phone from the provided text. "
    "If a field is not present, return null for that field. "
    "Return only valid JSON with keys: name, email, phone."
)
(config_dir / "extract_contact_system.minijinja").write_text(
    extract_system, encoding="utf-8"
)

# ── JSON Schema for extract_contact output ───────────────────────
contact_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "name":  {"type": ["string", "null"], "description": "Full name of the contact"},
        "email": {"type": ["string", "null"], "description": "Email address"},
        "phone": {"type": ["string", "null"], "description": "Phone number"}
    },
    "required": ["name", "email", "phone"],
    "additionalProperties": False
}
(config_dir / "contact_schema.json").write_text(
    json.dumps(contact_schema, indent=2), encoding="utf-8"
)

# ── Tool parameter schemas ───────────────────────────────────────
get_time_params = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "timezone": {
            "type": "string",
            "description": "IANA timezone name e.g. America/New_York, Asia/Kolkata, UTC"
        }
    },
    "required": ["timezone"],
    "additionalProperties": False
}
(config_dir / "get_current_time_params.json").write_text(
    json.dumps(get_time_params, indent=2), encoding="utf-8"
)

calculate_params = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "expression": {
            "type": "string",
            "description": "Arithmetic expression to evaluate e.g. '12 * 8 + 5'"
        }
    },
    "required": ["expression"],
    "additionalProperties": False
}
(config_dir / "calculate_params.json").write_text(
    json.dumps(calculate_params, indent=2), encoding="utf-8"
)

print("All config files written:")
for f in sorted(config_dir.iterdir()):
    print(f"  config/{f.name}")


# In[5]:


# ─────────────────────────────────────────────────────────────────
# CELL 5: Restart gateway to load Module 3 config
# ─────────────────────────────────────────────────────────────────
restart_gateway()


# ## 2.2 -- Demo: Named Templates with Variables

# In[6]:


# ─────────────────────────────────────────────────────────────────
# CELL 6: Template inference -- system_template from gateway config
# The system prompt is loaded from greet_system.minijinja by the gateway.
# Your code only passes the user's input -- the prompt logic is in config.
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:

    # Example 1: Formal greeting in French
    r1 = client.inference(
        function_name="greet_user",
        input={
            "messages": [{
                "role": "user",
                "content": "Name: Alice | Language: French | Style: formal"
            }]
        }
    )
    print(f"Example 1 [variant={r1.variant_name}]:")
    print(f"  {r1.content[0].text}")
    print()

    # Example 2: Casual greeting in Spanish
    r2 = client.inference(
        function_name="greet_user",
        input={
            "messages": [{
                "role": "user",
                "content": "Name: Carlos | Language: Spanish | Style: casual and friendly"
            }]
        }
    )
    print(f"Example 2 [variant={r2.variant_name}]:")
    print(f"  {r2.content[0].text}")
    print()

    # Example 3: Polite Japanese greeting
    r3 = client.inference(
        function_name="greet_user",
        input={
            "messages": [{
                "role": "user",
                "content": "Name: Kenji | Language: Japanese | Style: very polite and professional"
            }]
        }
    )
    print(f"Example 3 [variant={r3.variant_name}]:")
    print(f"  {r3.content[0].text}")
    print()

print("The system prompt (greet_system.minijinja) lives in gateway config.")
print("Your code only passes user variables -- no prompt strings in application code.")


# ## 2.3 -- Demo: Gateway Enforces Input Schema
# 
# The gateway **validates your inference input** before sending anything to the LLM.  
# If a required template variable is missing, you get a clear error immediately -- not a silent bad call.

# In[7]:


# ─────────────────────────────────────────────────────────────────
# CELL 7: Show what happens when you swap the system prompt
# The gateway value: change prompt in config, restart gateway.
# No application code change. No redeploy.
# ─────────────────────────────────────────────────────────────────
import subprocess, time, urllib.request

print("=== CURRENT prompt (formal greeting specialist) ===")
with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:
    r = client.inference(
        function_name="greet_user",
        input={"messages": [{"role": "user",
               "content": "Name: Alice | Language: English | Style: formal"}]}
    )
    print(f"Response: {r.content[0].text}")

print()
print("Now changing the system prompt to a different style...")
print()

# Swap the prompt in config -- no code change in the app
new_prompt = (
    "You are a pirate greeting specialist. "
    "Always greet in a pirate style, regardless of the style requested. "
    "Use 'Arrr!' and pirate language. Reply with ONLY the greeting."
)
(config_dir / "greet_system.minijinja").write_text(new_prompt, encoding="utf-8")

# Restart gateway to pick up new prompt
subprocess.run(["docker", "compose", "restart", "gateway"],
               cwd=str(project_dir.resolve()), capture_output=True)
for _ in range(20):
    try:
        urllib.request.urlopen(f"{GATEWAY_URL}/health", timeout=2)
        break
    except Exception:
        time.sleep(1)

print("=== NEW prompt (pirate style -- same app code, different config) ===")
with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:
    r = client.inference(
        function_name="greet_user",
        input={"messages": [{"role": "user",
               "content": "Name: Alice | Language: English | Style: formal"}]}
    )
    print(f"Response: {r.content[0].text}")

print()
print("IDENTICAL application code. Completely different behaviour.")
print("The prompt change happened at the gateway -- zero application changes.")

# Restore original prompt
(config_dir / "greet_system.minijinja").write_text(
    "You are a greeting specialist. The user will tell you a name, a language, and a style. "
    "Generate a personalized greeting exactly matching those requirements. "
    "Reply with ONLY the greeting -- no extra commentary.",
    encoding="utf-8"
)
subprocess.run(["docker", "compose", "restart", "gateway"],
               cwd=str(project_dir.resolve()), capture_output=True)
for _ in range(20):
    try:
        urllib.request.urlopen(f"{GATEWAY_URL}/health", timeout=2)
        break
    except Exception:
        time.sleep(1)
print("Original prompt restored.")


# ---
# # Part 3 -- JSON Structured Outputs
# ---
# 
# ## 3.1 -- How TensorZero Enforces JSON Output
# 
# When `type = "json"` in your function config, TensorZero:
# 
# ```
# 1. Sends request to LLM with JSON mode instructions
# 2. Receives response
# 3. Validates response against output_schema.json
# 4. If valid   --> returns parsed JSON to your app
# 5. If invalid --> RETRIES automatically (up to configured limit)
# 6. If retries exhausted --> returns error (never returns bad JSON silently)
# ```
# 
# ### json_mode Options:
# 
# | Value | How it works | Works with |
# |-------|-------------|------------|
# | `"off"` | No JSON enforcement | All providers |
# | `"on"` | Basic JSON mode | OpenAI, Groq, most providers |
# | `"strict"` | Strict schema validation | OpenAI only |
# | `"tool"` | Uses tool calling to force JSON | All providers with tools |
# 
# For this course (OpenAI + Groq), use `"on"` for broad compatibility.
# 
# ### What the Response Looks Like:
# 
# With `type = "chat"` -- response is a string:  
# `result.content[0].text`  --> `"The contact is Alice..."`
# 
# With `type = "json"` -- response is already parsed:  
# `result.output.parsed`  --> `{"name": "Alice", "email": "alice@example.com", "phone": null}`

# In[8]:


# ─────────────────────────────────────────────────────────────────
# CELL 8: JSON structured output -- extract_contact function
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway
import json

SAMPLE_TEXTS = [
    "Hi, I am Sarah Johnson and you can reach me at sarah.j@example.com or call +1-555-0192",
    "My name is Raj Patel. Email: raj.patel@techcorp.in. No phone provided.",
    "Please contact support@myapp.com for any issues. The team is available 24/7.",
]

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:

    for i, text in enumerate(SAMPLE_TEXTS, 1):
        result = client.inference(
            function_name="extract_contact",
            input={"messages": [{"role": "user", "content": text}]}
        )

        print(f"Sample {i}:")
        print(f"  Input:  {text[:70]}...")

        # For JSON functions, output is in result.output
        # result.output.parsed is the Python dict (already validated against schema)
        # result.output.raw    is the raw JSON string from the model
        parsed = result.output.parsed
        print(f"  Output: {json.dumps(parsed, indent=None)}")
        print(f"    name:  {parsed.get('name')}")
        print(f"    email: {parsed.get('email')}")
        print(f"    phone: {parsed.get('phone')}")
        print()


# ## 3.2 -- JSON Function vs Chat Function: Key Differences
# 
# ```python
# # Chat function response:
# result = client.inference(function_name="chat", input={...})
# text = result.content[0].text         # plain string
# # "The contact is Sarah Johnson, email sarah.j@example.com..."
# 
# # JSON function response:
# result = client.inference(function_name="extract_contact", input={...})
# data = result.output.parsed            # already-validated Python dict
# # {"name": "Sarah Johnson", "email": "sarah.j@example.com", "phone": "+1-555-0192"}
# ```
# 
# **Why this matters in production:**
# 
# ```
# Without TensorZero JSON mode:       With TensorZero JSON mode:
# 
# response = llm.call(prompt)         response = gateway.inference("extract_contact", ...)
# try:                                data = response.output.parsed  # always valid
#     data = json.loads(response)     name  = data["name"]          # always present
# except json.JSONDecodeError:        email = data["email"]         # null if missing
#     data = extract_with_regex(...)  # use safely, no try/except needed
# if "name" not in data:
#     data["name"] = None
# # ...5 more lines of defensive code
# ```
# 
# TensorZero eliminates the defensive parsing code. The gateway guarantees the schema.

# ---
# # Part 4 -- Tool Use (Function Calling) Through the Gateway
# ---
# 
# ## 4.1 -- What is Tool Use?
# 
# Tool use (also called function calling) lets the LLM request that your application  
# execute a function and return the result. The LLM decides **when** and **which** tool to call.
# 
# ```
# User:   "What is 347 * 28?"
# 
# Normal LLM:   "347 * 28 = 9716"   (might be wrong -- LLMs make math errors)
# 
# LLM + Tool:   1. LLM returns: {tool: "calculate", args: {expression: "347 * 28"}}
#               2. Your code runs: eval("347 * 28") = 9716
#               3. Your code sends result back: "The answer is 9716"
#               4. LLM returns: "347 multiplied by 28 equals 9716"
# ```
# 
# ## 4.2 -- Why Tools Go Through the Gateway
# 
# OpenAI and Groq use **different JSON formats** for tool calls in their raw APIs:
# 
# ```
# OpenAI raw tool call:                Groq raw tool call:
# {
#   "tool_calls": [{                   (similar but with subtle differences
#     "id": "call_abc123",             in field names, types, and structure)
#     "type": "function",
#     "function": {
#       "name": "calculate",
#       "arguments": "{\"expression\": \"347 * 28\"}"
#     }
#   }]
# }
# ```
# 
# TensorZero **normalises** this into one consistent format regardless of provider.  
# When you switch from OpenAI to Groq, your tool-handling code does not change at all.
# 
# ### How Tools Are Configured in TensorZero:
# 
# ```
# Step 1: Define the tool in [tools.name] with a parameters JSON Schema
# Step 2: Attach to a function with tools = ["tool_name"]
# Step 3: Set tool_choice on the variant ("auto", "required", "none")
# Step 4: In your inference call, handle tool_call results from the response
# ```

# In[ ]:


# ─────────────────────────────────────────────────────────────────
# CELL 10: Tool use -- first call, model requests a tool
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:

    print("Asking a math question -- model should call 'calculate' tool")
    print()

    result = client.inference(
        function_name="tool_assistant",
        input={"messages": [
            {"role": "user", "content": "What is 347 multiplied by 28?"}
        ]}
    )

    print(f"variant_name: {result.variant_name}")
    print(f"inference_id: {result.inference_id}")
    print()

    # Check what the model returned
    for block in result.content:
        print(f"Content block type: {type(block).__name__}")

        # If model called a tool, block is a ToolCallBlock
        if hasattr(block, 'name'):
            print(f"  Tool called:  {block.name}")
            print(f"  Tool call ID: {block.id}")
            print(f"  Arguments:    {block.arguments}")
            print()
            print("  The model wants us to run this tool.")
            print("  Next step: execute the tool, send result back to model.")

        # If model responded directly (no tool call)
        elif hasattr(block, 'text'):
            print(f"  Direct response: {block.text}")


# In[14]:


print(eval("10+20"))


# In[25]:


from tensorzero import TensorZeroGateway
import json
import datetime

def execute_tool(tool_name: str, arguments: dict) -> str:
    if tool_name == "calculate":
        expr = arguments.get("expression", "")
        allowed = set("0123456789+-*/()., ")
        if all(c in allowed for c in expr):
            return str(eval(expr))
        return "Error: unsafe expression"
    elif tool_name == "get_current_time":
        now = datetime.datetime.now(datetime.timezone.utc)
        return f"{now.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    return f"Unknown tool: {tool_name}"


def chat_with_tools(user_message1: str , user_message2: str):
    with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:

        # Turn 1: model decides which tool to call
        result = client.inference(
            function_name="tool_assistant",
            input={"messages": [{"role": "user", "content": user_message1}]}
        )
        episode_id = result.episode_id

        tool_calls = [b for b in result.content if hasattr(b, 'name') and hasattr(b, 'id')]

        if tool_calls:
            print(f"Model requested {len(tool_calls)} tool call(s):")

            tool_results_text = ""
            for tc in tool_calls:
                args = tc.arguments if isinstance(tc.arguments, dict) else json.loads(tc.arguments)
                tool_output = execute_tool(tc.name, args)
                print(f"  Tool: {tc.name}({args}) --> {tool_output}")
                tool_results_text += f"{tc.name} returned: {tool_output}"

            
            result2 = client.inference(
                function_name="tool_assistant",
                input={"messages": [{"role": "user", "content": user_message2}]},
                episode_id=episode_id
            )
            print()
            print(f"Final answer: {result2.content}")

        else:
            text_blocks = [b for b in result.content if hasattr(b, 'text')]
            print(f"Direct answer: {text_blocks[0].text if text_blocks else '(empty)'}")


print("=" * 55)
print("Question 1: Math")
print("=" * 55)
chat_with_tools("What is 347 multiplied by 28?" , "What is the current time in Asia")



# ## 4.3 -- Provider Normalisation: OpenAI vs Groq Tool Format
# 
# This is the gateway's hidden value in tool use.  
# Without TensorZero, switching from OpenAI to Groq requires rewriting your tool-handling code  
# because the raw response formats differ.
# 
# **With TensorZero:**
# 
# ```
# OpenAI variant:  model returns tool call --> gateway normalises --> your code gets ToolCallBlock
# Groq variant:    model returns tool call --> gateway normalises --> your code gets ToolCallBlock
#                                                                     (identical structure)
# ```
# 
# Your `execute_tool()` function in Cell 11 works for **both OpenAI and Groq** without changes.  
# The gateway absorbs the provider differences.

# In[26]:


# ─────────────────────────────────────────────────────────────────
# CELL 12: Same tool call but using Groq variant
# Shows that tool-handling code is identical across providers
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway
import json

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:

    # Force Groq variant by name
    result = client.inference(
        function_name="tool_assistant",
        variant_name="groq_variant",     # explicitly pick Groq
        input={"messages": [
            {"role": "user", "content": "What is 347 multiplied by 28?"}
        ]}
    )

    print(f"Provider: Groq (variant={result.variant_name})")
    print()

    for block in result.content:
        if hasattr(block, 'name'):
            args = block.arguments if isinstance(block.arguments, dict) else json.loads(block.arguments)
            tool_output = execute_tool(block.name, args)
            print(f"Tool called:  {block.name}")
            print(f"Arguments:    {args}")
            print(f"Result:       {tool_output}")
            print()
            print("Same ToolCallBlock structure as OpenAI.")
            print("execute_tool() works without any changes.")


# In[ ]:




