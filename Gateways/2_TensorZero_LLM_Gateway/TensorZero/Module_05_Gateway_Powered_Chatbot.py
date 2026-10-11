#!/usr/bin/env python
# coding: utf-8

# # Module 5 -- Building a Gateway-Powered Chatbot
# ### *Every gateway feature from this course, working together in one real app*
# 
# ---
# 
# **Course:** TensorZero LLM Gateways -- Basic to Advanced  
# **Module:** 5 of 5 (Capstone)  
# **Difficulty:** Intermediate  
# **Prerequisites:** Modules 1-4 complete, Docker stack running  
# **Time:** ~45 minutes  
# 
# ---

# ## What We Are Building
# 
# A **customer support chatbot** for a fictional company called *TechLearn Academy*.  
# The chatbot is a real Gradio web app running at `http://localhost:7860`.
# 
# What makes it special is NOT the chatbot itself -- it is what runs underneath:
# 
# ```
# User types message
#         |
#         v
#    Gradio UI (Python)
#         |
#         v
#    TensorZero Gateway  <-- ALL the intelligence is here
#         |                   - System prompt from config file
#         |                   - Episode locking (same model per conversation)
#         |                   - A/B routing (GPT vs Groq)
#         |                   - Feedback stored in Postgres
#         |                   - Full observability in UI
#         |
#    OpenAI / Groq API
# ```
# 
# The Python application code has **zero prompt strings**, **zero model names**,  
# **zero retry logic**, and **zero provider-specific code**.  
# Everything is handled by the gateway.
# 
# ---
# 
# ## Gateway Features Demonstrated
# 
# | Feature | Module Learned | How It Shows in the App |
# |---------|---------------|------------------------|
# | System prompt in config | Module 3 | Chatbot persona set in `.minijinja`, not code |
# | Episode locking | Module 4 | Same model used for entire conversation |
# | Provider routing | Module 2 | Auto A/B or force GPT/Groq via dropdown |
# | Feedback API | Module 4 | Thumbs up/down sends real feedback |
# | Observability | Module 1 | Link to `localhost:4000` shows every message |
# | OpenAI SDK compat | Module 1 | App works with TZ native client, zero raw API calls |
# 
# ---

# In[1]:


# ─────────────────────────────────────────────────────────────────
# CELL 1: Setup and install dependencies
# ─────────────────────────────────────────────────────────────────
import subprocess, sys, time, urllib.request
from pathlib import Path

project_dir = Path("tensorzero-demo")
config_dir  = project_dir / "config"

assert (project_dir / "docker-compose.yml").exists(), "Run Module 1 first!"

GATEWAY_URL = "http://localhost:3000"

# Install gradio if not present
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "gradio"],
               capture_output=True)
print("gradio installed.")

def restart_gateway():
    subprocess.run(["docker", "compose", "restart", "gateway"],
                   cwd=str(project_dir.resolve()), capture_output=True)
    for _ in range(20):
        try:
            urllib.request.urlopen(f"{GATEWAY_URL}/health", timeout=2)
            print("Gateway healthy.")
            return
        except Exception:
            time.sleep(1)
    print("Gateway did not come up.")

print("Setup complete.")


# ---
# ## Step 1 -- Configure the Gateway
# 
# The chatbot's personality, routing, and metrics are all configured in `tensorzero.toml`.  
# The Python app never sees any of this -- it just calls `client.inference(function_name="support_chat")`.
# 
# ### The `support_chat` function:
# - Two variants: `gpt_variant` (OpenAI) and `groq_variant` (Groq)
# - System prompt from `support_system.minijinja`
# - Feedback metric: `user_satisfied` (boolean)
# 
# ### The system prompt:
# Lives in `config/support_system.minijinja`.  
# To change the chatbot's personality, edit this file and restart the gateway.  
# **Zero Python code changes.**

# In[2]:


# ─────────────────────────────────────────────────────────────────
# CELL 2: Write system prompt and tensorzero.toml
# ─────────────────────────────────────────────────────────────────

