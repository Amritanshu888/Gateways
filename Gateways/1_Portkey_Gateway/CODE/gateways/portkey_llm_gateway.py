#!/usr/bin/env python
# coding: utf-8

# # 🌐 LLM Gateway with Portkey: Zero to Production
# ### A Complete Hands-On Guide for Enterprise AI Systems
# 
# ---
# 
# > **What you'll build:** A progressively enhanced LLM setup — starting from a raw direct API call, then routing every request through a production-grade gateway with observability, retries, fallbacks, caching, and more.
# 
# | Experiment | What We Build | New Concept |
# |---|---|---|
# | 🔴 Baseline | Raw Groq call, no gateway | The problem |
# | 🟡 Exp 1 | Route through Portkey | Gateway basics |
# | 🟡 Exp 2 | + Metadata & Observability | Request tagging |
# | 🟡 Exp 3 | + Automatic Retries | Resilience |
# | 🟡 Exp 4 | + Request Timeouts | Latency control |
# | 🟢 Exp 5 | + Fallbacks | Multi-provider routing |
# | 🟢 Exp 6 | + Load Balancing | Traffic splitting |
# | 🟢 Exp 7 | + Caching | Cost & speed |
# | 🟢 Exp 8 | + Saved Config from Dashboard | Production configs |
# | 🏭 Exp 9 | LangChain Drop-in | Framework integration |
# | 🏭 Exp 10 | Full Production Gateway | Everything combined |
# | 🏭 Exp 11 | Streaming | Real-time token output |

# SETUP

# In[9]:


import os
import time
import uuid
import json
from dotenv import load_dotenv

from portkey_ai import Portkey ,createHeaders , PORTKEY_GATEWAY_URL 


load_dotenv(dotenv_path="../.env")


PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY", "toHeU5iBWu0hDC+8A/NHbKqfAfcy")

portkey = Portkey(api_key=PORTKEY_API_KEY)


# VIRTUAL KEYS 

# In[4]:


GROQ_SLUG = "vk1"
GROQ_MODEL = f"@{GROQ_SLUG}/llama-3.3-70b-versatile"


GROQ_SLUG_2 = "vk2"
GROQ_MODEL_SMALL = f"@{GROQ_SLUG_2}/llama-3.1-8b-instant"


# Keep GROQ_API_KEY for the Baseline experiment (direct Groq call — no gateway)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# In[5]:


print("Setup complete!")
print(f"  Portkey API Key : {'OK' if PORTKEY_API_KEY else 'MISSING'}")
print(f"  Groq slug       : {GROQ_SLUG}")
print(f"  Groq model ref  : {GROQ_MODEL}")
print(f"  Groq slug 2     : {GROQ_SLUG_2}")
print(f"  Small model ref : {GROQ_MODEL_SMALL}")
print(f"\nPortkey Gateway : {PORTKEY_GATEWAY_URL}")


# In[18]:


def section(title):
    print(f"\n{'='*62}")
    print(f"  {title}")
    print(f"{'='*62}")

def show(q, answer, ms, label=""):
    bar = chr(9472) * 62
    print(f"\n{bar}")
    print(f"Q: {q}")
    print(f"A: {answer[:260]}{'...' if len(answer) > 260 else ''}")
    note = f" | {label}" if label else ""
    print(f"⏱  {ms:.0f}ms{note}")
    print(bar)


# ---
# ### BASELINE — Direct LLM Call (No Gateway)
# 
# **Goal:** See what a raw LLM call looks like — no routing, no logging, no resilience.

# In[19]:


from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

raw_groq = ChatGroq(api_key=GROQ_API_KEY, model="llama-3.3-70b-versatile", temperature=0)

section("BASELINE — Direct Groq Call")

questions = [
    "What is Kubernetes in one sentence?",
    "What is Intel SRIOV?",
]

