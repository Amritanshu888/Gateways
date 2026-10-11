# Bifrost Getting Started

A hands-on walkthrough of [Bifrost](https://github.com/maximhq/bifrost) — a self-hosted,
open-source AI gateway — using only providers with usable free tiers: **Groq** and **Mistral**
for chat, **Jina AI** for embeddings, and **Qdrant Cloud** for vector storage.

Everything lives in [`bifrost_experiment.ipynb`](bifrost_experiment.ipynb): baseline vanilla-SDK
calls, Bifrost's drop-in unified API, automatic failover, load balancing, streaming,
observability, virtual keys, MCP tool-calling (DeepWiki + Tavily), and a RAG pipeline built on
`langchain_qdrant.QdrantVectorStore`.

For deeper background — terminology, what Bifrost actually is, how it compares to alternatives,
free vs. enterprise, security, and AI governance — see [`docs/`](docs/), starting with
[`docs/00-terminologies.md`](docs/00-terminologies.md).

---

## Prerequisites

- Python 3.10+
- [Docker](https://www.docker.com/products/docker-desktop) (to run the Bifrost container)
- Free API keys:
  - [Groq](https://console.groq.com) — `GROQ_API_KEY`
  - [Mistral](https://console.mistral.ai) — `MISTRAL_API_KEY`
  - [Jina AI](https://jina.ai) — `JINA_API_KEY` (embeddings)
  - [Qdrant Cloud](https://cloud.qdrant.io) — free cluster, gives you `QDRANT_URL` + `QDRANT_API_KEY`

---

## 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

## 2. Configure environment variables

```bash
cp .env.example .env
```

Fill in `.env`:

```dotenv
GROQ_API_KEY=
MISTRAL_API_KEY=
JINA_API_KEY=
QDRANT_URL=                     # e.g. https://xxxxxxxx.aws.cloud.qdrant.io
QDRANT_API_KEY=
BIFROST_BASE_URL=http://localhost:8080
BIFROST_GROQ_VIRTUAL_KEY=       # optional, see step 5
BIFROST_MISTRAL_VIRTUAL_KEY=    # optional, see step 5
```

## 3. Run Bifrost on Docker

**First time only** — create the container:

```bash
docker run -d --name bifrost -p 8080:8080 maximhq/bifrost
```

- `--name bifrost` matters — every command below assumes this exact name.
- No config file or env vars need to be passed in here. Everything (providers, virtual keys,
  MCP servers) gets configured afterward through Bifrost's Web UI and is stored **inside this
  container**, so it survives stop/start cycles — it would only be lost if the container itself
  were deleted (`docker rm`) and recreated without a mounted data volume.

**Every time after** — this is your whole daily workflow, nothing else to run:

```bash
docker start bifrost   # bring it up
docker stop bifrost    # shut it down when done
```

**Verify it's up:**

```bash
curl http://localhost:8080/health
# {"components":{"db_pings":"ok"},"status":"ok"}
```

Or just open `http://localhost:8080` in a browser — that's also the Web UI for the next steps.

## 4. Add Groq & Mistral as providers

In the Web UI: **Models → Model Providers → Add New Provider**

- Provider = `groq`, paste your real `GROQ_API_KEY` as a new key
- Provider = `mistral`, paste your real `MISTRAL_API_KEY` as a new key

(The key's "name" field is just a label — it does **not** need to match any env var.)

## 5. (Optional) Virtual Keys — scoped access & budgets

**Governance → Virtual Keys → Add Virtual Key.** Create one per provider if you want scoped,
budget-limited access instead of using your raw provider keys everywhere. Bifrost shows you the
generated secret (`sk-bf-...`) once at creation — copy Groq's into `BIFROST_GROQ_VIRTUAL_KEY` and
Mistral's into `BIFROST_MISTRAL_VIRTUAL_KEY` in `.env`. Virtual keys are enforced per-provider: a
key scoped to Groq will get a `403` if used to call a Mistral model — that's expected, not a bug,
which is also why the notebook uses one client per virtual key instead of one shared client.

## 6. (Optional) MCP tool servers — DeepWiki & Tavily

**MCP Gateway → MCP Catalog → Add MCP Server:**

| Field | DeepWiki | Tavily |
|---|---|---|
| Name | `deepwiki` | `tavily` |
| Connection Type | `HTTP (Streamable)` | `HTTP (Streamable)` |
| Connection URL | `https://mcp.deepwiki.com/mcp` | `https://mcp.tavily.com/mcp/?tavilyApiKey=YOUR_TAVILY_KEY` |
| Authentication Type | `None` | `None` |

Tavily needs a free key from `https://app.tavily.com/home` first.

**Critical last step:** open each server after creating it and toggle **Auto-execute** on for
its tools. Without this, Bifrost proposes the tool call and stops instead of running it and
returning a real answer.

## 7. Run the notebook

```bash
jupyter notebook bifrost_experiment.ipynb
```

Run top to bottom. Section 0 will tell you immediately if Bifrost isn't reachable or a required
key is missing.

---

## What's in the notebook

| Section | Covers |
|---|---|
| 0 | Env setup, Bifrost health check, shared test prompts/models |
| 1 | Baseline: vanilla Groq/Mistral SDKs, no gateway |
| 2 | Bifrost setup, drop-in unified client |
| 3 | Unified API, failover, weighted load balancing, streaming, logs, virtual keys (3.6), MCP (3.7) |
| 4 | RAG pipeline: `QdrantVectorStore` + a custom Jina `Embeddings` class + Bifrost generation |

OpenTelemetry tracing, guardrails, cluster mode, secret-manager integration, and deeper RAG
techniques (chunking, reranking, hybrid search) are intentionally skipped — noted inline in the
notebook rather than given their own section, since most need infra or scope this repo doesn't
assume you have. See [`docs/03-oss-vs-enterprise.md`](docs/03-oss-vs-enterprise.md) for the
free-vs-enterprise breakdown of what's skipped and why.

---

## Known gotchas (found the hard way — already fixed in the notebook)

- **Groq is retiring `llama-3.3-70b-versatile` and `llama-3.1-8b-instant`** on 2026-08-16
  (free/dev tier). The notebook uses `openai/gpt-oss-120b` / `gpt-oss-20b` instead — Groq's own
  recommended replacements, served on Groq's hardware via `GROQ_API_KEY` (nothing to do with
  OpenAI credits).
- **`mistralai` SDK (2.x) moved its client** — `from mistralai import Mistral` now raises
  `ImportError`. Use `from mistralai.client import Mistral`.
- **Qdrant Cloud + `qdrant-client`**: Qdrant Cloud's documented default is REST over `:6333` —
  that's what the notebook tries first. If your network blocks that outbound port (some
  sandboxed/corporate networks do), it falls back to the standard HTTPS port (`443`)
  automatically. If you ever see a connection reset here, that's the symptom.
- **Bifrost's MCP auto-execute loop breaks on Groq's reasoning models** (`gpt-oss-120b`/`20b`) —
  it resends the model's reasoning trace on the follow-up turn, and Groq's API rejects it
  (`400: 'reasoning_content' is unsupported`). The notebook runs MCP calls on Mistral instead,
  which has no such issue.
- **MCP tools need "Auto-execute" turned on per tool** in the Web UI — enabled-but-not-executing
  is the default, and Bifrost will otherwise just hand back a proposed tool call.
- **Bifrost has no gateway-level auth by default.** Any string works as the client `api_key`
  unless you've set up real Virtual Keys (a separate feature from naming a provider key).
- **LangChain's built-in Jina wrapper is stale.** `langchain_community.embeddings.JinaEmbeddings`
  defaults to the old `jina-embeddings-v2-base-en` and has no `task` parameter — the thing that
  makes v3/v4 embeddings good. The notebook defines its own tiny `JinaEmbeddings(Embeddings)`
  class instead, so it can stay on `jina-embeddings-v4` with proper `retrieval.passage` /
  `retrieval.query` task adapters while still plugging into `QdrantVectorStore` normally.
- **A single request can't demonstrate load balancing.** Section 3.3 fires 10 requests and
  tallies which provider key handled each one — one call only ever proves which key exists, not
  how traffic splits across several.

---

## Security

- `.env` is gitignored — never commit it.
- The venv folder (`bienv`/`.venv`) is gitignored too.
- If any key in your `.env` was ever pasted somewhere shared (chat, logs, screenshots), rotate it.
