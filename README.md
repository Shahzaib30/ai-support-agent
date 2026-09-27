# AI Support Agent

> Production-grade AI customer support system with Hybrid RAG, Sentiment Analysis, and Human-in-the-Loop escalation — serving Web, Discord, WhatsApp, and Telegram from a single channel-agnostic pipeline.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?style=flat&logo=next.js)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat&logo=postgresql)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker)](https://docker.com)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-FF6B35?style=flat)](https://deepseek.com)

---

## Demo

> 🎥 *Demo video coming soon*

![System Architecture](assets/ai_support_agent.png)

---

## What It Does

A customer writes in on Discord, WhatsApp, or the web widget. The system:

1. **Retrieves** relevant knowledge from your documents using hybrid search (FAISS dense + BM25 sparse, fused with RRF, reranked by a cross-encoder)
2. **Generates** a grounded answer via DeepSeek — never hallucinating when confidence is low
3. **Monitors** sentiment across the conversation and escalates automatically after 3 consecutive negative messages, an explicit "talk to a human" request, or low retrieval confidence
4. **Pauses the bot** and alerts your team in Slack with a structured escalation containing conversation ID, customer, channel, reason, and sentiment
5. **Relays** the human agent's Slack thread reply back to the customer on their original channel via n8n
6. **Resumes** the bot automatically once the agent resolves the case

---

## System Architecture

![Architecture](assets/ai_support_agent.png)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLM** | DeepSeek Chat API |
| **Embeddings** | BAAI/bge-small-en-v1.5 (local, fastembed) |
| **Vector Search** | FAISS (dense) + BM25 (sparse) + RRF fusion |
| **Reranking** | FlashRank ms-marco-TinyBERT cross-encoder |
| **Backend** | FastAPI + Python 3.11 (async throughout) |
| **Database** | PostgreSQL 16 (asyncpg) |
| **Cache** | Redis 7 |
| **Automation** | n8n (2 workflows) |
| **Frontend** | Next.js 15 + Tailwind CSS |
| **Monitoring** | Prometheus + Grafana |
| **Containers** | Docker Compose (8 services) |
| **Tracing** | LangSmith |

---

## RAG Pipeline

![RAG Pipeline](assets/rag_pipeline.png)

The retrieval pipeline has 4 stages — most tutorials only implement stage 2:

```
Customer Question
      │
      ▼
1. Query Condenser    — DeepSeek rewrites conversational follow-ups into
                        standalone search queries before retrieval
      │
      ├──────────────────────────┐
      ▼                          ▼
2. Dense Search               Sparse Search
   FAISS cosine similarity    BM25 keyword matching
   (semantic meaning)         (exact terms)
      │                          │
      └────────────┬─────────────┘
                   ▼
           Reciprocal Rank Fusion
           combines both rankings
                   │
                   ▼
3. Cross-Encoder Reranker  — ms-marco-TinyBERT scores each candidate
                              against the query, top 5 selected
                   │
                   ▼
4. Generation      — DeepSeek answers from top 5 chunks
                     + chat history (last 6 turns)
                     + long-term conversation summary
```

All retrieval runs via `asyncio.to_thread` — blocking FAISS/BM25 calls never block the event loop during webhook handling.

---

## Human-in-the-Loop (HITL)

![HITL Flow](assets/HITL_FLOW.png)

### Conversation State Machine

```
              explicit request / 3× negative / low RAG confidence
  AI_ACTIVE ──────────────────────────────────────────► HUMAN_PENDING
      ▲                                                        │
      │                                              agent replies in thread
      │  5-min timeout (nobody engaged)                        ▼
      │◄────────────────────────────────────────── HUMAN_ACTIVE
      │                                                        │
      └──────────────── RESOLVED ◄── agent replies "resolved" ─┘
```

States are an explicit `conversations.status` column — not inferred from message history at read time. Duplicate Slack/WhatsApp webhook deliveries are deduplicated by `(source, event_id)` before they can touch conversation state twice.

### Escalation Triggers

| Trigger | Condition |
|---------|-----------|
| Explicit request | Customer says "I want to talk to an agent" (keyword list) |
| Sentiment | 3 consecutive negative-sentiment messages |
| Low confidence | RAG retrieval score below similarity threshold |

### Agent Workflow

```
Slack alert arrives in #escalations
(includes conversation ID as structured message metadata)
        │
        ▼
Agent replies naturally in the thread — no special format needed
        │
        ├── Any reply    → n8n calls POST /human_reply
        └── "resolved"   → n8n calls POST /resolve/{id}
        │
        ▼
Customer sees the reply on their original channel (Discord DM / web widget)
within 5 seconds via polling
```

---

## Docker Services

![Docker Network](assets/docker_compose_network.png)

```
docker compose up -d
```

| Service | Port | Description |
|---------|------|-------------|
| `api` | 8000 | FastAPI backend |
| `frontend` | 3001 | Next.js web widget + dashboard |
| `discord` | — | Discord bot (separate process) |
| `postgres` | 5432 | PostgreSQL 16 |
| `redis` | 6379 | Redis 7 cache |
| `n8n` | 5678 | Workflow automation |
| `prometheus` | 9090 | Metrics collection |
| `grafana` | 3000 | Metrics dashboard |

---

## Multi-Channel Architecture

Every channel connector normalizes its platform payload into one `IncomingMessage` shape before calling `core.agent.process_message()`. The agent has no idea which channel the customer is on.

```
connectors/
├── base.py          IncomingMessage / AgentReply — shared interface
├── whatsapp/        router.py, client.py, normalizer.py
├── discord/         bot.py (separate process), normalizer.py
├── web/             router.py (owns POST /chat), normalizer.py
└── telegram/        normalizer.py (n8n Workflow A relays here)
```

Adding a new channel = write one normalizer. Zero changes to the agent.

---

## Key Features

- **Channel-agnostic pipeline** — one agent, four channels, no per-channel branching in business logic
- **Hybrid RAG** — dense + sparse retrieval, RRF fusion, cross-encoder reranking, similarity threshold escape hatch
- **Query condensation** — follow-up questions rewritten into standalone queries before search
- **Explicit state machine** — `ai_active → human_pending → human_active → resolved` as a DB column, not inferred
- **Structured Slack HITL** — escalation alerts carry `conversation_id` as Slack message metadata; agents reply naturally in-thread
- **Webhook idempotency** — WhatsApp/Telegram/Slack retries deduplicated by event ID in `processed_events` table
- **Long-term memory** — full message history + rolling summary refreshed every 10 messages
- **Redis caching** — identical questions answered instantly without LLM call
- **Prometheus metrics** — messages, escalations, cache hits, response time, active conversations
- **LangSmith tracing** — full RAG pipeline observability

---

## Project Structure

```
ai-support-agent/
├── connectors/          channel adapters
├── core/
│   └── agent.py         single channel-agnostic pipeline
├── database/            Postgres + Redis (pool, conversations, messages,
│                        escalations, idempotency, cache, stats)
├── escalation/          HITL gate, sentiment gate, explicit detection, Slack
├── api/
│   ├── main.py          FastAPI app init, middleware, routers
│   ├── metrics.py       Prometheus counters/gauges
│   └── routes/          health, stats, resolve, human_reply, messages, ingest
├── rag/
│   ├── ingest.py        load → chunk → embed → FAISS + BM25 index
│   ├── retriever.py     async hybrid search + RRF fusion
│   ├── reranker.py      FlashRank cross-encoder
│   ├── condenser.py     standalone query rewriting
│   └── chain.py         pipeline orchestration + threshold
├── sentiment/
│   └── analyzer.py      async LLM sentiment classification
├── frontend/            Next.js web widget + stats dashboard
├── n8n/                 Workflow A (gateway), Workflow B (Slack HITL)
├── db/                  schema.sql + migrations
├── monitoring/          Prometheus + Grafana provisioning
└── docker-compose.yml
```

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- DeepSeek API key
- Discord Bot Token (for Discord channel)
- Slack Bot Token + Channel ID (for HITL alerts)

### Setup

```bash
git clone https://github.com/Shahzaib30/ai-support-agent.git
cd ai-support-agent

cp .env.example .env
# fill in your API keys in .env

docker compose up -d
```

### Add Your Documents

Drop PDF, TXT, or DOCX files into the `docs/` folder, then run:

```bash
curl -X POST http://localhost:8000/ingest
```

### Access Points

| URL | Description |
|-----|-------------|
| `http://localhost:3001` | Web chat widget |
| `http://localhost:3001/dashboard` | Stats dashboard |
| `http://localhost:8000/docs` | API documentation |
| `http://localhost:3000` | Grafana (admin/admin) |
| `http://localhost:5678` | n8n workflows |

---

## Environment Variables

See [`.env.example`](.env.example) for the full list with comments. Key variables:

```bash
# LLM
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/ai_support_agent
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=

# Discord
DISCORD_BOT_TOKEN=

# Slack (HITL alerts)
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=

# RAG
RAG_SIMILARITY_THRESHOLD=0.0
FAISS_INDEX_PATH=./vector_store/faiss_index

# Monitoring
LANGCHAIN_API_KEY=
```

---

## Database Migrations

Fresh install:
```bash
psql -U postgres -f db/schema.sql
```

Upgrading existing deployment:
```bash
psql -U postgres -d ai_support_agent -f db/migrations/001_long_term_memory_hitl.sql
psql -U postgres -d ai_support_agent -f db/migrations/002_conversation_state_machine.sql
```

Both migrations are idempotent — safe to re-run.

---

## API Reference

### Send a message
```bash
POST /chat
{
  "telegram_chat_id": "user-123",
  "message": "What is your refund policy?",
  "customer_name": "John",
  "channel": "web"
}
```

### Human agent reply
```bash
POST /human_reply
{
  "conversation_id": "uuid",
  "message": "Hi! I am looking into your issue.",
  "agent_name": "John"
}
```

### Resolve conversation (bot resumes)
```bash
POST /resolve/{conversation_id}
```

### Get conversation messages
```bash
GET /messages/{conversation_id}?limit=100
```

### Ingest documents
```bash
POST /ingest
```

---

## n8n Workflows

Import both from `n8n/` folder via **Workflows → Import from File**:

| Workflow | File | Purpose |
|----------|------|---------|
| Customer Gateway | `My workflow.json` | Relays Telegram traffic to `/chat` |
| Slack HITL | `slack_hitl_workflow.json` | Thread replies → `/human_reply` or `/resolve` |

After import, reconnect your Slack credential in each Slack node, then toggle **Active** on both workflows.

---

## Monitoring

Prometheus scrapes `/metrics` every 15 seconds. Grafana dashboards at `http://localhost:3000`:

| Metric | Description |
|--------|-------------|
| `messages_total` | Total messages processed |
| `escalations_total` | Total escalations triggered |
| `cache_hits_total` | Redis cache hits |
| `cache_misses_total` | Redis cache misses |
| `rag_response_seconds` | RAG pipeline latency histogram |
| `active_conversations` | Currently active conversations gauge |

---

## Future Improvements

- [ ] CI pipeline (GitHub Actions) running tests on every PR
- [ ] Live-test Telegram and WhatsApp against real accounts
- [ ] Pre-built Grafana dashboard provisioning
- [ ] Voice message transcription (Whisper) for WhatsApp/Telegram
- [ ] Multi-language support
- [ ] Dedicated human-agent dashboard (beyond Slack)
- [ ] Shared-secret auth on HITL endpoints

---

## Author

**Shahzaib Shafique** — AI Engineer | Generative AI | RAG Systems | AI Agents | Automation

- 🌐 Portfolio: [shahzaib30.github.io](https://shahzaib30.github.io)
- 💼 LinkedIn: [linkedin.com/in/s-shahzaib](https://linkedin.com/in/s-shahzaib)
- 🐙 GitHub: [@Shahzaib30](https://github.com/Shahzaib30)

---

*Built as a portfolio project demonstrating production patterns for AI support systems — not a SaaS product.*