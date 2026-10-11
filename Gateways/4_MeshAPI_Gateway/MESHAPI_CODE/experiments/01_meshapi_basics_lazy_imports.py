#!/usr/bin/env python
# coding: utf-8

# # MeshAPI Gateway Basics (bare minimum)
# 
# The absolute minimum needed to start talking to **MeshAPI** (`https://api.meshapi.ai`) -- an AI
# model gateway: one API key, one OpenAI-shaped API, many providers behind it.
# 
# This notebook only covers five things:
# 1. Opening a client
# 2. Seeing what models you actually have access to
# 3. One basic chat completion
# 4. Checking what that call cost (tokens + real $)
# 5. Closing the client
# 
# That's it. Streaming, `compare`, fallback model-picking, tool calling, structured outputs, error
# handling, and every other feature are covered properly in `features_lazy_imports.ipynb` -- no need
# to repeat them here. Next up: `02_rag_multiagent_lazy_imports.ipynb` builds a real RAG + multi-agent
# app on top of exactly what this notebook teaches, then `features_lazy_imports.ipynb` tours
# everything else.

# ## 1. Install

# In[1]:


get_ipython().run_line_magic('pip', 'install -q meshapi python-dotenv')


# ## 2. Open a client
# 
# The SDK does **not** auto-read env vars -- you pass `base_url` and `token` explicitly. Get your
# `rsk_...` key from the MeshAPI dashboard.

# In[2]:


import os
from getpass import getpass

from dotenv import load_dotenv
load_dotenv()

from meshapi import MeshAPI

MESHAPI_TOKEN = os.getenv("MESH_API_KEY") or getpass("MeshAPI token (rsk_...): ")
client = MeshAPI(base_url=os.getenv("MESHAPI_BASE_URL", "https://api.meshapi.ai"), token=MESHAPI_TOKEN)
print("Client ready.")


# ## 3. See what models you actually have
# 
# `client.models.list()` returns the full live catalog behind this one key. We're just looking here,
# not picking yet -- the fallback-picking logic (`pick_model()`) is covered in `02`/`features`, since
# that's a bit more than "bare minimum."

# In[3]:


ALL_MODELS = {m.id: m for m in client.models.list()}
print(f"{len(ALL_MODELS)} models available through this key.")


# In[4]:


# Peek at one full entry to see the shape of a model object -- pricing, capabilities, etc.
ALL_MODELS_BY_NAME = {m.name: m for m in ALL_MODELS.values()}
ALL_MODELS_BY_NAME[list(ALL_MODELS_BY_NAME.keys())[0]]


# ## 4. A basic chat completion
# 
# One call: a `model` string, a list of messages, get a reply back. `model` is a `"provider/model"`
# string -- swap it for any other provider MeshAPI supports and this exact code still works. That's
# the entire pitch of a gateway.
# 
# (The fallback-picking logic for handling a model that might not exist is covered in
# `02_rag_multiagent_lazy_imports.ipynb` and `features_lazy_imports.ipynb` -- kept out of this
# notebook on purpose.)

# In[5]:


from meshapi import ChatCompletionParams, ChatMessage

resp = client.chat.completions.create(
    ChatCompletionParams(
        model="openai/gpt-4o-mini",
        messages=[ChatMessage(role="user", content="In one sentence, what is an AI gateway?")],
        max_tokens=60,
    )
)
print(resp.choices[0].message.content)


# ## 5. Check what that call actually cost
# 
# Every response includes `usage` -- exactly how many tokens the call spent. Combine that with the
# model's published pricing (one lookup, `client.models.get(...)`, no need to fetch the whole catalog
# for this) and you can print the real cost of any call, any time after it finishes.

# In[6]:


usage = resp.usage
print(f"tokens used -- prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens}, total: {usage.total_tokens}")

pricing = client.models.get("openai/gpt-4o-mini").pricing
cost_usd = (usage.prompt_tokens * float(pricing.prompt_usd_per_1m) + usage.completion_tokens * float(pricing.completion_usd_per_1m)) / 1_000_000
print(f"estimated cost of this call: ${cost_usd:.6f}")


# ## 6. Close the client

# In[7]:


client.close()
print("Done. Next: open 02_rag_multiagent_lazy_imports.ipynb")

