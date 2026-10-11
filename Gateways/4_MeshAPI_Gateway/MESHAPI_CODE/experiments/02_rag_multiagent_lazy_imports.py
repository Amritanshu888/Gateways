#!/usr/bin/env python
# coding: utf-8

# # MeshAPI RAG + Multi-Agent Workflow (LangChain `create_agent`)
# 
# **Use case:** a support research assistant for a fictional product ("Nimbus Cloud") that:
# 1. Retrieves facts from a knowledge base using **MeshAPI's own embeddings endpoint** + **Pinecone**
# 2. Runs a 3-agent pipeline built with **LangChain's `create_agent`**, each agent backed by a different
#    provider through the same **MeshAPI gateway**:
#    - **Researcher** (`FAST_MODEL` -- cheap/fast) -- has a `search_knowledge_base` tool to gather facts
#    - **Writer** (`SMART_MODEL`) -- drafts a customer-facing answer from the research notes
#    - **Critic** (`SMART_MODEL`, structured output) -- grades the draft `pass` / `revise`
# 
# We don't hand-roll the tool-calling loop -- `create_agent` (from the `langchain` package, LangGraph-backed)
# handles the agent loop, tool dispatch, and structured-output parsing for us. Because MeshAPI is an
# OpenAI-compatible gateway, plugging it into LangChain is just pointing `ChatOpenAI` at MeshAPI's `base_url`
# with your `rsk_...` token as the `api_key` -- every agent still goes through one gateway, one key, one bill,
# even though the framework and the providers underneath are completely standard. Which two providers play
# the "fast" and "smart" roles doesn't matter for the lesson -- swap either model string and the rest of the
# notebook is unchanged.
# 
# **Embeddings also go through the gateway now** -- MeshAPI's `/v1/embeddings` endpoint offers 44 embedding
# models across 12 brands (OpenAI, Cohere, Amazon Titan, Mistral, Google, Qwen, BAAI...), so this notebook
# no longer needs a separate embeddings provider. Only **MeshAPI** and **Pinecone** keys are required.
# 
# **Prereqs:** `01_meshapi_basics_lazy_imports.ipynb` covers opening a client and one chat completion --
# that's all this notebook assumes. Everything else it needs (embeddings, Pinecone, LangChain) is
# introduced here, step by step, imported right where it's first used. You'll also need a **Pinecone**
# API key (pinecone.io).
# 
# ---
# 
# **This is the "lazy imports" variant of this notebook** -- same pipeline as `02_rag_multiagent.ipynb`,
# reorganized into small, single-purpose cells, imports placed at their first point of use, and models
# picked directly by name (no live-catalog fallback logic -- that lesson lives in `features_lazy_imports.ipynb`
# instead, kept out of here so this notebook stays focused on the RAG + multi-agent pipeline itself).

# ## 1. Install

# In[ ]:


get_ipython().run_line_magic('pip', 'install -q meshapi python-dotenv pinecone langchain langchain-openai')


# ## 2. Config: keys

# In[ ]:


import os
from getpass import getpass

from dotenv import load_dotenv
load_dotenv()

MESHAPI_BASE_URL = os.getenv("MESHAPI_BASE_URL", "https://api.meshapi.ai")
MESHAPI_TOKEN = os.getenv("MESH_API_KEY") or os.getenv("MESHAPI_TOKEN") or getpass("MeshAPI token (rsk_...): ")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY") or getpass("Pinecone API key: ")

PINECONE_INDEX_NAME = "meshapi-demo-kb"
PINECONE_CLOUD = "aws"
PINECONE_REGION = "us-east-1"
EMBEDDING_DIMENSIONS = 1024


# ## 3. Open the MeshAPI client

# In[ ]:


from meshapi import MeshAPI

# Native MeshAPI SDK client -- used for chat, embeddings, and model discovery
client = MeshAPI(base_url=MESHAPI_BASE_URL, token=MESHAPI_TOKEN)
print("MeshAPI client ready.")


# ## 4. Pick the models

# In[ ]:


# Picked directly by name -- no live-catalog fallback logic here (that's covered in
# 01/features). Swap any of these for another MeshAPI-routed provider/model string
# and the rest of the notebook works unchanged.
FAST_MODEL = "openai/gpt-4o-mini"
SMART_MODEL = "mistral/mistral-large-3-675b-instruct"
EMBEDDING_MODEL = "openai/text-embedding-3-small"


# ## 5. `ask()` helper -- one chat completion, any model

# In[ ]:


from meshapi import ChatCompletionParams, ChatMessage

def ask(model, prompt, temperature=0.4, max_tokens=350):
    resp = client.chat.completions.create(
        ChatCompletionParams(
            model=model,
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    )
    return resp.choices[0].message.content


# ## 6. MeshAPI embeddings helper
# 
# One call, same gateway client, no separate embeddings provider needed. `dimensions=1024` keeps the
# vectors small and matches the Pinecone index we create below (OpenAI's `text-embedding-3-small`
# supports truncating its native 1536 dimensions down via this param).

# In[ ]:


from meshapi import EmbeddingsParams

def mesh_embed(texts):
    resp = client.embeddings.create(
        EmbeddingsParams(model=EMBEDDING_MODEL, input=texts, dimensions=EMBEDDING_DIMENSIONS)
    )
    return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]


# In[ ]:


# smoke test
vec = mesh_embed(["hello world"])[0]
print("embedding dimensions:", len(vec))


# ## 7. Pinecone setup

# In[ ]:


import time

from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key=PINECONE_API_KEY)

if PINECONE_INDEX_NAME not in [idx["name"] for idx in pc.list_indexes()]:
    pc.create_index(
        name=PINECONE_INDEX_NAME,
        dimension=EMBEDDING_DIMENSIONS,
        metric="cosine",
        spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
    )
    while not pc.describe_index(PINECONE_INDEX_NAME).status["ready"]:
        time.sleep(1)

index = pc.Index(PINECONE_INDEX_NAME)
print(index.describe_index_stats())


# ## 8. Sample knowledge base
# 
# A small fictional support-docs corpus for "Nimbus Cloud" storage. Swap this for your own docs later --
# the pipeline below doesn't care where the text came from.

# In[ ]:


knowledge_base = [
    {"id": "doc-1", "title": "Refund Policy", "text": "Nimbus Cloud offers a 30-day money-back guarantee on all annual plans. Monthly plans can be cancelled anytime but are not eligible for partial refunds. Refund requests must be submitted through the billing portal within the eligibility window."},
    {"id": "doc-2", "title": "Storage Limits", "text": "The Starter plan includes 100GB of storage, Pro includes 2TB, and Enterprise is negotiated per contract. Exceeding your plan's limit pauses new uploads until you upgrade or free up space; existing files remain accessible."},
    {"id": "doc-3", "title": "Data Retention", "text": "Deleted files move to a Trash folder and are permanently removed after 30 days. Account cancellation triggers a 90-day data retention window before permanent deletion, during which reactivation restores all data."},
    {"id": "doc-4", "title": "Sharing & Permissions", "text": "Files can be shared via link (view or edit access) or invited by email with role-based permissions: Viewer, Commenter, Editor, Owner. Shared links can be password-protected and set to expire after a chosen number of days."},
    {"id": "doc-5", "title": "Two-Factor Authentication", "text": "2FA is optional for Starter and Pro plans but mandatory for all Enterprise accounts. Supported methods are authenticator apps (TOTP) and SMS. Recovery codes are generated once and shown only at setup time."},
    {"id": "doc-6", "title": "API Rate Limits", "text": "The Nimbus Cloud API allows 100 requests per minute on Starter, 1000 on Pro, and custom limits on Enterprise. Exceeding the limit returns HTTP 429 with a Retry-After header indicating when to resume."},
    {"id": "doc-7", "title": "Plan Downgrades", "text": "Downgrading takes effect at the end of the current billing cycle. If your stored data exceeds the new plan's limit, you'll have a 14-day grace period to remove files before uploads are paused."},
    {"id": "doc-8", "title": "Support Response Times", "text": "Starter plan support responds within 48 hours via email. Pro plan support responds within 24 hours and includes live chat. Enterprise customers get a dedicated support contact with a 4-hour SLA."},
]


