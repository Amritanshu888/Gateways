#!/usr/bin/env python
# coding: utf-8

# # Bifrost Getting Started — Groq + Mistral + Jina + Qdrant Cloud
# 
# ### A free-tier, self-hosted AI gateway walkthrough
# 
# ---
# 
# **Purpose:** Get hands-on with [Bifrost](https://github.com/maximhq/bifrost) (self-hosted, open-source AI
# gateway by Maxim AI) using only providers with usable free tiers:
# 
# - **Groq** — chat/completions (LPU inference, very fast, generous free tier)
# - **Mistral** — chat/completions (La Plateforme free tier)
# - **Jina AI** — embeddings (used only in the RAG section, called directly — not via Bifrost)
# - **Qdrant Cloud** — vector store (managed, used only in the RAG section)
# 
# **Your setup:** a single, already-created Docker container named `bifrost`, started with
# `docker start bifrost` and nothing else. Everything Bifrost-side is configured through its
# **Web UI** at `http://localhost:8080`, which persists inside that container across restarts.
# 
# **What you'll cover:**
# 1. Baseline: vanilla Groq/Mistral SDKs (no gateway)
# 2. Bifrost setup via the Web UI & a drop-in client
# 3. Bifrost feature showcase: unified API, failover, load balancing, streaming, observability, virtual keys, MCP
# 4. A small RAG pipeline built by hand (Jina embeddings + Qdrant Cloud + Bifrost generation)
# 
# **Prerequisites:**
# 1. Python 3.10+ and packages from `requirements.txt` (`pip install -r requirements.txt`)
# 2. `.env` filled in — `GROQ_API_KEY`, `MISTRAL_API_KEY` required from Section 1 onward; `JINA_API_KEY`,
#    `QDRANT_URL`, and `QDRANT_API_KEY` required only for Section 4
# 3. `docker start bifrost` — that's it, nothing else to run
# 4. Groq + Mistral added as providers in the Bifrost Web UI (Section 2.2 walks through this)
# 
# **A note on style:** every code cell here does one small thing. Where the same handful of lines
# would otherwise repeat across features (timing a call, reading which provider answered), there's
# one small helper function instead — defined once, reused everywhere. Full term definitions live
# in [`docs/00-terminologies.md`](docs/00-terminologies.md).
# 
# ---
# 

# ---
# <a id="section-0"></a>
# ## Section 0: Environment Setup & Prerequisites
# 

# LOAD YOUR ENV VARS

# In[89]:


from dotenv import load_dotenv
import os

load_dotenv()


# In[87]:


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
BIFROST_BASE_URL = os.getenv("BIFROST_BASE_URL", "http://localhost:8080")
BIFROST_GROQ_VIRTUAL_KEY = os.getenv("BIFROST_GROQ_VIRTUAL_KEY", "")
BIFROST_MISTRAL_VIRTUAL_KEY = os.getenv("BIFROST_MISTRAL_VIRTUAL_KEY", "")

print("Keys loaded. Bifrost base URL:", BIFROST_BASE_URL)


# ### 0.3 Bifrost Health Check
# 
# A quick check that the `bifrost` container is actually up before anything else tries to call it.
# 

# In[54]:


import httpx 

try : 
    health = httpx.get(f"{BIFROST_BASE_URL}/health" , timeout = 3)
    bifrost_ok = health.status_code == 200
except Exception:
    bifrost_ok = False
    
print("Bifrost:", "Online" if bifrost_ok else "Offline")

if not bifrost_ok:
    print("Start it with: docker start bifrost")    
    


# ### 0.4 Prompts We'll Reuse
# 
# One set of prompts, used throughout the notebook, so the vanilla SDKs, Bifrost, and the RAG
# section are all answering the same questions.
# 

# In[55]:


