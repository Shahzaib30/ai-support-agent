
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS summary TEXT;

ALTER TABLE messages
    DROP CONSTRAINT IF EXISTS messages_role_check;

ALTER TABLE messages
    ADD CONSTRAINT messages_role_check
    CHECK (role IN ('user', 'assistant', 'human_agent'));