# The chatbot's entire persona lives here -- not in Python code
support_system_prompt = """\
You are Maya, a friendly and knowledgeable support assistant for TechLearn Academy,
an online platform offering courses in AI, data science, and software engineering.

Your role:
- Help students with course-related questions
- Assist with technical issues on the platform
- Provide guidance on learning paths
- Handle billing and enrollment queries

Guidelines:
- Be warm, concise, and professional
- If you do not know something, say so honestly
- Keep responses under 3 sentences unless more detail is needed
- Always end with an offer to help further if needed
"""

(config_dir / "support_system.minijinja").write_text(
    support_system_prompt, encoding="utf-8"
)
print("Written: config/support_system.minijinja")

tensorzero_toml = """\
# ================================================================
# tensorzero.toml -- Module 5: Gateway-Powered Chatbot
# ================================================================


# ── Feedback metric ─────────────────────────────────────────────

[metrics.user_satisfied]
type     = "boolean"
level    = "inference"
optimize = "max"


# ── support_chat function ────────────────────────────────────────
# This is what the chatbot calls.
# System prompt = support_system.minijinja (not in Python code).
# Two variants for A/B testing GPT vs Groq.

[functions.support_chat]
type = "chat"

[functions.support_chat.variants.gpt_variant]
type            = "chat_completion"
model           = "openai::gpt-4o-mini"
system_template = "support_system.minijinja"
weight          = 0.5

[functions.support_chat.variants.groq_variant]
type            = "chat_completion"
model           = "groq::llama-3.3-70b-versatile"
system_template = "support_system.minijinja"
weight          = 0.5
"""

(config_dir / "tensorzero.toml").write_text(tensorzero_toml, encoding="utf-8")
print("Written: config/tensorzero.toml")

restart_gateway()
print()
print("Gateway configured for chatbot.")
print("  Function: support_chat")
print("  Variants: gpt_variant (50%) + groq_variant (50%)")
print("  Metric:   user_satisfied (boolean)")


# ---
# ## Step 2 -- The Application Logic
# 
# The core of the chatbot is just two gateway calls:
# 
# ```python
# # Send a message
# result = client.inference(
#     function_name="support_chat",
#     input={"messages": conversation_history},
#     episode_id=episode_id,          # locks variant for the whole conversation
#     variant_name=forced_variant      # optional: force a specific model
# )
# 
# # Send feedback
# client.feedback(
#     inference_id=last_inference_id,
#     metric_name="user_satisfied",
#     value=True  # or False
# )
# ```
# 
# That is the **entire business logic**. No model names. No API keys. No prompt strings.  
# Everything else is handled by the TensorZero gateway.

# In[3]:


# ─────────────────────────────────────────────────────────────────
# CELL 3: Core chatbot logic (gateway calls only)
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway

_gateway_client = None

def get_client():
    global _gateway_client
    if _gateway_client is None:
        _gateway_client = TensorZeroGateway.build_http(gateway_url=GATEWAY_URL)
    return _gateway_client


def send_message(user_message, history, episode_id, last_inference_id, model_choice):
    # history is a list of {"role": ..., "content": ...} dicts (new Gradio format)
    # Build TensorZero messages from history
    messages = [{"role": msg["role"], "content": msg["content"]} for msg in history]
    messages.append({"role": "user", "content": user_message})

    # Determine forced variant
    variant_name = None
    if model_choice == "Force GPT-4o-mini":
        variant_name = "gpt_variant"
    elif model_choice == "Force Groq Llama":
        variant_name = "groq_variant"

    kwargs = {
        "function_name": "support_chat",
        "input": {"messages": messages}
    }
    if episode_id:
        kwargs["episode_id"] = episode_id
    if variant_name:
        kwargs["variant_name"] = variant_name

    result = get_client().inference(**kwargs)

    response_text   = result.content[0].text
    new_episode_id  = result.episode_id
    new_inference_id = result.inference_id
    used_variant    = result.variant_name

    # New Gradio format: list of {"role", "content"} dicts
    new_history = history + [
        {"role": "user",      "content": user_message},
        {"role": "assistant", "content": response_text}
    ]

    model_label = "GPT-4o-mini" if used_variant == "gpt_variant" else "Groq Llama-3.3-70B"
    info = (
        f"Model:        {model_label}\n"
        f"Variant:      {used_variant}\n"
        f"Episode ID:   {str(new_episode_id)[:16]}...\n"
        f"Inference ID: {str(new_inference_id)[:16]}...\n\n"
        f"Turns in this session: {len(new_history) // 2}\n"
        f"All turns locked to same variant via episode_id"
    )

    return new_history, new_episode_id, new_inference_id, info