TEST_PROMPTS = {
    "simple": "What is the capital of France?",
    "reasoning": "Explain the difference between RAG and fine-tuning in 3 bullet points.",
    "code": "Write a Python function that validates an email address using regex.",
    "duplicate1": "What is LangChain used for?",
    "duplicate2": "What is LangChain primarily used for?",
    "deepwiki": "What are the stream modes in the new langgraph version? Use the deepwiki tool to check the langchain-ai/langgraph repo.",
    "tavily": "Search the web for the latest news about Groq AI and summarize the top result.",
}


# ### 0.5 Models We'll Use
# 
# Groq is retiring `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` on 2026-08-16 (free tier),
# so this notebook uses their recommended replacements instead. Mistral's `-latest` aliases always
# point at the current model, so they need no such swap.
# 
# `openai/gpt-oss-120b` is OpenAI's *open-weight* model, served on Groq's own hardware — it runs on
# `GROQ_API_KEY`, not an OpenAI key. Nothing here touches your OpenAI account.
# 

# In[56]:


import time 


# GROQ MODELS 

GROQ_MODEL = "openai/gpt-oss-120b"            # capable — replaces llama-3.3-70b-versatile
GROQ_MODEL_FALLBACK = "openai/gpt-oss-20b"    # fast/cheap — replaces llama-3.1-8b-instant

# MISTRAL MODELS 

MISTRAL_MODEL = "mistral-large-latest"
MISTRAL_MODEL_FALLBACK = "mistral-small-latest"

print("Groq:", GROQ_MODEL, "| fallback:", GROQ_MODEL_FALLBACK)
print("Mistral:", MISTRAL_MODEL, "| fallback:", MISTRAL_MODEL_FALLBACK)


# ---
# <a id="section-1"></a>
# ## Section 1: Baseline — Vanilla Groq & Mistral SDKs
# 
# > **Goal:** show what you have to write yourself WITHOUT a gateway — two separate SDKs, two
# > separate error-handling paths, no shared observability.
# 

# In[57]:


from groq import Groq 

client_groq= Groq(api_key=GROQ_API_KEY)


# In[58]:


start = time.perf_counter()
response = client_groq.chat.completions.create(
    model = GROQ_MODEL,
    messages=[
        {
            "role":"user",
            "content" : TEST_PROMPTS["simple"]
        }
    ]
)
latency_ms = (time.perf_counter() - start) * 1000

print(response.choices[0].message.content)
print(f"\n{latency_ms:.0f} ms, {response.usage.total_tokens} tokens")



# In[59]:


from mistralai.client import Mistral

client_mistral = Mistral(api_key=MISTRAL_API_KEY)


start = time.perf_counter()
response = client_mistral.chat.complete(
    model=MISTRAL_MODEL,
    messages=[{"role": "user", "content": TEST_PROMPTS["reasoning"]}],
)
latency_ms = (time.perf_counter() - start) * 1000

print(response.choices[0].message.content)
print(f"\n{latency_ms:.0f} ms, {response.usage.total_tokens} tokens")


# ### 1.3 Vanilla Streaming — Groq
# 
# For chat UIs that render tokens as they arrive, instead of waiting for the full response. Shown
# here on the raw SDK so Section 3.4 can show the same thing through Bifrost.
# 

# In[60]:


stream = client_groq.chat.completions.create(
    model=GROQ_MODEL,
    messages=[{"role": "user", "content": TEST_PROMPTS["code"]}],
    stream=True,
)

for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end ="" , flush=True)
print()


# ### 1.4 What's Missing Without a Gateway
# 
# | Problem                   | Vanilla Groq SDK | Vanilla Mistral SDK |
# |---------------------------|-------------------|-----------------------|
# | Automatic failover        | Manual            | Manual                |
# | Multi-provider routing    | Not possible      | Not possible           |
# | Unified request/response  | Per-SDK           | Per-SDK                |
# | Rate limit handling       | Manual retry      | Manual retry           |
# | Observability / tracing   | External only     | External only          |
# | Budget enforcement        | Not possible      | Not possible            |
# | MCP tool governance        | Not possible      | Not possible            |
# | Streaming normalization   | Per-provider       | Per-provider            |
# 

