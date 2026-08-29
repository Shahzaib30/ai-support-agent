

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


CREATE TABLE IF NOT EXISTS conversations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    telegram_chat_id    VARCHAR(50) UNIQUE NOT NULL,
    customer_name       VARCHAR(100),
    started_at          TIMESTAMP DEFAULT NOW(),
    last_message_at     TIMESTAMP DEFAULT NOW(),
    is_escalated        BOOLEAN DEFAULT FALSE,
    escalated_at        TIMESTAMP,
    total_messages      INTEGER DEFAULT 0,
    avg_sentiment_score FLOAT DEFAULT 0.0,
    status              VARCHAR(20) DEFAULT 'active'
                        CHECK (status IN ('active', 'escalated', 'resolved', 'closed'))
);


CREATE TABLE IF NOT EXISTS messages (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role                VARCHAR(10) NOT NULL CHECK (role IN ('user', 'assistant')),
    content             TEXT NOT NULL,
    sentiment_score     FLOAT,
    sentiment_label     VARCHAR(10) CHECK (sentiment_label IN ('positive', 'neutral', 'negative')),
    rag_used            BOOLEAN DEFAULT FALSE,
    cache_hit           BOOLEAN DEFAULT FALSE,
    response_time_ms    INTEGER,
    created_at          TIMESTAMP DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS escalations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    reason              TEXT,
    negative_count      INTEGER,
    slack_notified      BOOLEAN DEFAULT FALSE,
    resolved            BOOLEAN DEFAULT FALSE,
    resolved_at         TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS rag_queries (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id     UUID REFERENCES conversations(id) ON DELETE SET NULL,
    question            TEXT NOT NULL,
    retrieved_chunks    JSONB,
    generated_answer    TEXT,
    hallucination_score FLOAT,
    faithfulness_score  FLOAT,
    relevancy_score     FLOAT,
    retrieval_time_ms   INTEGER,
    correction_triggered BOOLEAN DEFAULT FALSE,
    hyde_triggered      BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS daily_summaries (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date                DATE UNIQUE NOT NULL,
    total_messages      INTEGER DEFAULT 0,
    total_conversations INTEGER DEFAULT 0,
    total_escalations   INTEGER DEFAULT 0,
    avg_sentiment       FLOAT,
    avg_response_ms     INTEGER,
    cache_hit_rate      FLOAT,
    created_at          TIMESTAMP DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id);

CREATE INDEX IF NOT EXISTS idx_messages_created
    ON messages(created_at);

CREATE INDEX IF NOT EXISTS idx_messages_sentiment
    ON messages(sentiment_label);

CREATE INDEX IF NOT EXISTS idx_conversations_chat_id
    ON conversations(telegram_chat_id);

CREATE INDEX IF NOT EXISTS idx_conversations_status
    ON conversations(status);

CREATE INDEX IF NOT EXISTS idx_rag_queries_conversation
    ON rag_queries(conversation_id);

CREATE INDEX IF NOT EXISTS idx_escalations_conversation
    ON escalations(conversation_id);

CREATE INDEX IF NOT EXISTS idx_daily_summaries_date
CREATE OR REPLACE FUNCTION update_conversation_last_message()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE conversations
    SET
        last_message_at = NOW(),
        total_messages = total_messages + 1
    WHERE id = NEW.conversation_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_conversation
    AFTER INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION update_conversation_last_message();