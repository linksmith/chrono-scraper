"""Discovery/dedup/scrape-state overhaul: capture digests, WARC refs, retry state, indexes

Revision ID: discovery_dedup_state
Revises: rename_pages_v2
Create Date: 2026-07-06

Additive only:
- pages.capture_digest (archive payload digest) + backfill from completed scrape_pages
- scrape_pages.warc_filename/warc_offset/warc_length (Common Crawl record location)
- scrape_pages.next_retry_at (exponential-backoff re-queue of failed fetches)
- scrape_pages.page_id: legacy never-populated INTEGER -> UUID so it can point at pages.id
- indexes needed by the digest lookup, retry beat task, reaper and session/domain queries,
  built CONCURRENTLY outside the migration transaction.
"""
from alembic import op

# revision identifiers
revision = 'discovery_dedup_state'
down_revision = 'rename_pages_v2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE pages ADD COLUMN IF NOT EXISTS capture_digest VARCHAR(64)")
    op.execute("ALTER TABLE scrape_pages ADD COLUMN IF NOT EXISTS warc_filename TEXT")
    op.execute("ALTER TABLE scrape_pages ADD COLUMN IF NOT EXISTS warc_offset BIGINT")
    op.execute("ALTER TABLE scrape_pages ADD COLUMN IF NOT EXISTS warc_length BIGINT")
    op.execute("ALTER TABLE scrape_pages ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMP WITH TIME ZONE")

    # scrape_pages.page_id was a legacy integer that was never populated; refuse to
    # convert it if that ever stops being true rather than silently losing values.
    op.execute("""
        DO $$
        DECLARE populated bigint;
        BEGIN
            IF (SELECT data_type FROM information_schema.columns
                WHERE table_name = 'scrape_pages' AND column_name = 'page_id') = 'integer' THEN
                SELECT count(*) INTO populated FROM scrape_pages WHERE page_id IS NOT NULL;
                IF populated > 0 THEN
                    RAISE EXCEPTION 'scrape_pages.page_id has % populated rows; refusing integer->uuid conversion', populated;
                END IF;
                ALTER TABLE scrape_pages ALTER COLUMN page_id TYPE uuid USING NULL;
            END IF;
        END $$;
    """)

    # Backfill the digest of already-extracted pages so they can be reused by digest.
    op.execute("""
        UPDATE pages p
        SET capture_digest = sp.digest_hash
        FROM (
            SELECT DISTINCT ON (original_url, unix_timestamp)
                   original_url, unix_timestamp::bigint AS ts, digest_hash
            FROM scrape_pages
            WHERE status = 'completed'
              AND digest_hash IS NOT NULL
              AND unix_timestamp ~ '^[0-9]+$'
            ORDER BY original_url, unix_timestamp, id
        ) sp
        WHERE p.url = sp.original_url
          AND p.unix_timestamp = sp.ts
          AND p.capture_digest IS NULL
    """)

    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_scrape_pages_domain_status "
                   "ON scrape_pages (domain_id, status)")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_scrape_pages_scrape_session_id "
                   "ON scrape_pages (scrape_session_id)")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_scrape_pages_retry_due "
                   "ON scrape_pages (next_retry_at) WHERE status = 'failed'")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_scrape_pages_in_progress "
                   "ON scrape_pages (last_attempt_at) WHERE status = 'in_progress'")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_project_pages_page_id "
                   "ON project_pages (page_id)")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pages_capture_digest "
                   "ON pages (capture_digest) WHERE capture_digest IS NOT NULL")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pages_content_hash "
                   "ON pages (content_hash) WHERE content_hash IS NOT NULL")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name in ("ix_pages_content_hash", "ix_pages_capture_digest", "ix_project_pages_page_id",
                     "ix_scrape_pages_in_progress", "ix_scrape_pages_retry_due",
                     "ix_scrape_pages_scrape_session_id", "ix_scrape_pages_domain_status"):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")

    op.execute("UPDATE scrape_pages SET page_id = NULL")
    op.execute("ALTER TABLE scrape_pages ALTER COLUMN page_id TYPE integer USING NULL")
    op.execute("ALTER TABLE scrape_pages DROP COLUMN IF EXISTS next_retry_at")
    op.execute("ALTER TABLE scrape_pages DROP COLUMN IF EXISTS warc_length")
    op.execute("ALTER TABLE scrape_pages DROP COLUMN IF EXISTS warc_offset")
    op.execute("ALTER TABLE scrape_pages DROP COLUMN IF EXISTS warc_filename")
    op.execute("ALTER TABLE pages DROP COLUMN IF EXISTS capture_digest")