# ### 1.5 Manual Fallback — What You'd Have to Write Yourself
# 
# The fallback logic teams end up hand-writing without a gateway: try Groq, and if it fails, retry
# on Mistral. Section 3.2 replaces this whole function with a single HTTP header.
# 

# In[61]:


def naive_manual_fallback(prompt:str) -> str:
    try:
        response = client_groq.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as groq_error:
        print("GROQ FAILED , trying mistral as backup:" , groq_error)
        response = client_mistral.chat.complete(
            model=MISTRAL_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content


# In[62]:


answer = naive_manual_fallback(TEST_PROMPTS["simple"])
print(answer)


# ---
# <a id="section-2"></a>
# ## Section 2: Bifrost Setup & Architecture
# 
# > **Bifrost** is a Go-based, open-source AI gateway. It provides failover, load balancing,
# > virtual keys, an MCP gateway, and observability — all via a single self-hosted container.
# 

# ### 2.1 Your Bifrost Container
# 
# You already have a container named `bifrost`. The full lifecycle for this notebook is just:
# 
# ```bash
# docker start bifrost   # bring it up
# docker stop bifrost    # shut it down when you're done
# ```
# 
# No `docker run`, no `docker-compose`, no extra containers. Bifrost persists whatever you
# configure through its Web UI **inside that same container**, so it survives stop/start cycles.
# 
# **Do you need a Bifrost API key?** No. Bifrost doesn't require its own credential for incoming
# requests by default — that's Virtual Keys (Section 3.6), an optional layer you can turn on later.
# The client below is the *unscoped* drop-in client: it needs to reach both Groq and Mistral, so it
# uses a placeholder instead of a virtual key (a virtual key is scoped to whatever provider it was
# created for — Section 3.6 uses `BIFROST_GROQ_VIRTUAL_KEY` and `BIFROST_MISTRAL_VIRTUAL_KEY`
# directly, one client per provider).
# 

# ### 2.2 Add Groq & Mistral as Providers (Web UI)
# 
# 1. Open `http://localhost:8080`
# 2. Go to **Providers** → **Add Provider**
# 3. Provider = `groq`, paste your actual `GROQ_API_KEY` value directly into the key field
# 4. Repeat for provider = `mistral` with your `MISTRAL_API_KEY`
# 5. (Optional, for Section 3.7) Go to **MCP Gateway → MCP Catalog** → **Add MCP Server**:
#    - `deepwiki` — connection type `HTTP (Streamable)`, URL `https://mcp.deepwiki.com/mcp`, auth `None`
#    - `tavily` — same connection type, URL `https://mcp.tavily.com/mcp/?tavilyApiKey=YOUR_TAVILY_KEY`
#      (free key from `https://app.tavily.com/home`), auth `None`
#    - **Important:** open each one and toggle **Auto-execute** on for its tools. Without this,
#      Bifrost proposes the tool call and stops — it won't actually run it.
# 

# ### 2.3 Bifrost Drop-in Client Setup
# 
# One `OpenAI` client instance now talks to every provider Bifrost knows about — which provider
# handles a call is picked by the `"<provider>/<model>"` string, not by which client you made.
# 

# In[63]:


from openai import OpenAI 

bifrost = OpenAI(
    api_key = "dont need because we have virtual keys",
    base_url = f"{BIFROST_BASE_URL}/v1"
)

print("Bifrost client ready. Pick a provider via the model string, e.g.:")
print(f"  groq/{GROQ_MODEL}")
print(f"  mistral/{MISTRAL_MODEL}")


# ---
# <a id="section-3"></a>
# ## Section 3: Bifrost Feature Showcase
# 

# ### 3.0 One Helper We'll Reuse
# 
# Every feature below calls Bifrost the same way: send a prompt, get back the answer plus *which
# provider* actually handled it. Bifrost injects that as a top-level `extra_fields` key in the raw
# JSON response — outside the normal OpenAI response schema, so we go through
# `with_raw_response` and parse the JSON ourselves to read it, rather than trust an SDK attribute
# to carry through a field it was never designed to know about.
# 

# In[64]:


import json as _json

def call_bifrost(prompt: str, model: str, fallback_model: str = None):
    headers = {"x-bifrost-fallback-models": fallback_model} if fallback_model else None

    raw = bifrost.chat.completions.with_raw_response.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        extra_headers=headers,
    )
    response = raw.parse()
    provider = _json.loads(raw.text).get("extra_fields", {}).get("provider", "unknown")
    return response.choices[0].message.content, provider


