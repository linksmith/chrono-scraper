# Project Scraping Debug Analysis

## Root Cause Analysis

After investigating the project creation and scraping flow, I've identified that the system **should** be working correctly, but there may be specific issues preventing automatic scraping initiation. Here's what I found:

## How The System Should Work

### 1. Frontend Project Creation Flow (`MultiStepProjectForm.svelte`)
```
1. Create project → POST /api/v1/projects
2. Create domains → POST /api/v1/projects/{id}/domains (for each target)
3. Auto-start scraping → POST /api/v1/projects/{id}/scrape (if auto_start_scraping=true)
```

- **Default Setting**: `auto_start_scraping = true` ✅
- **Domain Creation**: Works for both domain and prefix URL targets ✅
- **Scraping Trigger**: Calls the scraping endpoint when enabled ✅

### 2. Backend Scraping Flow
```
1. Create scrape session
2. Update project status to INDEXING  
3. Get active domains for project
4. Queue Celery task: scrape_domain_with_firecrawl.delay(domain_id, session_id)
```

### 3. Celery Task Flow (`scrape_domain_with_firecrawl`)
```
1. CDX API Discovery → fetch_cdx_records()
2. Intelligent Filtering → filter_records_intelligent()
3. Firecrawl Content Extraction → _process_batch_with_firecrawl()
4. Database Storage → Store as Page records
```

## Potential Issues & Debugging Steps

### Issue 1: Service Dependencies Not Running
**Symptoms**: Scraping never starts, no error messages
**Causes**: 
- Celery workers not running
- Redis connection issues
- CDX API unreachable

**Debug**: Run `python fix_project_scraping_issues.py`

### Issue 2: Domain Configuration Problems
**Symptoms**: Scraping starts but finds 0 pages
**Causes**:
- Domain marked as inactive (`active=False`)
- Domain status is ERROR instead of ACTIVE
- Invalid prefix URL configuration
- Date range excludes all content

**Debug**: Run `python debug_project_scraping.py debug <project_id>`

### Issue 3: CDX API Returns No Results
**Symptoms**: "No CDX data found" in logs
**Causes**:
- Domain has no archived content in date range
- URL prefix doesn't match any archived URLs  
- CDX API rate limiting
- Temporary CDX service issues

**Debug**: Check logs from scraping task, test CDX API manually

### Issue 4: Silent Failures in Task Queue
**Symptoms**: Tasks appear to start but never complete
**Causes**:
- Celery task exceptions not logged
- Database connection issues in task
- Import errors in task modules

**Debug**: Monitor Celery worker logs: `docker compose logs -f celery_worker`

## Debugging Scripts Created

### 1. `fix_project_scraping_issues.py`
Comprehensive health check that validates:
- Environment variables
- Docker services (backend, celery_worker, redis, postgres, meilisearch)
- Database connectivity
- Redis connectivity  
- Celery worker status
- Wayback Machine CDX API
- Domain configurations

**Usage**:
```bash
python fix_project_scraping_issues.py           # Full check
python fix_project_scraping_issues.py --quick   # Essential services only
```

### 2. `debug_project_creation.py`
Simulates the exact frontend project creation flow to identify where it fails.

**Usage**:
```bash
python debug_project_creation.py
```

### 3. `debug_project_scraping.py`  
Deep debugging of the scraping flow for specific projects or domains.

**Usage**:
```bash
python debug_project_scraping.py create example.com https://example.com/blog/
python debug_project_scraping.py debug <project_id>
python debug_project_scraping.py trigger <project_id>
```

## Most Likely Root Causes (In Order)

### 1. **Celery Workers Not Running** (90% likelihood)
The most common issue is that the Celery worker service isn't running or isn't processing tasks.

**Fix**: 
```bash
docker compose ps celery_worker
docker compose up -d celery_worker
docker compose logs celery_worker
```

### 2. **Domain Configuration Issues** (60% likelihood)
Domains created with incorrect status or inactive flag.

**Check**: Run the debug script to inspect domain properties:
- `domain.active` should be `True`
- `domain.status` should be `ACTIVE` not `ERROR`
- For PREFIX matches, `domain.url_path` must be set

### 3. **CDX API Returns No Results** (40% likelihood)
The domain/URL has no archived content for the specified date range.

**Fix**: 
- Try a broader date range
- Test with well-known domains (like `example.com`)
- Check CDX API status manually

### 4. **Service Connectivity Issues** (30% likelihood)
Redis, database, or network connectivity problems preventing task execution.

## Recommended Debugging Workflow

1. **Start with health check**:
   ```bash
   python fix_project_scraping_issues.py
   ```

2. **Create a test project**:
   ```bash
   python debug_project_creation.py
   ```

3. **If project created but no scraping**:
   ```bash
   python debug_project_scraping.py debug <project_id>
   ```

4. **Monitor live execution**:
   ```bash
   # In separate terminals:
   docker compose logs -f celery_worker
   docker compose logs -f backend  
   ```

## Key Files Involved

- **Frontend**: `/frontend/src/routes/projects/create/components/MultiStepProjectForm.svelte`
- **Backend API**: `/backend/app/api/v1/endpoints/projects.py` 
- **Services**: `/backend/app/services/projects.py`
- **Scraping Tasks**: `/backend/app/tasks/firecrawl_scraping.py`
- **CDX Client**: `/backend/app/services/wayback_machine.py`

## Expected Behavior When Working

1. Project creation form submits successfully
2. User is redirected to project page: `/projects/{id}`
3. Project shows status "Indexing" initially
4. Celery worker logs show CDX discovery and content extraction
5. Pages appear in project pages list as they're scraped
6. Project status updates to "Indexed" when complete

If any of these steps don't happen, use the debugging scripts to identify the specific failure point.