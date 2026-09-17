-- Runs once, when the db volume is first created. LangGraph creates its checkpoint tables itself.

CREATE EXTENSION IF NOT EXISTS vector;

-- Everything learned about the investor and the assistant, one row per fact, searchable by
-- meaning (embedding of `content`) and by words (`content_tsv`).
--   subject user:      kind memory (free text with a topic), profile and signal (keyed)
--   subject assistant: kind identity (keyed) and soul (free text, proposed then approved)
-- A keyed fact has one active value per (user, subject, key); a new value supersedes the old row,
-- which is kept. Signals are written by code from the request, never by the model.
-- The embedding size must match EMBED_DIMS; the agent refuses to start otherwise.
CREATE TABLE facts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id text NOT NULL,
    subject text NOT NULL CHECK (subject IN ('user', 'assistant')),
    kind text NOT NULL CHECK (kind IN ('identity', 'profile', 'soul', 'memory', 'signal')),
    key text,
    topic text,
    content text NOT NULL,
    value jsonb,
    sha256 text,
    embedding vector(384) NOT NULL,
    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    source text NOT NULL CHECK (source IN ('chat', 'client', 'gateway', 'voice', 'cli', 'owner')),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'proposed', 'superseded', 'rejected')),
    supersedes uuid REFERENCES facts (id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    -- Free-text memories are deduplicated by topic and normalized words.
    UNIQUE (user_id, sha256),
    CHECK ((key IS NOT NULL) = (kind IN ('identity', 'profile', 'signal'))),
    CHECK ((topic IS NOT NULL) = (kind = 'memory')),
    CHECK ((sha256 IS NOT NULL) = (kind = 'memory')),
    CHECK ((subject = 'assistant') = (kind IN ('identity', 'soul')))
);
CREATE INDEX facts_embedding_idx ON facts USING hnsw (embedding vector_cosine_ops);
CREATE INDEX facts_content_tsv_idx ON facts USING gin (content_tsv);
CREATE INDEX facts_user_kind_created_idx ON facts (user_id, kind, created_at DESC);
CREATE UNIQUE INDEX facts_one_active_key_idx ON facts (user_id, subject, key)
    WHERE key IS NOT NULL AND status = 'active';
CREATE UNIQUE INDEX facts_one_active_soul_idx ON facts (user_id)
    WHERE kind = 'soul' AND status = 'active';

-- What the investor owns, as they told us. Never synced from a broker.
CREATE TABLE holdings (
    user_id text NOT NULL,
    ticker text NOT NULL,
    shares numeric NOT NULL CHECK (shares > 0),
    avg_cost numeric CHECK (avg_cost > 0),
    note text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, ticker)
);

-- Every research run: the analyst's story, the checker's review, the advisor's suggestion.
CREATE TABLE theses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id text NOT NULL,
    ticker text NOT NULL,
    story jsonb NOT NULL,
    review jsonb NOT NULL,
    advice jsonb NOT NULL,
    revisions integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX theses_user_ticker_idx ON theses (user_id, ticker, created_at DESC);
