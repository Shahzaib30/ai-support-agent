# 🤖 AI Customer Support Agent with Memory & Auto-Escalation

An end-to-end AI automation system that handles customer support on Telegram — answers questions using company documents, tracks sentiment, escalates angry customers to humans, and logs everything to a database. Built with n8n, RAG, DeepSeek, and PostgreSQL.

---

## 🎯 What It Does

A customer sends a message on Telegram. From that point, everything is automatic:

- The message hits an **n8n webhook** and gets routed instantly
- A **RAG pipeline** searches through company documents and generates a relevant answer using **DeepSeek API**
- **Sentiment analysis** runs on every message and tracks the mood score over time
- If a customer sends **3 negative messages in a row**, a Slack alert fires and a human agent takes over
- If the RAG system isn't confident enough in its answer, a **support ticket is auto-created** in Notion
- Every conversation, message, and sentiment score is saved to **PostgreSQL** with full memory
- A **daily summary report** is emailed to the manager every morning automatically via n8n schedule

---

## 🏗️ Architecture

```
Telegram Message
      │
      ▼
 n8n Webhook
      │
      ├──► RAG Pipeline (DeepSeek + Company Docs)
      │         │
      │         └──► Auto Reply to Telegram
      │
      ├──► Sentiment Analysis
      │         │
      │         ├── Score < threshold × 3 ──► Slack Escalation Alert
      │         └── Low confidence ──► Notion Ticket Created
      │
      └──► PostgreSQL (Full Conversation Memory)
                │
                └──► Daily Email Summary (n8n Schedule)
```

---

## ⚙️ Tech Stack

| Layer | Tool |
|-------|------|
| Automation | n8n |
| LLM | DeepSeek API |
| RAG | LangChain + FAISS |
| Database | PostgreSQL |
| Messaging | Telegram Bot API |
| Alerts | Slack API |
| Tickets | Notion API |
| Language | Python |

---

## 🚀 Features

- **RAG-powered answers** — responds from actual company documents, not hallucinations
- **Sentiment tracking** — scores every message and remembers the conversation mood
- **Smart escalation** — automatically knows when a human needs to step in
- **Full memory** — every conversation stored and retrievable from PostgreSQL
- **Zero manual work** — from message received to reply sent, nothing needs a human unless escalated
- **Daily reports** — manager gets a summary every morning without asking for it

---

## 📁 Project Structure

```
ai-support-agent/
├── rag/
│   ├── ingest.py          # Load and chunk company documents
│   ├── retriever.py       # Vector search with FAISS
│   └── chain.py           # RAG chain with DeepSeek
├── sentiment/
│   └── analyzer.py        # Sentiment scoring per message
├── n8n/
│   └── workflow.json      # Full n8n workflow export
├── db/
│   └── schema.sql         # PostgreSQL schema
├── .env.example
├── requirements.txt
└── README.md
```

---

## 🛠️ Setup

### 1. Clone the repo
```bash
git clone https://github.com/Shahzaib30/ai-support-agent
cd ai-support-agent
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables
```bash
cp .env.example .env
```

Fill in your `.env`:
```
DEEPSEEK_API_KEY=your_key
TELEGRAM_BOT_TOKEN=your_token
SLACK_WEBHOOK_URL=your_url
NOTION_API_KEY=your_key
POSTGRES_URL=your_db_url
```

### 4. Set up the database
```bash
psql -U postgres -f db/schema.sql
```

### 5. Ingest your documents
```bash
python rag/ingest.py --docs ./docs
```

### 6. Import the n8n workflow
- Open your n8n instance
- Go to **Workflows → Import**
- Upload `n8n/workflow.json`

---

## 📊 How Escalation Works

```
Message received
      │
      ▼
Sentiment score calculated  (-1.0 to +1.0)
      │
      ├── score < -0.5 → flagged as negative
      │
      └── 3 consecutive negative flags?
                │
                ├── YES → Slack alert sent to human agent
                └── NO  → Continue automated flow
```

---

## 🔮 Planned Improvements

- [ ] Voice message transcription via Whisper
- [ ] Multi-language support
- [ ] Dashboard UI for conversation analytics
- [ ] WhatsApp integration alongside Telegram
- [ ] Fine-tuned model on domain-specific support data

---

## 👤 Author

**Shahzaib Shafique**
- GitHub: [@Shahzaib30](https://github.com/Shahzaib30)
- LinkedIn: [linkedin.com/in/s-shahzaib](https://linkedin.com/in/s-shahzaib)
- Portfolio: [shahzaib30.github.io](https://shahzaib30.github.io)