for q in questions:
    t0 = time.time()
    r = raw_groq.invoke([HumanMessage(content=q)])
    show(q, r.content, (time.time()-t0)*1000, label="direct Groq — no gateway")


# ---
# # EXPERIMENT 1 — Route Through the Gateway
# 
# **Goal:** Same call, same answer — but now every request is logged in your Portkey dashboard.
# 
# **New concepts:**
# - `Portkey(api_key=...)` — the gateway client
# - `model="@slug/model-name"` — tells Portkey which provider to use
# - `response.choices[0].message.content` — standard OpenAI response format

# In[22]:


section("EXP 1 — Basic Gateway Call")

questions = [
    "What is AI and gen ai ?",
    "What is coffee and black coffee?",
]


for q in questions:
    t0 = time.time()
    r = portkey.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role":"user","content":q}]
    )
    show(q, r.choices[0].message.content, (time.time()-t0)*1000,
         label="routed via Portkey gateway")
    
print("\n✅ Check portkey.ai → Logs to see both requests fully logged!")
print("   Token count, cost, latency — all tracked. Zero extra code.")


# ### What changed?
# 
# ```
# Before:  Your App  →  Groq directly
# After:   Your App  →  Portkey  →  Groq (via @flight-policsy integration)
# ```
# 
# - Portkey adds ~20–40ms then forwards to Groq using stored credentials
# - Full request + response logged automatically — no extra code
# - **You changed 3 lines. Your business logic is identical.**
# 
# ---
# # EXPERIMENT 2 — Metadata & Observability
# 
# **Goal:** Tag every request with user, session, and feature info so you can filter and analyse in the dashboard.
# 
# **New concept:** `portkey.with_options(metadata={...})` — attaches tags to a single request.
# The special key `_user` powers per-user analytics.

# In[23]:


section("EXP 2 — Metadata & Observability")

# new unique id

session = str(uuid.uuid4())[:8]

scenarios = [
    ("alice", "enterprise-rag",   "What is Kubernetes RBAC?"),
    ("bob",   "docs-chatbot",     "How does BGP path selection work?"),
    ("carol", "support-bot",      "What is SRIOV virtualization?"),
    ("alice", "enterprise-rag",   "Explain Kubernetes NetworkPolicy"),   # same user, diff Q
]



# In[24]:


for user, feature, q in scenarios:
    t0 = time.time()
    r = portkey.with_options(
        metadata={
            "_user":       user,          # powers per-user analytics in dashboard
            "session_id":  session,
            "feature":     feature,
            "environment": "notebook"
        }
    ).chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": q}]
    )
    ms = (time.time() - t0) * 1000
    print(f"\n👤 {user:8s} | 🔧 {feature:18s} | {ms:.0f}ms")
    print(f"  Q: {q}")
    print(f"  A: {r.choices[0].message.content[:120]}...")


# AUTOMATIC RETRIES

# ### Why metadata matters in production
# 
# With `_user` tagging you can answer:
# - *Which users generate the most cost?*
# - *Which feature uses the most tokens?*
# - *What did Alice's full session look like?*
# - *Is the RAG pipeline slower than the support bot?*
# 
# All answered from the Portkey dashboard — no extra logging code.
# 
# ---
# # EXPERIMENT 3 — Automatic Retries
# 
# **Goal:** Portkey automatically retries failed requests with exponential backoff. App code never sees transient 429/5xx errors.
# 
# **New concept:** Pass a `config` dict to `Portkey(...)` with retry settings.

# In[26]:


retry_config = {
    "retry": {
        "attempts": 3,
        "on_status_codes": [429, 500, 502, 503, 504]
    }
}

portkey_retry = Portkey(api_key=PORTKEY_API_KEY, config=retry_config)

section("EXP 3 — Automatic Retries")
print("Config: 3 retry attempts on [429, 500, 502, 503, 504]")
print("Retries fire automatically on failure — transparent to your code\n")