def send_feedback(last_inference_id, is_positive):
    if not last_inference_id:
        return "No inference to rate yet."
    fb = get_client().feedback(
        inference_id=last_inference_id,
        metric_name="user_satisfied",
        value=is_positive
    )
    emoji = "👍" if is_positive else "👎"
    return f"{emoji} Feedback sent! feedback_id: {str(fb.feedback_id)[:16]}..."


def new_conversation():
    return [], None, None, "Start a new conversation above."


print("Chatbot logic defined.")
print("  send_message()     -- calls TensorZero gateway")
print("  send_feedback()    -- sends thumbs up/down to gateway")
print("  new_conversation() -- resets episode")


# ---
# ## Step 3 -- The Gradio UI
# 
# Gradio wraps the logic into a web interface running at `http://localhost:7860`.
# 
# The UI has three panels:
# 
# ```
# ┌─────────────────────────────────────────────────────────┐
# │  TechLearn Academy Support Bot                          │
# │  Powered by TensorZero Gateway                          │
# ├─────────────────────────────┬───────────────────────────┤
# │                             │  GATEWAY INFO             │
# │   CHAT PANEL                │  Model: GPT-4o-mini       │
# │                             │  Variant: gpt_variant     │
# │   User: Hello               │  Episode: abc123...       │
# │   Maya: Hi! How can I help? │  Inference: xyz789...     │
# │                             │  Turns: 1                 │
# │                             ├───────────────────────────┤
# │                             │  Model Selector           │
# │                             │  [Auto A/B  ▼]           │
# │                             ├───────────────────────────┤
# │                             │  Rate last response:      │
# │                             │  [👍 Good] [👎 Bad]       │
# │                             │  feedback_id: def456...   │
# ├─────────────────────────────┴───────────────────────────┤
# │  [Type your message here...]               [Send]       │
# │                              [New Conversation]         │
# └─────────────────────────────────────────────────────────┘
# ```

# In[4]:


# Kill any existing Gradio server on ports 7860-7862
import socket, subprocess, sys

for port in [7860, 7861, 7862]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) == 0:
                subprocess.run(
                    [sys.executable, "-c",
                     f"import requests; requests.get('http://localhost:{port}/close_app')"],
                    capture_output=True, timeout=3
                )
    except Exception:
        pass

import gradio as gr
gr.close_all()
print("All Gradio servers closed.")


# In[5]:


# ─────────────────────────────────────────────────────────────────
# CELL 4: Build and launch the Gradio UI
# Visit http://localhost:7861 after running this cell.
# ─────────────────────────────────────────────────────────────────
import gradio as gr