# ### 3.1 Feature 1 — Unified Drop-in API (Groq + Mistral, Same Client)
# 
# Swap providers per-request — cheap/fast Groq for simple queries, Mistral for others — without
# maintaining two SDKs or two code paths.
# 

# In[65]:


answer , provider = call_bifrost(TEST_PROMPTS["simple"] , f"groq/{GROQ_MODEL}")
print(f"[{provider}] {answer}")


# In[66]:


answer , provider = call_bifrost( "how to learn ai gateways shortcut , respond in 10 words" , f"mistral/{MISTRAL_MODEL}")
print(f"[{provider}] {answer}")


# ### 3.2 Feature 2 — Automatic Failover / Provider Fallback
# 
# Keep serving requests even if your primary provider is down or rate-limiting you. Bifrost retries
# on the fallback model automatically — your code never sees the failure. It triggers on **5xx,
# 429, and 401**; it does **not** trigger on a **404** (model not found) — that's a bug in your
# request, not an outage, so Bifrost passes the error straight through instead of masking it.
# 

# In[67]:


answer , provider = call_bifrost(
    TEST_PROMPTS["duplicate2"] , f"groq/{GROQ_MODEL}",
    fallback_model=f"mistral/{MISTRAL_MODEL}"
)
print(f"[{provider}] {answer}")


# In[68]:


# Bad model name (404) — does NOT trigger the Mistral fallback, by design
try:
    answer, provider = call_bifrost(
    TEST_PROMPTS["duplicate2"] , 
    f"groq/fake-model",
    fallback_model=f"mistral/{MISTRAL_MODEL}"
    )
    print(f"[{provider}] {answer}")
except Exception as e:
    print("No fallback triggered, as expected for a 404:", e)


# ### 3.3 Feature 3 — Weighted Load Balancing Across API Keys
# 
# Bifrost spreads traffic across multiple keys for the *same* provider, by weight, to raise your
# effective rate limit. A single request can't show that — it can only ever hit one key. So this
# fires several requests and tallies which key actually handled each one. With only one Groq key
# configured (the default here), every request will land on that same key — the distribution only
# gets interesting once you add a second key with its own weight in the Web UI.
# 

# In[31]:


from collections import Counter

# 10 - 5 , 5 