try:
    t0 = time.time()
    r = portkey_retry.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": "What is a AI?"}]
    )
    ms = (time.time() - t0) * 1000
    print(f"✅ Succeeded in {ms:.0f}ms")
    print(f"   {r.choices[0].message.content[:300]}")
    print("\nRetry sequence if Groq had failed:")
    print("  Attempt 1 → 429 → wait 1s → Attempt 2 → 429 → wait 2s → Attempt 3")
    print("  Your code only sees the final success or the last failure")
except Exception as e:
    print(f"❌ All attempts failed: {e}")


# ---
# # EXPERIMENT 4 — Request Timeouts
# 
# **Goal:** Kill requests that take too long. An LLM stall blocks your FastAPI worker indefinitely without a timeout.
# 
# **New concept:** `request_timeout` in milliseconds in the config dict. Portkey returns **HTTP 408** on timeout. Pair with fallbacks for auto-recovery.

# In[27]:


timeout_config = {"request_timeout": 10000}   # 10 seconds in ms

portkey_timeout = Portkey(api_key=PORTKEY_API_KEY, config=timeout_config)

section("EXP 4 — Request Timeouts")
print("Timeout: 10,000ms (10 seconds). Portkey returns HTTP 408 if exceeded.\n")

try:
    t0 = time.time()
    r = portkey_timeout.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": "Explain Kubernetes networking in 2 sentences."}]
    )
    ms = (time.time() - t0) * 1000
    print(f"✅ Response in {ms:.0f}ms (within 10s timeout)")
    print(f"   {r.choices[0].message.content}")
except Exception as e:
    print(f"⏱  Timed out: {e}")
    print("   Portkey issued a 408. Pair with fallback to auto-switch providers on timeout.")

print("\n--- Combining timeout + retry (production pattern) ---")
combined = {
    "request_timeout": 10000,
    "retry": {"attempts": 2, "on_status_codes": [408, 429, 503]}
}
print(json.dumps(combined, indent=2))


# ---
# # EXPERIMENT 5 — Fallbacks
# 
# **Goal:** If the primary model fails, automatically switch to the fallback. Users never see the error.
# 
# **New concept:** `strategy.mode = "fallback"` with an ordered `targets` list. First target is primary, rest are fallbacks.
# 
# **This experiment has two parts:**
# - **Part 1** — primary works fine (shows fallback is ready but not needed)
# - **Part 2** — primary uses a deliberately invalid key → Groq returns 401 → **real fallback fires live**

# In[28]:


fallback_config = {
    "strategy": {"mode": "fallback"},
    "targets": [
        {"override_params": {"model": GROQ_MODEL}},        # primary
        {"override_params": {"model": GROQ_MODEL_SMALL}}   # fallback if primary fails
    ]
}


portkey_fallback = Portkey(api_key=PORTKEY_API_KEY, config=fallback_config)


section("EXP 5 — Fallback Routing")
print(f"Primary  : {GROQ_MODEL}")
print(f"Fallback : {GROQ_MODEL_SMALL}\n")

fallback_questions = [
    "What is Intel Technology?",
    "Explain Kubernetes persistent volume claims.",
]

for q in fallback_questions:
    try:
        t0 = time.time()
        r = portkey_fallback.chat.completions.create(
            messages=[{"role": "user", "content": q}]
        )
        ms = (time.time() - t0) * 1000
        show(q, r.choices[0].message.content, ms, label="primary served")
    except Exception as e:
        print(f"❌ {e}")
        print("   → Check that both GROQ_SLUG and GROQ_SLUG_2 are set correctly in c04")



# In[30]:


# ── Part 2: FORCED fallback — bad primary key triggers real failover ──
print("\n\n--- FORCED FALLBACK DEMO ---")
print("Primary target uses a deliberately invalid Groq API key.")
print("Groq returns 401 → Portkey detects non-2xx → fallback fires automatically.\n")

