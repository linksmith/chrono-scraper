# Chrono Scraper — Full Audit & Simplification Plan

_Generated 2026-07-03. Basis: full static exploration of `frontend/`, `backend/`, and the
`munin-community` WireGuard reference project._

## 1. Executive summary

Chrono Scraper works, but it has accreted far more surface than a domain-in → scrape-out tool
needs. The frontend carries ~30 routes (7 of them test/debug stubs, 3 dead admin backups) and
two parallel implementations of most scraping-progress UI. The backend has **111 service files
(~21 orphaned, never imported), 48 endpoint files, three overlapping Common Crawl proxy
implementations, and two archive routers** — and the live scrape path actually bypasses the
"enhanced" router in favour of a simpler direct fetcher. Documentation (CLAUDE.md) still
describes Firecrawl as the extraction engine, but Firecrawl has already been removed from
`docker-compose.yml`; extraction now runs on trafilatura/newspaper3k/BeautifulSoup.

The four requested changes are all achievable with **low structural risk**, because:

1. **Simplify the UI** — the essential path already exists; simplification is mostly deletion
   plus collapsing a 4-step wizard into 1 step and slimming one 1641-line progress page.
2. **Progress / logging / reporting** — the backend already records everything needed
   (`ScrapeSession`, `ScrapePage` with per-URL filter/error reasons, `PageErrorLog`,
   `ScrapeMonitoringLog`). The gap is a **completion-report view and a log stream** on the
   frontend, plus one REST endpoint that reads the error/monitoring logs directly.
3. **FlareSolverr** — there is currently **no** challenge handling at all. This is a clean,
   additive integration: a new sidecar service + a fetch fallback when a 403/503/challenge is
   detected.
4. **Mullvad WireGuard egress** — the proxy env plumbing (`USE_PROXY`, `PROXY_SERVER`,
   `PROXY_USERNAME/PASSWORD`) is **already wired to every network client** (httpx, requests,
   aiohttp). Switching egress is mostly a config change: point `PROXY_SERVER` at a
   `wg-gateway` sidecar (copied from munin-community) instead of Decodo/SmartProxy.

## 2. What actually runs today (vs. what the docs claim)

| Area | Reality |
|---|---|
| Extraction | trafilatura / newspaper3k / BeautifulSoup via `content_extraction_service.py`. **Firecrawl is gone** from compose despite CLAUDE.md and task/file names still saying "firecrawl". |
| Scrape trigger | `POST /api/v1/projects/{id}/scrape` (alias of `/execute`) → creates `ScrapeSession` → dispatches `scrape_domain_with_intelligent_extraction.delay(domain_id, session_id)` per active domain (`app/tasks/firecrawl_scraping.py`). |
| CDX discovery | Wayback via `wayback_machine.py` (httpx); Common Crawl via `cc_simple_fetcher.py` → `common_crawl_direct_service.py` (aiohttp). The "enhanced" router with SmartProxy strategies is **bypassed** on the live CC path. |
| Proxy | Decodo/SmartProxy residential rotation. Env-driven; **already applied to every archive/content client.** |
| Progress | Two parallel WebSocket systems + a polling fallback. No completion report screen. |
| Auth | Session cookies (not JWT). Registration + email verification + LLM approval + admin panel — heavy for a single-user tool. |

## 3. Findings

### 3.1 Frontend bloat (delete candidates)
- **Test/debug routes (7):** `/simple-test`, `/test-buttons`, `/test-markdown`, `/meilisearch-test`,
  `/search-demo`, `/shared-pages-test`, `/admin/debug`.
- **Dead files in routes tree:** `admin/+page.svelte.backup`, `.backup2`, `.complex` (830/337/830
  lines), `admin/debug.svelte` orphan.
- **Entire incremental-scraping subsystem** reachable only through
  `lib/components/examples/ProjectPageWithIncremental.svelte` — effectively dead
  (`RealTimeProgress`, `ScrapingControls`, `IncrementalScraping*`, `DomainManagement`,
  `CoverageVisualization`, ~3000 lines).
- **Zero-import components:** `LiveTaskProgress`, `AnalyticsDashboard`, `DiscoveryDashboard`,
  `AdvancedSearchForm`, `ContentPreview`, `EnhancedDomainCard`, `ArchiveSourceExample`, etc.
- **Duplicate families:** legacy `URLProgress*`/`URLGroupedResults` vs active
  `EnhancedURLProgress*`; two `BulkActionToolbar`; three WebSocket connection strategies;
  four overlapping filter stores (`filters.ts`, `filtering.ts`, `page-management.ts`, `search.ts`).
- **Feature routes tangential to scrape-first:** `/dashboard`, `/library`, `/entities`,
  `/extraction`, `/investigations`, `/search`, `/profile`, `/admin`, `/projects/[id]/analytics`,
  `/projects/[id]/share`, `/projects/[id]/scrape-pages`.
- **Hardcoded secret:** Meilisearch key in `stores/search.ts` (+ in `docker-compose.yml`).

### 3.2 Backend bloat & redundancy
- **~21 orphaned service files** (never imported): `audit_alerts`, `audit_logging_service`,
  `audit_retention`, `backup_monitoring/notifications/verification`, `change_detection`,
  `compliance_reporting`, `cost_estimation`, `data_transformers`, `enhanced_project_creation`,
  `fetch_service`, `firecrawl_extractor`, `health_check_service`, `hybrid_query_monitoring`,
  `investigation_service`, `meilisearch_service_old`, `performance_dashboard_service`,
  `prometheus_metrics_service`, `quality_scoring`, `topic_modeling`.
- **Three overlapping Common Crawl proxy services** (`common_crawl_service`,
  `common_crawl_proxy_service`, `smartproxy_common_crawl_service`) + `common_crawl_direct_service`.
- **Two archive routers** (`archive_service_router` base + `enhanced_archive_router` subclass),
  with the live path using neither for CC (uses `cc_simple_fetcher`).
- **Diagnostic scripts** committed at `backend/` root (`fetch_stoerwoud_*.py`,
  `domain_investigation.py`, `debug_env_settings.py`, `verify_common_crawl_fix.py`).

### 3.3 Observability gaps (what blocks "was everything scraped?")
The **data exists** but is not surfaced as a single answer:
- Completeness = `ScrapeSession.total_urls` vs `completed_urls + failed_urls + cancelled_urls`
  and `status`; corroborated by `CDXResumeState` (did discovery finish?).
- Failures = `ScrapePage.status == failed` with `error_type`/`error_message`/`retry_count`;
  deliberate skips = the `FILTERED_*` statuses with `filter_reason`/`filter_category`.
- Root cause = `PageErrorLog` (structured `error_details`, `is_recoverable`) and
  `ScrapeMonitoringLog` (archive availability, throughput).
- **Gap:** no REST endpoint reads `PageErrorLog`/`ScrapeMonitoringLog` directly, and no frontend
  "completion report" view. This is the main net-new work for the reporting requirement.

### 3.4 Network / proxy layer (for the Mullvad experiment)
- Config: `USE_PROXY`, `PROXY_SERVER`, `PROXY_USERNAME`, `PROXY_PASSWORD`, plus `DECODO_*`
  (`app/core/config.py:238-249,325-329`). Clients check `PROXY_SERVER` truthiness (not `USE_PROXY`).
- Applied in: `wayback_machine.py` (httpx `proxy=`), `archive_org_client.py`,
  `content_extraction_service.py`, `common_crawl_service.py`, `smartproxy_common_crawl_service.py`,
  `common_crawl_proxy_service.py`, `common_crawl_direct_service.py` (proxy→direct fallback).
- **No FlareSolverr, no Cloudflare/CAPTCHA challenge handling anywhere.** HTTP 522/503 are treated
  as retryable errors only. Anti-block today = SmartProxy IP rotation + stealth UA/headers
  (`stealth_headers.py`).

### 3.5 Security notes
- Meilisearch master keys hardcoded in `docker-compose.yml` (lines 29, 98, 193) and in
  `stores/search.ts`.
- Landing page exposes API health to unauthenticated users (from prior memory).

## 4. The plan

Decisions (confirmed with user): strip to scrape-first core; simplify auth to single-user;
add Mullvad **side-by-side and switchable** with Decodo; build everything autonomously.

**Phase 0 — Checkpoint.** Branch + commit the 143 pre-existing modified files so the refactor is
cleanly separable and fully reversible.

**Phase 1 — Simplified scrape-first UI.**
- New front door: one page — enter domain(s) (+ optional date range, archive source) → submit →
  scrape starts. Reuse `TargetConfiguration.svelte` logic; collapse the 4-step wizard to 1.
- Slim the progress page to: live connection indicator, core status counts, results list.
- Simplify auth to a single login (drop registration/verification/approval/admin from the UI).
- Delete: all test/debug routes, dead admin backups, incremental subsystem, zero-import
  components, duplicate progress families, and the tangential feature routes.
- Standardize on the `websocket.ts` store (one WS strategy).

**Phase 2 — Progress, logging & completion reporting.**
- New REST endpoint(s) that read `PageErrorLog` + `ScrapeMonitoringLog` and return a
  completion report: discovered / scraped / failed / filtered counts, per-domain breakdown,
  and a failure list with reasons.
- Frontend "completion report" panel + a live log stream (WebSocket-driven), so the user can
  see progress while running and a clear "everything scraped / N failed because X" at the end.

**Phase 3 — FlareSolverr.**
- Add `flaresolverr` sidecar to compose. Add a fetch fallback: on 403/503/429/challenge
  detection in the content/CDX fetch path, retry the request through FlareSolverr's
  `/v1` `request.get` and feed the returned HTML back into extraction. Config-gated
  (`FLARESOLVERR_ENABLED`, `FLARESOLVERR_URL`).

**Phase 4 — Switchable Decodo / Mullvad WireGuard egress.**
- Add `wg-gateway` sidecar (adapted from munin-community): Mullvad `wg-quick` tunnel, tinyproxy
  `:8888` + dante SOCKS5 `:1080`, **MTU 1280, US exits**, `privileged` + `/dev/net/tun`.
- Mount a directory of Mullvad `.conf` files; select exit via `WG_GATEWAY_CONF`; add
  restart-based rotation + an exit-IP health check.
- Introduce an egress selector (`EGRESS_PROVIDER=decodo|mullvad`) that sets `PROXY_SERVER` to
  either the Decodo endpoint or `http://wg-gateway:8888`, so success rates can be compared
  without code changes.

**Phase 5 — Verify end-to-end.** Bring up the stack, run a real scrape through the new UI,
confirm the report answers "was everything scraped?", verify FlareSolverr handles a challenge,
and confirm traffic egresses through Mullvad (exit-IP check). Run lint + tests.

## 5. Risks & mitigations
- **Deleting shared code** the "kept" pages secretly depend on → verify imports before each
  deletion; the checkpoint commit makes reversal trivial.
- **WireGuard MTU** — Mullvad needs 1280; a higher MTU passes handshake but silently stalls bulk
  transfers (looks like the archive blocking us). Hardcode 1280.
- **`privileged` sidecar** — `wg-gateway` needs `/dev/net/tun`; acceptable for local dev, flagged
  for any production deploy.
- **Not touching backend orphans in this pass** unless they block the UI simplification —
  removing 21 service files is a separate, lower-priority cleanup to avoid conflating risks.
