-- Explicit conversation lifecycle: ai_active -> human_pending -> human_active -> resolved/closed
-- Replaces the old two-state (active/escalated) model, which relied on inferring
-- "is a human actively engaged" by re-querying message history at read time.

-- messages.role was VARCHAR(10), which cannot hold 'human_agent' (11 chars) --
-- inserting a human reply would fail with "value too long for type character
-- varying(10)" on any install that hasn't already had this column patched by hand.
ALTER TABLE messages ALTER COLUMN role TYPE VARCHAR(20);

ALTER TABLE conversations
    DROP CONSTRAINT IF EXISTS conversations_status_check;

-- Backfill existing rows into the new vocabulary before widening the constraint.
UPDATE conversations SET status = 'ai_active' WHERE status = 'active';
UPDATE conversations SET status = 'human_active'
    WHERE status = 'escalated'
    AND EXISTS (
        SELECT 1 FROM messages
        WHERE messages.conversation_id = conversations.id
        AND messages.role = 'human_agent'
    );
UPDATE conversations SET status = 'human_pending' WHERE status = 'escalated';

ALTER TABLE conversations
    ADD CONSTRAINT conversations_status_check
    CHECK (status IN ('ai_active', 'human_pending', 'human_active', 'resolved', 'closed'));

ALTER TABLE conversations
    ALTER COLUMN status SET DEFAULT 'ai_active';

-- Customer's origin channel, so it's a real queryable column instead of being
-- sniffed from telegram_chat_id string prefixes (e.g. "discord_...").
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS channel VARCHAR(20);

-- Slack message timestamp of the escalation alert, so follow-up customer
-- messages during the handoff can be posted as thread replies instead of
-- new top-level messages, and so Workflow B can look up the parent message's
-- structured metadata from the thread_ts of a reply.
ALTER TABLE escalations
    ADD COLUMN IF NOT EXISTS slack_message_ts VARCHAR(32);

-- Generic idempotency guard for at-least-once delivery webhooks (WhatsApp,
-- Telegram, Slack Events retries). (source, event_id) must be unique so a
-- retried delivery is detected and skipped instead of reprocessed.
CREATE TABLE IF NOT EXISTS processed_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source      VARCHAR(20) NOT NULL,
    event_id    VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (source, event_id)
);