with gr.Blocks(title="TechLearn Support Bot") as demo:

    gr.Markdown("""
    # TechLearn Academy Support Bot
    ### Powered by TensorZero LLM Gateway
    This chatbot demonstrates all LLM gateway features from the course working together.
    """)

    episode_id_state     = gr.State(None)
    last_inference_state = gr.State(None)

    with gr.Row():

        with gr.Column(scale=3):
            chatbot = gr.Chatbot(
                label="Maya -- TechLearn Support",
                height=450
            )

            with gr.Row():
                user_input = gr.Textbox(
                    placeholder="Ask about courses, technical issues, billing...",
                    label="Your message",
                    lines=1,
                    scale=4
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)

            new_chat_btn = gr.Button("New Conversation", variant="secondary", size="sm")

        with gr.Column(scale=2):

            gr.Markdown("### Gateway Info")
            info_box = gr.Textbox(
                value="Start a new conversation above.",
                label="TensorZero Gateway Status",
                lines=7,
                interactive=False
            )

            gr.Markdown("### Model Selector")
            gr.Markdown(
                "*Auto A/B* lets the gateway split traffic 50/50.  \n"
                "Force options lock to a specific provider."
            )
            model_selector = gr.Dropdown(
                choices=["Auto A/B (50/50)", "Force GPT-4o-mini", "Force Groq Llama"],
                value="Auto A/B (50/50)",
                label="Model Routing",
                interactive=True
            )

            gr.Markdown("### Rate Last Response")
            gr.Markdown("*Sends real feedback to TensorZero via the feedback API.*")

            with gr.Row():
                thumbs_up_btn   = gr.Button("👍  Good response", variant="primary", scale=1)
                thumbs_down_btn = gr.Button("👎  Bad response",  variant="stop",    scale=1)

            feedback_status = gr.Textbox(
                value="",
                label="Feedback Status",
                lines=1,
                interactive=False
            )

            gr.Markdown("""
            ### Observability
            **[Open TensorZero UI](http://localhost:4000)**
            """)

    def handle_send(user_msg, history, episode_id, last_inf_id, model_choice):
        if not user_msg.strip():
            return history, episode_id, last_inf_id, "", ""
        new_hist, new_ep, new_inf, info = send_message(
            user_msg, history, episode_id, last_inf_id, model_choice
        )
        return new_hist, new_ep, new_inf, "", info

    send_btn.click(
        fn=handle_send,
        inputs=[user_input, chatbot, episode_id_state, last_inference_state, model_selector],
        outputs=[chatbot, episode_id_state, last_inference_state, user_input, info_box]
    )

    user_input.submit(
        fn=handle_send,
        inputs=[user_input, chatbot, episode_id_state, last_inference_state, model_selector],
        outputs=[chatbot, episode_id_state, last_inference_state, user_input, info_box]
    )

    thumbs_up_btn.click(
        fn=lambda x: send_feedback(x, True),
        inputs=[last_inference_state],
        outputs=[feedback_status]
    )

    thumbs_down_btn.click(
        fn=lambda x: send_feedback(x, False),
        inputs=[last_inference_state],
        outputs=[feedback_status]
    )

    new_chat_btn.click(
        fn=new_conversation,
        inputs=[],
        outputs=[chatbot, episode_id_state, last_inference_state, info_box]
    )

print("Launching chatbot...")
print("Open: http://localhost:7861")
print("TensorZero UI: http://localhost:4000")
print()
print("To stop: click the stop button on this cell.")

demo.launch(server_port=7861, share=False, quiet=True)


# ---
# ## Step 4 -- Testing the Gateway Features
# 
# Open `http://localhost:7860` and try these scenarios:
# 
# ### Test 1: Episode Locking (Module 4 concept)
# ```
# 1. Send a message with "Auto A/B" selected
# 2. Note the Variant in the info panel (gpt_variant or groq_variant)
# 3. Send 3 more messages in the same conversation
# 4. Observe: ALL messages use the SAME variant
# 5. Click "New Conversation"
# 6. Send a message -- may get a different variant this time
# ```
# 
# ### Test 2: Forced Variant (Module 2 concept)
# ```
# 1. Change dropdown to "Force GPT-4o-mini"
# 2. Send a message -- info panel shows gpt_variant
# 3. Change to "Force Groq Llama"
# 4. Start a NEW conversation and send a message
# 5. Info panel shows groq_variant
# Note: changing model mid-conversation does NOT work (episode lock)
# ```
# 
# ### Test 3: Feedback API (Module 4 concept)
# ```
# 1. Send a message, read the response
# 2. Click 👍 if it was good -- see feedback_id in status
# 3. Open http://localhost:4000 -- see feedback stored
# 4. Send another message, click 👎
# 5. Compare both in the TensorZero UI
# ```
# 
# ### Test 4: Prompt Change Without Code Change (Module 3 concept)
# ```
# 1. Stop the chatbot cell (click Stop)
# 2. Edit tensorzero-demo/config/support_system.minijinja
#    (change Maya's name or personality)
# 3. Run Cell 2 again (restart gateway)
# 4. Run Cell 4 again (relaunch chatbot)
# 5. Chat -- completely different persona, zero Python code change
# ```
# 
# ### Test 5: Observability (Module 1 concept)
# ```
# 1. Open http://localhost:4000
# 2. Go to Inferences -- see every message logged
# 3. Go to Episodes -- see full conversations grouped
# 4. Each entry shows: model used, latency, tokens, cost
# ```

# 
