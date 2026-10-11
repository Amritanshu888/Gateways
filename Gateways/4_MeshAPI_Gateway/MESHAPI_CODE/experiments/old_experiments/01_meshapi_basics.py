#!/usr/bin/env python
# coding: utf-8

# # MeshAPI Gateway Basics
# 
# This notebook is a teaching intro to **MeshAPI** (`https://api.meshapi.ai`), an AI model gateway:
# one API key, one OpenAI-shaped API, many providers behind it addressed as `provider/model` strings.
# 
# We'll route to two different providers through the *same* gateway client — which two doesn't matter,
# the point is that swapping providers is a one-line change:
# - `FAST_MODEL` — a cheap/fast model for quick calls and streaming
# - `SMART_MODEL` — a stronger model for higher-quality answers
# 
# What this notebook covers:
# 1. Client setup + auth
# 2. Discovering live model IDs (and why the `provider=` filter can't be trusted blindly)
# 3. A basic chat completion, run against both providers with zero code changes
# 4. Streaming
# 5. `compare` — run the same prompt across multiple providers at once
# 6. Error handling
# 
# The companion notebook `02_rag_multiagent.ipynb` builds a RAG + multi-agent workflow on top of this.

# ## 1. Install

# In[ ]:


get_ipython().run_line_magic('pip', 'install -q meshapi python-dotenv')


# ## 2. Config & client
# 
# The SDK does **not** auto-read env vars — you pass `base_url` and `token` explicitly.
# Get your `rsk_...` key from the MeshAPI dashboard.

# In[ ]:


import os, json

from getpass import getpass

from dotenv import load_dotenv

load_dotenv()



from meshapi import (

    MeshAPI, ChatCompletionParams, ChatMessage,

    MeshAPIError,

    CompareParams,

)



MESHAPI_BASE_URL = os.getenv("MESHAPI_BASE_URL", "https://api.meshapi.ai")

MESHAPI_TOKEN = os.getenv("MESH_API_KEY") or os.getenv("MESHAPI_TOKEN") or getpass("MeshAPI token (rsk_...): ")



client = MeshAPI(base_url=MESHAPI_BASE_URL, token=MESHAPI_TOKEN)

print("Client ready.")


# ## 3. Helper: pretty-print any SDK response
# 
# SDK responses are Pydantic v2 models, so `model_dump_json()` always works even if you're
# not sure of the exact field names yet — handy while exploring.

# In[ ]:


def show(obj, indent=2):

    if hasattr(obj, "model_dump_json"):

        print(obj.model_dump_json(indent=indent))

    else:

        print(json.dumps(obj, indent=indent, default=str))


# ## 4. Pick two models through the gateway
# 
# **Note on the `provider=` filter:** `client.models.list(provider="...")` looks like it should filter
# by provider, but in practice most catalog entries have `provider: null` server-side (only a few
# first-party-labeled models populate it) — so that filter silently returns an empty list for most
# providers, including ones that definitely have models (e.g. Mistral). We fetch the **full** catalog
# once and filter client-side instead, which is reliable.
# 
# We also don't hardcode a model purely on faith — we verify live that our preferred pick still exists
# and actually supports tool calling (needed for the agent sections later).

# In[ ]:


ALL_MODELS = {m.id: m for m in client.models.list()}

print(f"{len(ALL_MODELS)} models available through this key.")



def pick_model(preferred_id, fallback_prefix, require_tools=True):

    """Use preferred_id if it's live and capable; otherwise fall back to the first

    tool-capable model under fallback_prefix (e.g. 'openai/', 'mistralai/')."""

    m = ALL_MODELS.get(preferred_id)

    if m and (not require_tools or m.supports_tools):

        return preferred_id

    for mid, m in ALL_MODELS.items():

        if mid.startswith(fallback_prefix) and (not require_tools or m.supports_tools):

            print(f"'{preferred_id}' unavailable -- falling back to '{mid}'")

            return mid

    raise RuntimeError(f"No suitable model found for {preferred_id} (fallback prefix {fallback_prefix!r})")



# Two different providers behind the same gateway -- swap either string and everything else still works.

FAST_MODEL = pick_model("openai/gpt-4o-mini", fallback_prefix="openai/")

SMART_MODEL = pick_model("mistral/mistral-large-3-675b-instruct", fallback_prefix="mistral/")



print("FAST_MODEL  =", FAST_MODEL)

print("SMART_MODEL =", SMART_MODEL)


# ## 5. A basic chat completion
# 
# Same function, same code path — only the `model=` string changes between providers.
# That's the entire pitch of a gateway.

# In[ ]:


def ask(model, prompt, temperature=0.5, max_tokens=300):

    resp = client.chat.completions.create(

        ChatCompletionParams(

            model=model,

            messages=[ChatMessage(role="user", content=prompt)],

            temperature=temperature,

            max_tokens=max_tokens,

        )

    )

    return resp.choices[0].message.content



question = "In two sentences, what makes an AI model gateway useful for a startup?"



print(f"=== {FAST_MODEL} ===")

print(ask(FAST_MODEL, question))



print(f"\n=== {SMART_MODEL} ===")

print(ask(SMART_MODEL, question))


# ## 6. Streaming

# In[ ]:


print(f"Streaming from {FAST_MODEL}:\n")



stream = client.chat.completions.stream(

    ChatCompletionParams(

        model=FAST_MODEL,

        messages=[ChatMessage(role="user", content="Count from 1 to 5, one number per line, with a short fun fact about each number.")],

    )

)



for chunk in stream:

    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:

        print(chunk.choices[0].delta.content, end="", flush=True)


# ## 7. `compare` — same prompt, multiple providers at once
# 
# `client.compare` fans a single prompt out to several models in one call, optionally with an
# LLM-generated synthesis step. Great for "which provider should I use for this task" demos.

# In[ ]:


result = client.compare.create(

    CompareParams(

        models=[FAST_MODEL, SMART_MODEL],

        messages=[ChatMessage(role="user", content="What's the single biggest tradeoff of using an AI gateway vs calling providers directly?")],

    )

)



# Inspect the raw shape first — compare responses vary slightly by SDK version.

show(result)


# ### Streaming variant of compare
# 
# If you'd rather watch both models answer token-by-token, use `.stream()` instead of `.create()`.
# Print the raw event once to see the exact shape your installed SDK version returns, then adapt.

# In[ ]:


for event in client.compare.stream(

    CompareParams(

        models=[FAST_MODEL, SMART_MODEL],

        messages=[ChatMessage(role="user", content="Name one good use case for a fast/cheap model vs a slow/powerful one.")],

    )

):

    print(event)


# ## 8. Error handling
# 
# `MeshAPIError` carries structured fields — `status`, `error_code`, `request_id`, `retry_after_seconds` —
# so you can branch on things like rate limits or spend caps instead of parsing strings.

# In[ ]:


try:

    client.chat.completions.create(

        ChatCompletionParams(model="not-a-real-provider/not-a-real-model", messages=[ChatMessage(role="user", content="hi")])

    )

except MeshAPIError as e:

    print(f"[{e.status}] {e.error_code}: {e}")

    print("request_id:", e.request_id)

    if e.error_code == "rate_limit_exceeded":

        print("retry after:", e.retry_after_seconds, "seconds")


# ## 9. Cleanup

# In[ ]:


client.close()

print("Done. Next: open 02_rag_multiagent.ipynb")