def bifrost_key_used(model: str, prompt: str = "Hello") -> str:
    response = httpx.post(
        f"{BIFROST_BASE_URL}/v1/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    return response.json().get("extra_fields", {}).get("routing_info", {}).get("key", "unknown")


# In[32]:


counts = Counter(bifrost_key_used(f"groq/{GROQ_MODEL}") for _ in range(10))
print("Requests per key (10 calls):", dict(counts))


# ### 3.4 Feature 4 — Streaming (Unified Across Providers)
# 
# Same streaming function, no `if provider == "groq"` branching — swap the model string and the
# same code streams from a different backend.
# 

# In[69]:


def stream_bifrost(prompt: str, model: str):
    stream = bifrost.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print()


# In[70]:


stream_bifrost(TEST_PROMPTS["code"], f"groq/{GROQ_MODEL}")


# In[71]:


stream_bifrost(TEST_PROMPTS["code"], f"mistral/{MISTRAL_MODEL}")


# ### 3.5 Feature 5 — Observability: Logs API
# 
# See exactly what Bifrost routed, to which provider, and how long it took — without adding any
# logging of your own. Full Prometheus `/metrics` needs a separate plugin binary (not covered
# here); this REST endpoint works out of the box.
# 

# In[72]:


import pprint

response = httpx.get(f"{BIFROST_BASE_URL}/api/logs?limit=5", timeout=5)
logs = response.json() if response.status_code == 200 else {"status": response.status_code}

pprint.pprint(logs)


# ### 3.6 Feature 6 — Virtual Keys & Budget Governance
# 
# Hand a teammate, or a specific app, a scoped key with a spending cap — instead of giving out your
# raw Groq/Mistral keys. Create one at `http://localhost:8080` → **Virtual Keys** (a separate tab
# from **Providers**) for each provider you want to govern separately. Bifrost shows you the
# generated secret once — put it in `.env` as `BIFROST_GROQ_VIRTUAL_KEY` /
# `BIFROST_MISTRAL_VIRTUAL_KEY` to try these cells. Each key only works for the provider it was
# created for, so unlike Section 2.3's client, this is one client per virtual key.
# 

# In[84]:


def call_with_virtual_key(virtual_key: str, model: str, prompt: str):
    if not virtual_key:
        print("No virtual key set for this provider — create one at http://localhost:8080 -> Virtual Keys")
        return
    client = OpenAI(api_key=virtual_key, base_url=f"{BIFROST_BASE_URL}/v1")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        print(response.choices[0].message.content)
    except Exception as e:
        print("Call failed — check the virtual key is valid and not over budget:", e)


# In[99]:


BIFROST_GROQ_VIRTUAL_KEY="sk-bf-5dba0cb8-9fbb-4be7-a1bc-2a357d56b476"
BIFROST_MISTRAL_VIRTUAL_KEY="sk-bf-c9e41e4e-b964-46ac-b106-4d17eaec505f"


# In[100]:


call_with_virtual_key(BIFROST_GROQ_VIRTUAL_KEY, f"groq/{GROQ_MODEL}", TEST_PROMPTS["simple"])


# In[102]:


call_with_virtual_key(BIFROST_MISTRAL_VIRTUAL_KEY, f"mistral/{MISTRAL_MODEL}", TEST_PROMPTS["code"])


# ### 3.7 Feature 7 — MCP Gateway (DeepWiki + Tavily)
# 
# Let the model call external tools — DeepWiki (ask questions about a GitHub repo) and Tavily (live
# web search) — through the gateway, instead of wiring tool-calling into every client app
# separately. Requires both MCP clients added with **Auto-execute** on (Section 2.2).
# 
# > **Model note:** Groq's `openai/gpt-oss-*` models fail with a 400 during Bifrost's tool-calling
# > loop (`'reasoning_content' is unsupported` — Bifrost resends the model's own reasoning trace,
# > and Groq's API rejects it for these models). So this section runs on **Mistral** instead, which
# > has no such issue.
# 

# REGISTOR MCP TO BIFROST

# In[ ]:


response = httpx.get(f"{BIFROST_BASE_URL}/api/mcp/clients", timeout=5)
response






# In[105]:


clients = response.json().get("clients", [])

clients


# In[106]:


registered = {c["config"]["name"] for c in clients}


# In[107]:


print("Registered:", registered or "none")


# In[108]:


def call_with_tools(prompt: str, servers: list[str]) -> dict:
    response = httpx.post(
        f"{BIFROST_BASE_URL}/v1/chat/completions",
        json={
            "model": f"mistral/{MISTRAL_MODEL}",
            "messages": [{"role": "user", "content": prompt}],
            "bifrost": {"mcp": {"enabled": True, "code_mode": True, "servers": servers}},
        },
        timeout=60,
    )
    return response.json()["choices"][0]["message"]


# In[109]:


# DeepWiki — ask a question about a GitHub repo
if "deepwiki" in registered:
    message = call_with_tools(TEST_PROMPTS["deepwiki"], ["deepwiki"])
    print(message.get("content") or message.get("tool_calls"))
else:
    print("Skipped — add the deepwiki MCP server first (see Section 2.2)")


# In[110]:


# Tavily — live web search
if "tavily" in registered:
    message = call_with_tools(TEST_PROMPTS["tavily"], ["tavily"])
    print(message.get("content") or message.get("tool_calls"))
else:
    print("Skipped — add the tavily MCP server first (see Section 2.2)")


# In[111]:


### ASSIGNMNETT


## SEARCH FOR YOUR MCP 


## SIMPLE AGENT - PROMPT , MCP TOOL , BIFROST 


# In[112]:


## SIMPLE MINI RAGG 


# In[ ]:





# In[ ]:





# In[ ]:





# In[ ]:





# In[ ]:





# In[ ]:





# In[ ]:





# In[ ]:





# In[ ]:





# ---
# <a id="section-4"></a>
# ## Section 4: A Small RAG Pipeline (Jina Embeddings + Qdrant Cloud + Bifrost Generation)
# 
# > Uses `langchain_qdrant.QdrantVectorStore` for storage/retrieval — the current idiomatic way to
# > wire a vector store in LangChain — with a small custom `Embeddings` class for Jina, since
# > LangChain's built-in Jina wrapper only supports an older model and has no `task` parameter
# > (the thing that actually makes Jina v3/v4 embeddings good). Generation still goes through
# > Bifrost. Deliberately skipped: chunking, a relevance-score cutoff, reranking, hybrid search —
# > real techniques, out of scope for a getting-started demo over 7 sentences.
# 

# ### 4.1 Connect to Qdrant Cloud
# 
# A managed, always-on vector store you don't have to run yourself — just a URL and an API key
# from your Qdrant Cloud cluster dashboard.
# 

# In[73]:


JINA_API_KEY = os.getenv("JINA_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")


# In[74]:


from qdrant_client import QdrantClient

try:
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    qdrant.get_collections()
except Exception:
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, port=443)


