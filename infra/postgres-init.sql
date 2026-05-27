-- Runs once on first Postgres boot (mounted into docker-entrypoint-initdb.d).
-- Enables the extensions PyNote depends on. Schemas + tables are managed by Alembic.

CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector: dense embeddings
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- trigram similarity for fuzzy sparse
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- gen_random_uuid alternative
CREATE EXTENSION IF NOT EXISTS btree_gin;    -- composite GIN indexes