# ## 9. Chunk the knowledge base

# In[ ]:


def chunk_text(text, max_chars=500, overlap=50):
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunks.append(text[start:end])
        start = end - overlap
    return chunks

chunks = []
for doc in knowledge_base:
    for i, c in enumerate(chunk_text(doc["text"])):
        chunks.append({"doc_id": doc["id"], "title": doc["title"], "chunk_index": i, "text": c})

print(f"{len(chunks)} chunks from {len(knowledge_base)} documents.")


# ## 10. Embed + upsert into Pinecone

# In[ ]:


embeddings = mesh_embed([c["text"] for c in chunks])

pinecone_vectors = [
    {
        "id": f"{c['doc_id']}-{c['chunk_index']}",
        "values": emb,
        "metadata": {"title": c["title"], "text": c["text"], "doc_id": c["doc_id"]},
    }
    for c, emb in zip(chunks, embeddings)
]

index.upsert(vectors=pinecone_vectors)
print(f"Upserted {len(pinecone_vectors)} chunks into Pinecone index '{PINECONE_INDEX_NAME}'.")


# ## 11. Retrieval

# In[ ]:


def retrieve(query, top_k=3):
    query_embedding = mesh_embed([query])[0]
    results = index.query(vector=query_embedding, top_k=top_k, include_metadata=True)
    return [
        {"score": m["score"], "title": m["metadata"]["title"], "text": m["metadata"]["text"]}
        for m in results["matches"]
    ]

for r in retrieve("How much storage do I get on the Pro plan?"):
    print(f"[{r['score']:.3f}] {r['title']}: {r['text'][:100]}...")


# ## 12. Plain RAG QA (single call, no agents yet)
# 
# The simplest useful thing: retrieve context, stuff it in a prompt, ask a fast model directly via the
# native MeshAPI SDK (no framework needed for a one-shot call like this).

# In[ ]:


def rag_answer(question, model=FAST_MODEL, top_k=3):
    hits = retrieve(question, top_k=top_k)
    context = "\n\n".join(f"[{h['title']}] {h['text']}" for h in hits)
    prompt = f"""Answer the question using ONLY the context below. If the answer isn't in the context, say you don't know.

Context:
{context}

Question: {question}"""
    return ask(model, prompt, temperature=0.2, max_tokens=300), hits

answer, sources = rag_answer("What happens if I go over my storage limit?")
print(answer)
print("\nSources:", [s["title"] for s in sources])


# ## 13. Multi-agent capstone with LangChain's `create_agent`
# 
# `create_agent` (verified against the current LangChain docs -- `docs.langchain.com/oss/python/langchain/agents`,
# `reference.langchain.com/python/langchain/agents/factory/create_agent`) builds a LangGraph-backed agent that
# handles the tool-calling loop and structured-output parsing for you. We build three of them -- Researcher,
# Writer, Critic -- and wire the whole thing up ourselves in Python (no persistence/checkpointer needed for
# this single-shot pipeline).

# ### 13.1 MeshAPI-backed chat models for LangChain
# 
# MeshAPI is an OpenAI-compatible gateway, so `langchain_openai.ChatOpenAI` can talk to it directly --
# just point `base_url` at MeshAPI and pass your `rsk_...` token as `api_key`. This is the documented,
# recommended way to plug any OpenAI-compatible gateway/proxy into LangChain.

# In[ ]:


from langchain_openai import ChatOpenAI

MESHAPI_OPENAI_BASE_URL = f"{MESHAPI_BASE_URL}/v1"

fast_chat = ChatOpenAI(base_url=MESHAPI_OPENAI_BASE_URL, api_key=MESHAPI_TOKEN, model=FAST_MODEL, temperature=0.3)
smart_chat = ChatOpenAI(base_url=MESHAPI_OPENAI_BASE_URL, api_key=MESHAPI_TOKEN, model=SMART_MODEL, temperature=0.4)

print("LangChain chat models wired to MeshAPI:", FAST_MODEL, "|", SMART_MODEL)


# ### 13.2 Tool: wrap `retrieve()` for the Researcher agent
# 
# `create_agent` accepts either a plain typed/documented function or an `@tool`-decorated one -- we use
# the decorator for a clean name + description, which the LLM uses to decide when to call it.

# In[ ]:


import json

from langchain_core.tools import tool

@tool
def search_knowledge_base(query: str) -> str:
    """Search the Nimbus Cloud knowledge base for relevant policy/product information.

    Args:
        query: the search query text
    """
    hits = retrieve(query, top_k=3)
    return json.dumps(hits)


# ### 13.3 Researcher agent (`FAST_MODEL`, via `create_agent` with a tool)

# In[ ]:


from langchain.agents import create_agent

researcher_agent = create_agent(
    model=fast_chat,
    tools=[search_knowledge_base],
    system_prompt=(
        "You are a research assistant. Use the search_knowledge_base tool to gather facts "
        "before answering. Once you have enough information, summarize the relevant facts as "
        "a short bullet list. Do not answer the user's question directly -- just report findings."
    ),
)

def run_researcher(question):
    result = researcher_agent.invoke({"messages": [{"role": "user", "content": question}]})
    return result["messages"][-1].content


# ### 13.4 Writer agent (`SMART_MODEL`, via `create_agent` with no tools)
# 
# Even with zero tools, using `create_agent` keeps every agent in the pipeline built the same way --
# one consistent framework construct instead of a hand-rolled call for some agents and a loop for others.

# In[ ]:


writer_agent = create_agent(
    model=smart_chat,
    system_prompt=(
        "You are a helpful support agent for Nimbus Cloud. Using the research notes the user gives you, "
        "write a clear, friendly answer to their original question."
    ),
)

def run_writer(question, research_notes):
    prompt = f"Customer question: {question}\n\nResearch notes:\n{research_notes}"
    result = writer_agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    return result["messages"][-1].content


# ### 13.5 Critic agent (`SMART_MODEL`, structured output via `response_format`)
# 
# `response_format=Critique` makes `create_agent` return a validated Pydantic instance at
# `result["structured_response"]` -- no manual JSON parsing.

# In[ ]:


from pydantic import BaseModel, Field

class Critique(BaseModel):
    verdict: str = Field(description="'pass' or 'revise'")
    reason: str
    missing_info: str = Field(default="", description="what's missing, if verdict is 'revise'")

critic_agent = create_agent(
    model=smart_chat,
    system_prompt=(
        "You are a quality reviewer for customer support answers. Grade the draft strictly: does it "
        "fully and accurately answer the question using only reasonable support-agent knowledge?"
    ),
    response_format=Critique,
)

def run_critic(question, draft):
    prompt = f"Question: {question}\n\nDraft answer: {draft}\n\nGrade this draft."
    result = critic_agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    return result["structured_response"]


# ### 13.6 Orchestrate the full pipeline

# In[ ]:


def research_write_review(question):
    print(f"Question: {question}\n")

    notes = run_researcher(question)
    print(f"--- Researcher ({FAST_MODEL}) ---\n{notes}\n")

    draft = run_writer(question, notes)
    print(f"--- Writer ({SMART_MODEL}) ---\n{draft}\n")

    critique = run_critic(question, draft)
    print(f"--- Critic ({SMART_MODEL}) --- verdict={critique.verdict}, reason={critique.reason}\n")

    return draft


# In[ ]:


final = research_write_review("If I cancel my monthly plan halfway through, do I get money back?")
print("\n=== FINAL ANSWER ===")
print(final)


# ## 14. Try your own questions

# In[ ]:


research_write_review("Is two-factor authentication required on the Pro plan?")


# ## 15. Cleanup

# In[ ]:


# pc.delete_index(PINECONE_INDEX_NAME)
client.close()
print("Done.")