print("Connected. Existing collections:", [c.name for c in qdrant.get_collections().collections])


# ### 4.2 Jina Embeddings — as a LangChain `Embeddings` Class
# 
# Wrapping Jina's REST API in LangChain's standard `Embeddings` interface (`embed_documents` /
# `embed_query`) is what lets it plug straight into `QdrantVectorStore` below. `retrieval.passage`
# is the adapter tuned for documents you're storing; `retrieval.query` is tuned for the question
# you're searching with.
# 

# In[43]:


import requests
from langchain_core.embeddings import Embeddings

class JinaEmbeddings(Embeddings):
    def __init__(self, api_key: str, model: str = "jina-embeddings-v4"):
        self.api_key = api_key
        self.model = model

    def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        response = requests.post(
            "https://api.jina.ai/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts, "task": task},
            timeout=30,
        )
        response.raise_for_status()
        return [item["embedding"] for item in response.json()["data"]]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, task="retrieval.passage")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], task="retrieval.query")[0]

jina = JinaEmbeddings(api_key=JINA_API_KEY)


# In[44]:


JINA_DIM = len(jina.embed_query("HELLOWWWW WORLDDD"))
print("Embeddings length" , JINA_DIM)


# ### 4.3 Build a Tiny Knowledge Base in Qdrant Cloud
# 
# Seeds the vector store with a handful of reference documents so the retrieval step in 4.4 has
# something real to find. Re-running this wipes and rebuilds the demo collection.
# 

# In[76]:


from qdrant_client.models import Distance, VectorParams
from langchain_qdrant import QdrantVectorStore

COLLECTION = "bifrost_rag_demo"

DOCS = [
    "Bifrost is a Go-based, open-source AI gateway built by Maxim AI, released under Apache 2.0.",
    "Bifrost supports automatic failover across providers, triggered on 5xx errors, 429 rate limits, and 401 auth failures.",
    "Bifrost exposes a single OpenAI-compatible /v1/chat/completions endpoint; the provider is selected via a \"provider/model\" string.",
    "Groq serves LLMs on custom LPU hardware, offering very low-latency inference with a free API tier.",
    "Mistral AI offers La Plateforme with a free tier for models like mistral-large-latest and mistral-small-latest.",
    "Qdrant Cloud is a managed vector database used here for RAG retrieval, reached over a URL + API key.",
    "Jina AI provides an embeddings API (jina-embeddings-v4) with task-specific adapters for retrieval and classification.",
]