forced_fallback_config = {
    "strategy": {"mode": "fallback"},
    "targets": [
        {
            "provider": "groq",
            "api_key": "gsk_FAKE_INVALID_KEY_THIS_WILL_FAIL",   # bad key → 401 from Groq
            "override_params": {"model": "llama-3.3-70b-versatile"}
        },
        {"override_params": {"model": GROQ_MODEL_SMALL}}         # real key via virtual key
    ]
}

portkey_forced = Portkey(api_key=PORTKEY_API_KEY, config=forced_fallback_config)

try:
    t0 = time.time()
    r = portkey_forced.chat.completions.create(
        messages=[{"role": "user", "content": "What is ge ai?"}]
    )
    ms = (time.time() - t0) * 1000
    print(f"✅ Got a response in {ms:.0f}ms despite the bad primary key!")
    print(f"   {r.choices[0].message.content[:250]}")
    print("\n→ Check Portkey Logs: attempt 1 shows FAILED (401), attempt 2 shows SUCCEEDED")
    print("   The fallback fired automatically — app code never saw the error.")
except Exception as e:
    print(f"❌ Both targets failed: {e}")


# ### Narrow the fallback trigger
# 
# Default fires on any non-2xx. Narrow it to avoid accidental fallbacks on bad requests:
# 
# ```python
# # Only fall back on rate limits and server errors
# "strategy": {"mode": "fallback", "on_status_codes": [429, 503]}
# ```
# 
# ---
# # EXPERIMENT 6 — Load Balancing
# 
# **Goal:** Split traffic between providers by weight. Use for gradual migration, A/B testing, or cost control.
# 
# **New concept:** `strategy.mode = "loadbalance"` with `weight` per target. Portkey normalises weights to percentages.

# In[32]:


load_balance_config = {
    "strategy": {"mode": "loadbalance"},
    "targets": [
        {"override_params": {"model": GROQ_MODEL},   "weight": 0.7},   # 70%
        {"override_params": {"model": GROQ_MODEL_SMALL}, "weight": 0.3}    # 30%
    ]
}

portkey_lb = Portkey(api_key=PORTKEY_API_KEY, config=load_balance_config)

section("EXP 6 — Load Balancing (70% large / 30% small)")

lb_questions = [
    "What is a Kubernetes Ingress resource?",
    "How does OSPF differ from BGP?",
    "What is Intel FPGA acceleration?",
    "Explain Kubernetes HPA.",
    "What is a VLAN trunk?",
    "How does Kubernetes etcd work?",
]

print("Sending 6 requests. Expect ~4 on large model (70b), ~2 on small model (8b) (probabilistic).\n")

for i, q in enumerate(lb_questions, 1):
    try:
        t0 = time.time()
        r = portkey_lb.chat.completions.create(
            messages=[{"role": "user", "content": q}]
        )
        ms = (time.time() - t0) * 1000
        print(f"Req {i} [{ms:.0f}ms]: {q}")
        print(f"         {r.choices[0].message.content[:120]}...")
    except Exception as e:
        print(f"Req {i}: ERROR — {e}")

print("\n✅ Check Portkey Logs to see which provider served each request")
print("   Set weight=0 to pause a target without removing it from the config")


# ### Load balancing use cases
# 
# | Scenario | Config |
# |---|---|
# | **Gradual migration** | Start 95/5, shift to 50/50, then 0/100 over weeks |
# | **A/B testing** | 50/50 — measure quality + user satisfaction per model |
# | **Cost control** | Route more traffic to the cheaper model |
# | **Maintenance** | `weight: 0` pauses a target without removing it |
# 
# ---
# # EXPERIMENT 7 — Request Caching
# 
# **Goal:** Cache responses to identical questions. Second call is instant and costs nothing.
# 
# **New concept:** `cache.mode = "simple"` does exact-match caching. Identical request → served from cache, no LLM call.

# In[33]:


cache_config = {"cache": {"mode": "simple"}}

portkey_cached = Portkey(api_key=PORTKEY_API_KEY, config=cache_config)

