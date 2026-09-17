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

-- Conversations, keyed by their owner and an id: the API's thread names and the OpenAI adapter's
-- hashed ids alike. The checkpoint key is `{user_id}:{thread_id}`, built by the server.
CREATE TABLE threads (
    user_id text NOT NULL,
    thread_id text NOT NULL,
    client text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, thread_id)
);
CREATE INDEX threads_user_created_idx ON threads (user_id, created_at DESC);

-- A prompt and its answer, hashed with the user, pointing at the thread they were said on.
-- Chat apps resend a sliding window of past turns and no conversation id; any pair still in
-- the window finds the thread. The first thread to register an alias keeps it.
CREATE TABLE thread_aliases (
    user_id text NOT NULL,
    alias_hash text NOT NULL,
    thread_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, alias_hash),
    FOREIGN KEY (user_id, thread_id) REFERENCES threads (user_id, thread_id) ON DELETE CASCADE
);

-- Row-level security: one user's rows are invisible and unwritable to another. The app connects
-- as `lauretta_app` (01-app-role.sh), a role without BYPASSRLS, and sets `app.user_id` inside each
-- transaction. Unset, `current_setting(..., true)` is NULL, or '' on a connection that was scoped
-- before (NULLIF makes that NULL too), and no row matches or may be written. FORCE applies the
-- policies to the tables' owner too; only a superuser (backups, this script) bypasses them.
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['facts', 'holdings', 'theses', 'threads', 'thread_aliases'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I'
            ' USING (user_id = NULLIF(current_setting(''app.user_id'', true), ''''))'
            ' WITH CHECK (user_id = NULLIF(current_setting(''app.user_id'', true), ''''))',
            t || '_own', t
        );
    END LOOP;
END
$$;