if qdrant.collection_exists(COLLECTION):
    qdrant.delete_collection(COLLECTION)
    
qdrant.create_collection(
    collection_name=COLLECTION,
    vectors_config=VectorParams(size=JINA_DIM, distance=Distance.COSINE),
)   

vectorstore = QdrantVectorStore(
    client = qdrant , 
    collection_name=COLLECTION,
    embedding=jina
)

print("COLLECTION_READY")


# In[77]:


print("COLLECTION_READY" , COLLECTION)


# In[79]:


vectorstore.add_texts(DOCS)


# In[80]:


print(f'Indexed {len(DOCS)} documents into "{COLLECTION}"')


# ### 4.4 Retrieve + Generate (Full RAG Loop, Generation via Bifrost)
# 
# The actual RAG pattern: embed the question, retrieve the closest stored facts via the
# vector store (with their similarity scores, so you can see *why* each one was picked), then ask
# an LLM — through Bifrost, using the same `call_bifrost` helper from Section 3 — to answer using
# only that retrieved context.
# 

# In[81]:


def rag_query(question: str, model: str = f"groq/{GROQ_MODEL}", top_k: int = 3) -> dict:
    hits = vectorstore.similarity_search_with_score(question, k=top_k)

    context = "\n".join(f"- {doc.page_content}" for doc, _score in hits)
    prompt = (
        "YOu are a bifrost agent.Answer the question using ONLY the context below. "
        "If the answer isn't in the context, say so.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}"
    )

    answer, provider = call_bifrost(prompt, model)
    return {"retrieved": hits, "answer": answer, "provider": provider}


# In[83]:


result = rag_query("What hardware does groq use for inference")


print("Retrieved context:")
for doc, score in result["retrieved"]:
    print(f"  [{round(score, 3)}] {doc.page_content}")


# ---
# ## Summary
# 
# | Covered | Skipped (needs paid/enterprise infra, or out of scope for a getting-started demo) |
# |---|---|
# | Vanilla Groq/Mistral SDK baseline | Guardrails (AWS Bedrock / Azure) |
# | Drop-in unified Bifrost client (Web UI configured) | Cluster mode (multi-node) |
# | Automatic failover, weighted load balancing | Secret Manager (Vault / cloud) |
# | Unified streaming, logs API | OpenTelemetry tracing (needs a collector) |
# | Virtual keys & budgets | RAG: chunking, relevance cutoff, reranking, hybrid search |
# | MCP gateway (DeepWiki + Tavily) | |
# | RAG via `QdrantVectorStore` + Jina embeddings + Bifrost generation | |
# 
# For a full breakdown of every term used above, see [`docs/00-terminologies.md`](docs/00-terminologies.md).
# For the enterprise-tier features, see [`docs/03-oss-vs-enterprise.md`](docs/03-oss-vs-enterprise.md).
# 

# ## ASSIGNMENT 
# 
# 
# RAG SYSTEM 
# 
# BIFROST 
# QDRANT 
# JINA 
# 
# 
# FIND  - COLLECT - DEVELOP -- NEW DATA 
# 
# # 4 sources of data 
# 
# # DATA LOADING -- pARSE 
# # CHUNK -- SEMANTIC CHUNKING 
# # LOAD THEM QDRANT 
# 
# ## RETRVAL 
# 
# ### RERANKING  --- JINA
# 
# 
# # 1
# # 2
# # 3
# 
# are they ordered meaningfully/SEMANTICALLY coreect 
# 
# # RAG QUERY 
# 
# ## LANGCHAIN - create_Agent 
# 
# ## RETRIVER AS A TOOL 
# 
# 
# ## OBSERVABILITY 
# ## GUARDRAILS 
# 
# 
# ## EVALUATIONSSSS ARE WAITING
# 
# 
# 
# 
# 
# 

# 