# Use a short, precise question with temperature=0 to maximise cache-key stability
q = "Define Kubernetes ConfigMap in one sentence."
call_params = dict(
    model=GROQ_MODEL,
    messages=[{"role": "user", "content": q}],
    temperature=0,
    max_tokens=120,
)


# In[34]:


print("--- CALL 1: Cache MISS — Portkey forwards to Groq ---")
t0 = time.time()
r1 = portkey_cached.chat.completions.create(**call_params)
t1 = (time.time() - t0) * 1000
ans1 = r1.choices[0].message.content.strip()
print(f"Answer  : {ans1[:200]}")
print(f"Latency : {t1:.0f}ms | Cost: normal token price")


# COST AND TOKENN SAVING

# In[36]:


print("CALL 2: Same request — should be a Cache HIT")
t0 = time.time()
r2 = portkey_cached.chat.completions.create(**call_params)
t2 = (time.time() - t0) * 1000
ans2 = r2.choices[0].message.content.strip()
print(f"Answer  : {ans2[:200]}")
print(f"Latency : {t2:.0f}ms")

identical = ans1 == ans2
speedup   = t1 / t2 if t2 > 0 else 999
print()
print(f"Identical answers : {identical}  ← True = cache served exact stored response")
print(f"Speedup           : {speedup:.1f}x")
if t2 < 200:
    print("✅ Cache HIT confirmed — response served from Portkey in <200ms")
elif identical:
    print("✅ Answers match — cache likely hit but gateway latency added round-trip time")
else:
    print("⚠️  Answers differ — Portkey may have missed cache due to header variation.")
    print("   Verify in Portkey Logs: look for cache_status = HIT on call 2.")
print()
print("To force a fresh response (e.g. after updating docs):")
print("  portkey_cached.with_options(cache_force_refresh=True).chat.completions.create(...)")
print("Note: Portkey Logs → each request shows cache_status (HIT / MISS) in the detail panel.")


# ### Provider slug vs Config ID — the difference
# 
# ```
# @vk1/llama-3.3-70b-versatile
#         ↑
#    Provider slug — identifies WHICH provider to use
#    (you set this when adding the integration)
# 
# pc-abc123
#    ↑
#    Config ID — identifies a saved routing STRATEGY
#    (fallback, retry rules, load balance weights, etc.)
#    (you get this from Portkey → Configs → your config)
# ```
# 
# Both are useful. Provider slugs select the LLM. Config IDs apply complex routing rules.
# 
# ---
# # EXPERIMENT 8 — LangChain Drop-In Integration
# 
# **Goal:** Slot Portkey into any existing LangChain pipeline with **zero changes to chain logic**. Works with chains, agents, and tools — just swap the client.

# In[37]:


from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


portkey_llm = ChatOpenAI(
    api_key=PORTKEY_API_KEY,          # Portkey API key (not Groq key)
    base_url=PORTKEY_GATEWAY_URL,     # Portkey gateway endpoint
    model=GROQ_MODEL,                 # "@flight-policsy/llama-3.3-70b-versatile"
    temperature=0,
    default_headers=createHeaders(    # adds x-portkey-* headers
        api_key=PORTKEY_API_KEY,
        metadata={
            "_user":       "langchain-demo",
            "environment": "notebook",
            "feature":     "langchain-integration"
        }
    )
)


section("EXP 9 — LangChain Drop-in")

# Test 1: Direct .invoke() — same as calling any LangChain LLM directly
print("--- Test 1: Direct .invoke() ---")
t0 = time.time()
r = portkey_llm.invoke([
    SystemMessage(content="You are an Enterprise IT Assistant."),
    HumanMessage(content="What is the difference between a Deployment and a TESTING?")
])
ms = (time.time() - t0) * 1000
print(f"✅ {ms:.0f}ms")
print(r.content[:250])


# CHAIN - LCEL

# In[38]:


# Test 2: LCEL chain — prompt | llm | parser
print("\n--- Test 2: LCEL chain ---")
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an Enterprise IT expert. Be concise."),
    ("human",  "{question}")
])
chain = prompt | portkey_llm | StrOutputParser()

t0 = time.time()
answer = chain.invoke({"question": "Explain Kubernetes pod affinity rules."})
ms = (time.time() - t0) * 1000
print(f"✅ {ms:.0f}ms")
print(answer[:250])

print("\n→ Drop-in replacement for ChatGroq in any LangChain app")
print("→ Every call is now logged in Portkey with metadata, retries, and fallback")


# TASK - LANGCHAIN - CONFIG - retry , cache , fallback 

# In[39]:


PRODUCTION_CONFIG = {
    "strategy":        {"mode": "fallback"},
    "request_timeout": 30000,              # 30s hard cap
    "retry": {
        "attempts":        2,
        "on_status_codes": [429, 500, 503]
    },
    "cache": {"mode": "simple"},           # free repeated queries
    "targets": [
        {"override_params": {"model": GROQ_MODEL}},        # primary — large 70b
        {"override_params": {"model": GROQ_MODEL_SMALL}}   # fallback — small 8b
    ]
}

production_gateway = Portkey(api_key=PORTKEY_API_KEY, config=PRODUCTION_CONFIG)

section("EXP 10 — Full Production Gateway")
print("⚙️  Active:")
print("   Fallback  : large Groq 70b → small Groq 8b on failure")
print("   Retry     : 2 attempts on 429/500/503")
print("   Timeout   : 30 seconds")
print("   Cache     : simple exact match")

test_suite = [
    ("alice", "enterprise-rag",   "What is Kubernetes RBAC?"),
    ("bob",   "support-chat",     "How does Intel SRIOV work?"),
    ("carol", "docs-lookup",      "Explain BGP route reflectors."),
    ("alice", "enterprise-rag",   "What is Kubernetes RBAC?"),  # cache hit!
    ("dave",  "support-chat",     "What is a Kubernetes operator pattern?"),
]

for user, feature, q in test_suite:
    try:
        t0 = time.time()
        r = production_gateway.with_options(
            metadata={
                "_user":       user,
                "feature":     feature,
                "session_id":  str(uuid.uuid4())[:8],
                "environment": "production"
            }
        ).chat.completions.create(
            messages=[{"role": "user", "content": q}]
        )
        ms = (time.time() - t0) * 1000
        cache_hint = " — CACHE HIT!" if ms < 100 else ""
        print(f"\n👤 {user:8s} | {feature:18s} | {ms:.0f}ms{cache_hint}")
        print(f"   Q: {q}")
        print(f"   A: {r.choices[0].message.content[:150]}...")
    except Exception as e:
        print(f"   ERROR: {e}")

print("\n✅ Full observability, resilience, and cost control on every call.")


# ---
# # EXPERIMENT 11 — Streaming
# 
# **Goal:** Stream tokens back to the client as they are generated. All gateway features — logging, retries, fallback — still apply to streaming calls.
# 
# **New concept:** Add `stream=True` to `.chat.completions.create(...)`. The response becomes an iterator of chunks instead of a single completion object.

# In[41]:


section("EXP 11 — Streaming")
print("stream=True works with any Portkey config — logging, fallbacks, and retries still apply.\n")

print("Streaming response: ", end="", flush=True)
t0 = time.time()

stream = portkey.chat.completions.create(
    model=GROQ_MODEL,
    messages=[{"role": "user", "content": "Explain what an LLM gateway does in exactly 3 bullet points."}],
    stream=True
)

for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)

ms = (time.time() - t0) * 1000
print(f"\n\n⏱  {ms:.0f}ms total stream time")
print("\n✅ Full request is still logged in Portkey dashboard — streaming doesn't lose observability.")
print("   Add stream=True to any existing call. All gateway features still apply.")


# In[ ]:




