<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { page } from '$app/stores';
    import { goto } from '$app/navigation';
    import { isAuthenticated, auth } from '$lib/stores/auth';
    import { getApiUrl, formatDate, getRelativeTime, getFileSize } from '$lib/utils';
    import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
    import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
    import { Button } from '$lib/components/ui/button';
    import { Badge } from '$lib/components/ui/badge';
    import { Input } from '$lib/components/ui/input';
    import { 
        Play, 
        Pause,
        BarChart3,
        Globe,
        Calendar,
        Database,
        Search,
        Edit,
        Share,
        Archive,
        Clock,
        Activity,
        FileText,
        AlertTriangle,
        CheckCircle,
        Ban,
        TrendingUp,
        HardDrive,
        Filter,
        ShieldCheck,
        Eye,
        PlayCircle,
        XCircle
    } from 'lucide-svelte';
    import URLProgressResults from '$lib/components/project/URLProgressResults.svelte';
    import URLGroupedResults from '$lib/components/project/URLGroupedResults.svelte';
    import URLProgressFilters from '$lib/components/project/URLProgressFilters.svelte';
    import EnhancedURLProgressCard from '$lib/components/project/EnhancedURLProgressCard.svelte';
    import EnhancedURLProgressFilters from '$lib/components/project/EnhancedURLProgressFilters.svelte';
    import BulkActionToolbar from '$lib/components/project/BulkActionToolbar.svelte';
    import FilteringStatusBadge from '$lib/components/project/FilteringStatusBadge.svelte';
    import EnhancedURLGroupedResults from '$lib/components/project/EnhancedURLGroupedResults.svelte';
    import ErrorBoundary from '$lib/components/ErrorBoundary.svelte';
    import { websocketStore, connectionState, MessageType } from '$lib/stores/websocket';
    import { pageManagementActions } from '$lib/stores/page-management';
    import type { 
        ScrapePage, 
        EnhancedFilters, 
        FilteringAnalysis,
        ScrapeSession,
        BulkAction,
        PageAction,
        ProjectUpdatePayload,
        TaskProgressPayload,
        WebSocketMessage,
        Project,
        ProjectStatsResponse,
        ScrapePageStatus,
        FilterCategory,
        FilterReason
    } from '$lib/types/scraping';
    
    let projectId: string;
    let project: Project | null = null;
    let domains: any[] = []; // TODO: Create proper Domain interface
    let sessions: ScrapeSession[] = [];
    
    // Check for active sessions
    $: hasActiveSession = sessions.some(s => s.status === 'running' || s.status === 'pending');
    let scrapePages: ScrapePage[] = [];
    let scrapePagesStats: Record<string, number> = { 
        total: 0, pending: 0, in_progress: 0, completed: 0, failed: 0, skipped: 0 
    };
    let loading = false;
    let loadingScrapePages = false; // Separate loading flag to prevent infinite loops
    let error = '';
    let searchQuery = '';
    let debounceTimeout: NodeJS.Timeout;
    
    // Enhanced URL Progress specific state
    let urlProgressViewMode: 'list' | 'grid' = 'list';
    let showUrlProgressBulkActions = false;
    let selectedPages: ScrapePage[] = [];
    let showAllUrls: boolean = false; // Toggle to show/hide filtered content
    let enhancedFilters: EnhancedFilters = {
        status: [],
        filterCategory: [],
        sessionId: null,
        searchQuery: '',
        dateRange: { from: null, to: null },
        contentType: [],
        hasErrors: null,
        isManuallyOverridden: null,
        priorityScore: { min: null, max: null },
        showOnlyProcessable: false
    };
    let filteredScrapePages: ScrapePage[] = [];
    let filteringAnalysis: FilteringAnalysis = {
        totalPages: 0,
        filteredPages: 0,
        processablePages: 0,
        overriddenPages: 0,
        statusDistribution: {},
        filterReasonDistribution: {},
        filterCategoryDistribution: {},
        priorityDistribution: { high: 0, normal: 0, low: 0 },
        canBeProcessedCount: 0,
        alreadyOverriddenCount: 0,
        recommendations: []
    };
    
    // Mobile filter panel state
    let mobileFiltersOpen = false;
    
    let stats = {
        total_pages: 0,
        indexed_pages: 0,
        failed_pages: 0,
        total_domains: 0,
        active_sessions: 0,
        storage_used: 0,
        last_scrape: null,
        success_rate: 0
    };
    
    $: projectId = $page.params.id as string;
    
    // Removed problematic reactive statement that caused infinite loops
    // loadScrapePages() is now only called explicitly from loadProject() and event handlers
    
    // WebSocket message handlers for real-time updates
    function handleWebSocketMessage(event: CustomEvent) {
        const message = event.detail;
        
        if (message.type === MessageType.PROJECT_UPDATE && message.payload?.project_id === parseInt(projectId)) {
            // Real-time project updates
            handleProjectUpdate(message.payload);
        } else if (message.type === MessageType.TASK_PROGRESS && message.payload?.project_id === parseInt(projectId)) {
            // Real-time scraping progress updates
            handleScrapingProgressUpdate(message.payload);
        }
    }

    function handleProjectUpdate(payload: ProjectUpdatePayload) {
        // Update project status and statistics
        if (payload.project_status) {
            project.status = payload.project_status;
        }
        
        // Update statistics if provided
        if (payload.stats) {
            projectStats = { ...projectStats, ...payload.stats };
        }
        
        // Reload scrape pages if there are significant changes
        if (payload.should_reload_pages) {
            loadScrapePages(enhancedFilters);
        }
    }

    function handleScrapingProgressUpdate(payload: TaskProgressPayload) {
        // Update individual page statuses
        if (payload.page_updates && Array.isArray(payload.page_updates)) {
            payload.page_updates.forEach((update: any) => {
                const pageIndex = scrapePages.findIndex(p => p.id === update.page_id);
                if (pageIndex !== -1) {
                    // Update the page with new status, filtering info, etc.
                    scrapePages[pageIndex] = { ...scrapePages[pageIndex], ...update };
                    filteredScrapePages = [...filteredScrapePages];
                    
                    // Regenerate filtering analysis
                    filteringAnalysis = generateFilteringAnalysis(scrapePages);
                }
            });
        }

        // Update overall statistics
        if (payload.status_counts) {
            scrapePagesStats = { ...scrapePagesStats, ...payload.status_counts };
        }
    }
    
    onMount(async () => {
        // Initialize auth and check if user is authenticated
        await auth.init();
        
        // Redirect to login if not authenticated
        if (!$isAuthenticated) {
            goto(`/auth/login?redirect=/projects/${projectId}`);
            return;
        }
        
        // Load project data
        await loadProject();
        
        // Enable shared pages API for this project
        pageManagementActions.enableSharedPagesApi(parseInt(projectId));
        
        // Set up WebSocket connection for real-time updates (temporarily disabled)
        // TODO: Fix WebSocket authentication and connection issues
        if (false && $auth.token && $auth.user?.id) {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.hostname;
            // Use port 8000 for backend API, not the frontend development server port
            const wsUrl = `${protocol}//${host}:8000/api/v1/ws/dashboard/${$auth.user.id}`;
            websocketStore.connect(wsUrl, $auth.token);
            
            // Subscribe to project-specific events
            websocketStore.subscribeToChannel(`project_${projectId}`);
        }
        
        // Set up WebSocket event listeners for real-time updates
        if (typeof window !== 'undefined') {
            window.addEventListener('websocket-message', handleWebSocketMessage);
        }
    });
    
    // Cleanup on component destroy
    onDestroy(() => {
        // Clean up WebSocket event listeners
        if (typeof window !== 'undefined') {
            window.removeEventListener('websocket-message', handleWebSocketMessage);
        }
        
        // Unsubscribe from project-specific WebSocket channels
        websocketStore.unsubscribeFromChannel(`project_${projectId}`);
        
        // Clear any polling intervals
        if (pollingInterval) {
            clearInterval(pollingInterval);
        }
    });
    
    // Live updates polling mechanism
    let pollingInterval: NodeJS.Timeout | null = null;
    const POLLING_INTERVAL = 5000; // 5 seconds
    
    // Set up polling for live updates when there are active sessions
    $: if (hasActiveSession && !pollingInterval) {
        console.log('Starting live updates polling (active session detected)');
        pollingInterval = setInterval(async () => {
            try {
                // Only refresh if we're not currently loading to avoid conflicts
                if (!loadingScrapePages && !loading) {
                    await Promise.all([
                        loadScrapePages(urlProgressFilters),
                        loadSessions() // Refresh sessions to keep button states current
                    ]);
                }
            } catch (error) {
                console.error('Error during polling update:', error);
            }
        }, POLLING_INTERVAL);
    } else if (!hasActiveSession && pollingInterval) {
        console.log('Stopping live updates polling (no active sessions)');
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
    
    const loadProject = async () => {
        loading = true;
        try {
            await Promise.all([
                loadProjectDetails(),
                loadProjectStats(),
                loadDomains(),
                loadSessions(),
                loadScrapePages()
            ]);
        } catch (e) {
            error = 'Failed to load project data.';
        } finally {
            loading = false;
        }
    };
    
    const loadProjectDetails = async () => {
        try {
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}`), {
                credentials: 'include'
            });
            
            if (res.ok) {
                project = await res.json();
            } else if (res.status === 404) {
                error = 'Project not found.';
            } else if (res.status === 401) {
                error = 'You are not authorized to view this project.';
            } else {
                error = 'Failed to load project.';
            }
        } catch (e) {
            console.error('Failed to load project:', e);
        }
    };
    
    const loadProjectStats = async () => {
        try {
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/stats`), {
                credentials: 'include'
            });
            
            if (res.ok) {
                stats = await res.json();
            }
        } catch (e) {
            console.error('Failed to load stats:', e);
        }
    };
    
    
    const loadDomains = async () => {
        try {
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/domains`), {
                credentials: 'include'
            });
            
            if (res.ok) {
                domains = await res.json();
                console.log('Domains loaded:', domains.length, domains);
            } else {
                console.error('Failed to load domains:', res.status, res.statusText);
            }
        } catch (e) {
            console.error('Failed to load domains:', e);
        }
    };
    
    const loadSessions = async () => {
        try {
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/sessions`), {
                credentials: 'include'
            });
            
            if (res.ok) {
                sessions = await res.json();
                console.log('Sessions loaded:', sessions.length, sessions);
            } else {
                console.error('Failed to load sessions:', res.status, res.statusText);
            }
        } catch (e) {
            console.error('Failed to load sessions:', e);
        }
    };

    const loadScrapePages = async (filters = enhancedFilters) => {
        // Prevent multiple concurrent calls
        if (loadingScrapePages) {
            console.log('loadScrapePages already running, skipping...');
            return;
        }
        
        loadingScrapePages = true;
        try {
            // Build enhanced query parameters
            const params = new URLSearchParams();
            params.set('limit', '1000');
            params.set('include_filtered', showAllUrls ? 'true' : 'false');
            
            // Status filters (support multiple)
            if (filters.status && filters.status.length > 0) {
                filters.status.forEach(status => {
                    params.append('status', status);
                });
            }
            
            // Filter category filters
            if (filters.filterCategory && filters.filterCategory.length > 0) {
                filters.filterCategory.forEach(category => {
                    params.append('filter_category', category);
                });
            }
            
            if (filters.sessionId) {
                params.set('session_id', filters.sessionId.toString());
            }
            
            // Manual override filters
            if (filters.isManuallyOverridden !== null) {
                params.set('is_manually_overridden', filters.isManuallyOverridden.toString());
            }
            
            // Priority score range
            if (filters.priorityScore.min !== null) {
                params.set('min_priority_score', filters.priorityScore.min.toString());
            }
            if (filters.priorityScore.max !== null) {
                params.set('max_priority_score', filters.priorityScore.max.toString());
            }
            
            // Show only processable pages
            if (filters.showOnlyProcessable) {
                params.set('can_be_manually_processed', 'true');
            }
            
            console.log('Fetching enhanced scrape pages with params:', params.toString());
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/scrape-pages?${params.toString()}`), {
                credentials: 'include'
            });
            
            if (res.ok) {
                const data = await res.json();
                let pages = data.scrape_pages || [];
                const statusCounts = data.status_counts || {};
                
                // Calculate enhanced statistics
                const total = Object.values(statusCounts).reduce((sum: number, count: any) => sum + (count || 0), 0);
                
                scrapePagesStats = {
                    total: total,
                    pending: statusCounts.pending || 0,
                    in_progress: statusCounts.in_progress || 0,
                    completed: statusCounts.completed || 0,
                    failed: statusCounts.failed || 0,
                    skipped: statusCounts.skipped || 0,
                    // Enhanced filtering statistics
                    filtered_duplicate: statusCounts.filtered_duplicate || 0,
                    filtered_list_page: statusCounts.filtered_list_page || 0,
                    filtered_low_quality: statusCounts.filtered_low_quality || 0,
                    filtered_size: statusCounts.filtered_size || 0,
                    filtered_type: statusCounts.filtered_type || 0,
                    filtered_custom: statusCounts.filtered_custom || 0,
                    awaiting_manual_review: statusCounts.awaiting_manual_review || 0,
                    manually_approved: statusCounts.manually_approved || 0
                };
                
                // Apply client-side filters that aren't supported by the API yet
                if (filters.searchQuery) {
                    const query = filters.searchQuery.toLowerCase();
                    pages = pages.filter(page => 
                        page.original_url?.toLowerCase().includes(query) ||
                        page.domain_name?.toLowerCase().includes(query) ||
                        page.error_message?.toLowerCase().includes(query) ||
                        page.filter_reason?.toLowerCase().includes(query) ||
                        page.filter_details?.toLowerCase().includes(query)
                    );
                }
                
                if (filters.contentType && filters.contentType.length > 0) {
                    pages = pages.filter(page => filters.contentType.includes(page.mime_type));
                }
                
                if (filters.hasErrors !== null) {
                    pages = pages.filter(page => 
                        filters.hasErrors ? !!page.error_message : !page.error_message
                    );
                }
                
                if (filters.dateRange.from || filters.dateRange.to) {
                    const fromDate = filters.dateRange.from ? new Date(filters.dateRange.from) : null;
                    const toDate = filters.dateRange.to ? new Date(filters.dateRange.to) : null;
                    
                    pages = pages.filter(page => {
                        const pageDate = new Date(parseInt(page.unix_timestamp) * 1000);
                        if (fromDate && pageDate < fromDate) return false;
                        if (toDate && pageDate > toDate) return false;
                        return true;
                    });
                }
                
                // Generate filtering analysis
                filteringAnalysis = generateFilteringAnalysis(pages);
                
                scrapePages = pages;
                filteredScrapePages = pages;
                console.log('Enhanced scrape pages loaded successfully:', scrapePages.length, scrapePagesStats, filteringAnalysis);
            } else {
                console.error('Failed to load scrape pages:', res.status, res.statusText);
                // Don't reset arrays on failed requests to prevent infinite loops
                if (scrapePages.length === 0) {
                    scrapePages = [];
                    filteredScrapePages = [];
                }
            }
        } catch (e) {
            console.error('Failed to load scrape pages:', e);
            // Don't reset arrays on network errors to prevent infinite loops
            if (scrapePages.length === 0) {
                scrapePages = [];
                filteredScrapePages = [];
            }
        } finally {
            loadingScrapePages = false;
        }
    };
    
    // Enhanced filtering analysis generator
    function generateFilteringAnalysis(pages: ScrapePage[]): FilteringAnalysis {
        const analysis = {
            totalPages: pages.length,
            filteredPages: 0,
            processablePages: 0,
            overriddenPages: 0,
            statusDistribution: {},
            filterReasonDistribution: {},
            filterCategoryDistribution: {},
            priorityDistribution: { high: 0, normal: 0, low: 0 },
            canBeProcessedCount: 0,
            alreadyOverriddenCount: 0,
            recommendations: []
        };
        
        pages.forEach(page => {
            // Count status distribution
            const status = page.status || 'unknown';
            analysis.statusDistribution[status] = (analysis.statusDistribution[status] || 0) + 1;
            
            // Count filtered pages
            if (status.startsWith('filtered_') || status === 'awaiting_manual_review') {
                analysis.filteredPages++;
                
                // Count filter reasons and categories
                if (page.filter_reason) {
                    analysis.filterReasonDistribution[page.filter_reason] = 
                        (analysis.filterReasonDistribution[page.filter_reason] || 0) + 1;
                }
                
                if (page.filter_category) {
                    analysis.filterCategoryDistribution[page.filter_category] = 
                        (analysis.filterCategoryDistribution[page.filter_category] || 0) + 1;
                }
            }
            
            // Count processable pages
            if (page.can_be_manually_processed && !page.is_manually_overridden) {
                analysis.canBeProcessedCount++;
            }
            
            // Count overridden pages
            if (page.is_manually_overridden) {
                analysis.overriddenPages++;
                analysis.alreadyOverriddenCount++;
            }
            
            // Priority distribution
            const priority = page.priority_score || 5;
            if (priority >= 7) analysis.priorityDistribution.high++;
            else if (priority >= 4) analysis.priorityDistribution.normal++;
            else analysis.priorityDistribution.low++;
        });
        
        analysis.processablePages = analysis.canBeProcessedCount;
        
        // Generate recommendations
        if (analysis.canBeProcessedCount > 10) {
            analysis.recommendations.push({
                type: 'bulk_override',
                message: `${analysis.canBeProcessedCount} pages can be manually processed`,
                count: analysis.canBeProcessedCount
            });
        }
        
        if (analysis.filteredPages > analysis.totalPages * 0.5) {
            analysis.recommendations.push({
                type: 'adjust_filters',
                message: 'High filtering rate - consider adjusting filter rules',
                count: analysis.filteredPages
            });
        }
        
        return analysis;
    }
    
    const startScraping = async () => {
        try {
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/scrape`), {
                method: 'POST',
                credentials: 'include'
            });
            
            if (res.ok) {
                await loadProject();
            } else {
                error = 'Failed to start scraping.';
            }
        } catch (e) {
            error = 'Network error while starting scraping.';
        }
    };
    
    const pauseScraping = async () => {
        try {
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/pause`), {
                method: 'POST',
                credentials: 'include'
            });
            
            if (res.ok) {
                await loadProject();
            } else {
                error = 'Failed to pause scraping.';
            }
        } catch (e) {
            error = 'Network error while pausing scraping.';
        }
    };
    
    const handleSearchRedirect = () => {
        const query = searchQuery.trim();
        if (query) {
            try {
                // Redirect to general search page with project filter
                const searchUrl = `/search?project=${projectId}&q=${encodeURIComponent(query)}`;
                goto(searchUrl);
            } catch (error) {
                console.error('Failed to redirect to search:', error);
                // Fallback: could show an error message or alternative action
            }
        }
    };
    

    // Enhanced URL Progress handlers
    function handleEnhancedFiltersChange(event: CustomEvent) {
        enhancedFilters = event.detail;
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(() => {
            loadScrapePages(enhancedFilters);
        }, 300);
    }

    function handleUrlProgressViewModeChange(event: CustomEvent) {
        urlProgressViewMode = event.detail.mode;
    }

    function handleUrlProgressBulkActionsToggle(event: CustomEvent) {
        showUrlProgressBulkActions = event.detail;
    }

    function handleShowAllUrlsToggle(event: CustomEvent) {
        showAllUrls = event.detail;
        loadScrapePages(enhancedFilters);
    }

    // Enhanced page selection handlers
    function handlePageSelect(event: CustomEvent) {
        const { pageId, selected, shiftKey } = event.detail;
        
        if (shiftKey && selectedPages.length > 0) {
            // Handle shift-click range selection
            const lastSelectedIndex = scrapePages.findIndex(p => p.id === selectedPages[selectedPages.length - 1].id);
            const currentIndex = scrapePages.findIndex(p => p.id === pageId);
            
            if (lastSelectedIndex !== -1 && currentIndex !== -1) {
                const start = Math.min(lastSelectedIndex, currentIndex);
                const end = Math.max(lastSelectedIndex, currentIndex);
                
                const rangesToSelect = scrapePages.slice(start, end + 1);
                const newSelected = [...selectedPages];
                
                rangesToSelect.forEach(page => {
                    if (!newSelected.find(p => p.id === page.id)) {
                        newSelected.push(page);
                    }
                });
                
                selectedPages = newSelected;
                return;
            }
        }
        
        // Normal selection
        const page = scrapePages.find(p => p.id === pageId);
        if (!page) return;
        
        if (selected) {
            if (!selectedPages.find(p => p.id === pageId)) {
                selectedPages = [...selectedPages, page];
            }
        } else {
            selectedPages = selectedPages.filter(p => p.id !== pageId);
        }
    }

    function handleSelectAll() {
        selectedPages = [...filteredScrapePages];
    }

    function handleSelectNone() {
        selectedPages = [];
    }

    async function handleUrlProgressPageAction(event: CustomEvent) {
        const { type, pageId, data } = event.detail;
        
        try {
            switch (type) {
                case 'retry':
                    await fetch(getApiUrl(`/api/v1/projects/${projectId}/pages/${pageId}/retry`), {
                        method: 'POST',
                        credentials: 'include'
                    });
                    break;
                case 'skip':
                    await fetch(getApiUrl(`/api/v1/projects/${projectId}/scrape-pages/bulk-skip`), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify([pageId])
                    });
                    break;
                case 'priority':
                    await fetch(getApiUrl(`/api/v1/projects/${projectId}/scrape-pages/bulk-priority`), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify([pageId])
                    });
                    break;
                case 'manual_process':
                    // Process a filtered page manually (override filter and queue for processing)
                    await fetch(getApiUrl(`/api/v1/projects/${projectId}/scrape-pages/${pageId}/manual-process`), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({ 
                            reason: data?.reason || 'Manual override - user decision',
                            force_process: true
                        })
                    });
                    break;
                case 'override_filter':
                    // Override filter decision without processing
                    await fetch(getApiUrl(`/api/v1/projects/${projectId}/scrape-pages/${pageId}/override-filter`), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({ 
                            reason: data?.reason || 'Filter decision overridden by user'
                        })
                    });
                    break;
            }
            // Reload data after action
            await loadScrapePages(enhancedFilters);
        } catch (e) {
            console.error('Enhanced URL progress action failed:', e);
            // Could show user-friendly error toast here
        }
    }

    async function handleUrlProgressBulkAction(event: CustomEvent) {
        const { action, pageIds, data } = event.detail;
        
        if (pageIds.length === 0) return;
        
        try {
            let endpoint = '';
            let requestBody = pageIds;
            
            switch (action) {
                case 'retry':
                    endpoint = 'bulk-retry';
                    break;
                case 'skip':
                    endpoint = 'bulk-skip';
                    break;
                case 'priority':
                    endpoint = 'bulk-priority';
                    break;
                case 'manual_process':
                    endpoint = 'bulk-manual-process';
                    requestBody = { 
                        page_ids: pageIds,
                        reason: data?.reason || 'Bulk manual processing',
                        force_process: true
                    };
                    break;
                case 'override_filter':
                    endpoint = 'bulk-override-filter';
                    requestBody = { 
                        page_ids: pageIds,
                        reason: data?.reason || 'Bulk filter override'
                    };
                    break;
                case 'restore_filter':
                    endpoint = 'bulk-restore-filter';
                    requestBody = { 
                        page_ids: pageIds,
                        reason: data?.reason || 'Restore original filter decisions'
                    };
                    break;
                case 'view_errors':
                    // Handle error viewing (could open modal/dialog)
                    console.log('View errors for pages:', pageIds);
                    return;
                default:
                    console.warn('Unknown bulk action:', action);
                    return;
            }
            
            const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/scrape-pages/${endpoint}`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(requestBody)
            });
            
            if (response.ok) {
                const result = await response.json();
                console.log('Enhanced bulk action result:', result);
                
                // Clear selection after successful bulk action
                selectedPages = [];
                
                // Reload data after bulk action
                await loadScrapePages(enhancedFilters);
                
                // Could show success toast here
                console.log(`Successfully processed ${result.processed_count || pageIds.length} pages`);
            } else {
                const errorData = await response.json();
                console.error('Bulk action failed:', response.status, errorData);
                // Could show error toast here
            }
        } catch (e) {
            console.error('Enhanced bulk action failed:', e);
            // Could show error toast here
        }
    }

    async function handleUrlGroupAction(event: CustomEvent) {
        const { action, urlGroup, pageIds } = event.detail;
        console.log('Group action:', action, 'for URL:', urlGroup, 'pageIds:', pageIds);
        
        if (pageIds.length === 0) return;
        
        try {
            let endpoint = '';
            switch (action) {
                case 'retry':
                    endpoint = 'bulk-retry';
                    break;
                case 'skip':
                    endpoint = 'bulk-skip';
                    break;
                case 'priority':
                    endpoint = 'bulk-priority';
                    break;
                default:
                    return;
            }
            
            const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/scrape-pages/${endpoint}`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(pageIds)
            });
            
            if (response.ok) {
                const result = await response.json();
                console.log('Group action result:', result);
                // Reload data after group action
                await loadScrapePages(urlProgressFilters);
            }
        } catch (e) {
            console.error('Group action failed:', e);
        }
    }

    function handleUrlGroupSelect(event: CustomEvent) {
        const { urlGroup, selected } = event.detail;
        console.log('Group selection:', urlGroup, selected);
        // Group selection is handled internally by the component
        // but we can add additional logic here if needed
    }
    
    const editProject = () => {
        goto(`/projects/${projectId}/edit`);
    };
    
    const shareProject = () => {
        goto(`/projects/${projectId}/share`);
    };
    
    const viewAnalytics = () => {
        goto(`/projects/${projectId}/analytics`);
    };
    
    const viewDomain = (domainId: string) => {
        goto(`/projects/${projectId}/domains/${domainId}`);
    };
    
    
    const getStatusColor = (status: string | undefined) => {
        switch (status?.toLowerCase()) {
            case 'indexing':
            case 'active':
                return 'default';
            case 'paused':
                return 'secondary';
            case 'completed':
                return 'outline';
            case 'failed':
            case 'error':
                return 'destructive';
            default:
                return 'secondary';
        }
    };
    
</script>

<svelte:head>
    <title>{project?.name || 'Project'} - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
    <ErrorBoundary 
        context="Project Detail Page" 
        showDetails={true}
        onRetry={() => loadProject()}
    >
        <div class="space-y-6">
        {#if loading && !project}
            <!-- Loading skeleton -->
            <div class="space-y-6">
                <div class="animate-pulse">
                    <div class="h-8 bg-gray-200 rounded w-1/3 mb-2"></div>
                    <div class="h-4 bg-gray-200 rounded w-1/2"></div>
                </div>
                <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                    {#each Array(4) as _}
                        <Card class="animate-pulse">
                            <CardContent class="pt-6">
                                <div class="h-8 bg-gray-200 rounded w-16 mb-2"></div>
                                <div class="h-4 bg-gray-200 rounded w-24"></div>
                            </CardContent>
                        </Card>
                    {/each}
                </div>
            </div>
        {:else if error}
            <Card class="border-destructive">
                <CardContent class="pt-6">
                    <div class="flex items-center space-x-2 text-destructive">
                        <AlertTriangle class="h-5 w-5" />
                        <p>{error}</p>
                    </div>
                </CardContent>
            </Card>
        {:else if project}
            <!-- Header -->
            <div class="space-y-4">
                <div class="space-y-3">
                    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                        <div class="space-y-1">
                            <div class="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
                                <h2 class="text-2xl sm:text-3xl font-bold tracking-tight break-words">{project.name}</h2>
                                <Badge variant={getStatusColor(project.status)} class="self-start">
                                    {project.status || 'No Index'}
                                </Badge>
                            </div>
                            {#if project.description}
                                <p class="text-muted-foreground text-sm sm:text-base">
                                    {project.description}
                                </p>
                            {/if}
                        </div>
                        <!-- Mobile action buttons -->
                        <div class="flex flex-col sm:hidden gap-2 w-full">
                            <button 
                                class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2 w-full"
                                onclick={viewAnalytics}
                            >
                                <BarChart3 class="mr-2 h-4 w-4" />
                                Analytics
                            </button>
                            <button 
                                class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2 w-full"
                                onclick={shareProject}
                            >
                                <Share class="mr-2 h-4 w-4" />
                                Share
                            </button>
                            <button 
                                class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2 w-full"
                                onclick={editProject}
                            >
                                <Edit class="mr-2 h-4 w-4" />
                                Edit
                            </button>
                            {#if sessions.some(s => s.status === 'running' || s.status === 'pending')}
                                <!-- Show pause and stop when there's an active session -->
                                <button 
                                    class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2 w-full"
                                    onclick={pauseScraping}
                                >
                                    <Pause class="mr-2 h-4 w-4" />
                                    Pause
                                </button>
                            {:else if project.status !== 'completed'}
                                <!-- Show start scraping button when no active session and project not completed -->
                                <button 
                                    class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2 w-full"
                                    onclick={startScraping}
                                    aria-label="Start scraping session for this project"
                                    title="Begin scraping web pages for this project"
                                >
                                    <Play class="mr-2 h-4 w-4" aria-hidden="true" />
                                    Start Scraping
                                </button>
                            {/if}
                        </div>
                        <!-- Desktop action buttons -->
                        <div class="hidden sm:flex gap-2">
                            <button 
                                class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2"
                                onclick={viewAnalytics}
                            >
                                <BarChart3 class="mr-2 h-4 w-4" />
                                Analytics
                            </button>
                            <button 
                                class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2"
                                onclick={shareProject}
                            >
                                <Share class="mr-2 h-4 w-4" />
                                Share
                            </button>
                            <button 
                                class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2"
                                onclick={editProject}
                            >
                                <Edit class="mr-2 h-4 w-4" />
                                Edit
                            </button>
                            {#if sessions.some(s => s.status === 'running' || s.status === 'pending')}
                                <!-- Show pause and stop when there's an active session -->
                                <button 
                                    class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2"
                                    onclick={pauseScraping}
                                >
                                    <Pause class="mr-2 h-4 w-4" />
                                    Pause
                                </button>
                            {:else if project.status !== 'completed'}
                                <!-- Show start scraping button when no active session and project not completed -->
                                <button 
                                    class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2"
                                    onclick={startScraping}
                                    aria-label="Start scraping session for this project"
                                    title="Begin scraping web pages for this project"
                                >
                                    <Play class="mr-2 h-4 w-4" aria-hidden="true" />
                                    Start Scraping
                                </button>
                            {/if}
                            <!-- No buttons shown when project is completed and no active sessions -->
                        </div>
                    </div>
                    
                    <!-- Project metadata -->
                    <div class="flex flex-wrap items-center gap-3 sm:gap-4 text-sm text-muted-foreground">
                        <div class="flex items-center">
                            <Calendar class="mr-1 h-3 w-3" />
                            <span class="truncate">Created {formatDate(project.created_at)}</span>
                        </div>
                        <div class="flex items-center">
                            <Globe class="mr-1 h-3 w-3" />
                            {stats.total_domains || 0} {stats.total_domains === 1 ? 'target' : 'targets'}
                        </div>
                        <div class="flex items-center">
                            <Database class="mr-1 h-3 w-3" />
                            {getFileSize(stats.storage_used || 0)} used
                        </div>
                        {#if stats.last_scrape}
                            <div class="flex items-center">
                                <Clock class="mr-1 h-3 w-3" />
                                <span class="truncate">Last scraped {getRelativeTime(stats.last_scrape)}</span>
                            </div>
                        {/if}
                    </div>
                </div>
            </div>
            
            
            
            <!-- Search Existing Pages -->
            <div class="space-y-3">
                <div>
                    <h3 class="text-lg font-semibold">Search Scraped Content</h3>
                    <p class="text-sm text-muted-foreground">Search through pages that have already been scraped and indexed</p>
                </div>
                <div class="flex flex-col sm:flex-row gap-2 sm:space-x-2">
                    <div class="flex-1 relative">
                        <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                        <Input
                            bind:value={searchQuery}
                            on:keydown={(e) => e.key === 'Enter' && handleSearchRedirect()}
                            placeholder="Search content, titles, or URLs in scraped pages..."
                            class="pl-10"
                        />
                    </div>
                    <Button onclick={handleSearchRedirect} disabled={!searchQuery.trim()} class="w-full sm:w-auto">
                        <Search class="mr-2 h-4 w-4" />
                        Search Pages
                    </Button>
                </div>
            </div>
            
            <!-- Scraping Progress Section -->
            <div class="space-y-2">
                <div class="flex items-center justify-between">
                    <div>
                        <h3 class="text-xl font-semibold">Scraping Progress</h3>
                        <p class="text-sm text-muted-foreground">Live status of URLs being discovered and processed</p>
                    </div>
                    <div class="flex items-center space-x-2">
                        <div class="flex items-center space-x-1">
                            <div class="w-2 h-2 rounded-full {$connectionState === 'connected' ? 'bg-green-500' : $connectionState === 'connecting' || $connectionState === 'reconnecting' ? 'bg-yellow-500 animate-pulse' : 'bg-red-500'}"></div>
                            <span class="text-xs text-muted-foreground">
                                {$connectionState === 'connected' ? 'Real-time updates enabled' : 
                                 $connectionState === 'connecting' || $connectionState === 'reconnecting' ? 'Connecting...' : 
                                 'Updates disabled'}
                            </span>
                        </div>
                    </div>
                </div>
                
                <!-- Targets List -->
                {#if domains && domains.length > 0}
                    <div class="flex items-center gap-2 text-sm text-muted-foreground">
                        <Globe class="h-3 w-3" />
                        <span>Targets:</span>
                        <div class="flex flex-wrap items-center gap-1">
                            {#each domains.slice(0, 3) as domain, index}
                                <span class="text-foreground font-medium cursor-pointer hover:underline" 
                                      onclick={() => domain.id && viewDomain(domain.id)}>
                                    {domain.domain_name || 'Unknown Domain'}
                                </span>
                                {#if index < Math.min(domains.length, 3) - 1}<span>,</span>{/if}
                            {/each}
                            {#if domains.length > 3}
                                <span>and {domains.length - 3} more</span>
                            {/if}
                        </div>
                    </div>
                {/if}
            </div>
            
            <!-- Project Overview Statistics -->
            <div class="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Pages Indexed</CardTitle>
                        <FileText class="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold">{stats.total_pages || 0}</div>
                        <p class="text-xs text-muted-foreground">
                            <Database class="inline h-3 w-3 mr-1" />
                            Searchable content
                        </p>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Success Rate</CardTitle>
                        <TrendingUp class="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold">{stats.success_rate || 0}%</div>
                        <p class="text-xs text-muted-foreground">
                            <CheckCircle class="inline h-3 w-3 mr-1" />
                            Extraction quality
                        </p>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Active Sessions</CardTitle>
                        <Activity class="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold">{stats.active_sessions || 0}</div>
                        <p class="text-xs text-muted-foreground">
                            <Clock class="inline h-3 w-3 mr-1" />
                            Currently running
                        </p>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Storage Used</CardTitle>
                        <HardDrive class="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold">{getFileSize(stats.storage_used || 0)}</div>
                        <p class="text-xs text-muted-foreground">
                            <Archive class="inline h-3 w-3 mr-1" />
                            Content archive
                        </p>
                    </CardContent>
                </Card>
            </div>
            
            <!-- URL Processing Details -->
            <div class="space-y-2">
                <div>
                    <h3 class="text-lg font-semibold">URL Processing Status</h3>
                    <p class="text-sm text-muted-foreground">Real-time breakdown of individual URL processing</p>
                </div>
            </div>

            <!-- Enhanced URL Processing Statistics -->
            <div class="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8">
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Total URLs</CardTitle>
                        <Archive class="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold">{scrapePagesStats.total || 0}</div>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Pending</CardTitle>
                        <Clock class="h-4 w-4 text-yellow-500" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold text-yellow-600">{scrapePagesStats.pending || 0}</div>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">In Progress</CardTitle>
                        <Activity class="h-4 w-4 text-blue-500" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold text-blue-600">{scrapePagesStats.in_progress || 0}</div>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Completed</CardTitle>
                        <CheckCircle class="h-4 w-4 text-green-500" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold text-green-600">{scrapePagesStats.completed || 0}</div>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Failed</CardTitle>
                        <AlertTriangle class="h-4 w-4 text-red-500" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold text-red-600">{scrapePagesStats.failed || 0}</div>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Skipped</CardTitle>
                        <Ban class="h-4 w-4 text-gray-500" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold text-gray-600">{scrapePagesStats.skipped || 0}</div>
                    </CardContent>
                </Card>

                <!-- Enhanced filtering statistics -->
                <Card class="border-amber-200 bg-amber-50">
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium text-amber-800">Filtered</CardTitle>
                        <Filter class="h-4 w-4 text-amber-600" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold text-amber-700">
                            {(scrapePagesStats.filtered_duplicate || 0) + 
                             (scrapePagesStats.filtered_list_page || 0) + 
                             (scrapePagesStats.filtered_low_quality || 0) + 
                             (scrapePagesStats.filtered_size || 0) + 
                             (scrapePagesStats.filtered_type || 0) + 
                             (scrapePagesStats.filtered_custom || 0)}
                        </div>
                        <p class="text-xs text-amber-600">
                            {filteringAnalysis.canBeProcessedCount} processable
                        </p>
                    </CardContent>
                </Card>

                <Card class="border-green-200 bg-green-50">
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium text-green-800">Overridden</CardTitle>
                        <ShieldCheck class="h-4 w-4 text-green-600" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold text-green-700">
                            {(scrapePagesStats.manually_approved || 0) + filteringAnalysis.alreadyOverriddenCount}
                        </div>
                        <p class="text-xs text-green-600">Manual decisions</p>
                    </CardContent>
                </Card>
            </div>
            
            <!-- Enhanced Filtering Insights -->
            {#if filteringAnalysis.filteredPages > 0}
                <Card class="border-amber-200 bg-amber-50">
                    <CardHeader>
                        <CardTitle class="text-base flex items-center gap-2 text-amber-800">
                            <Filter class="h-4 w-4" />
                            Filtering Analysis
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                            <div class="space-y-2">
                                <div class="text-sm font-medium text-amber-800">Filter Breakdown</div>
                                <div class="space-y-1 text-xs text-amber-700">
                                    {#each Object.entries(filteringAnalysis.filterCategoryDistribution) as [category, count]}
                                        <div class="flex justify-between">
                                            <span>{category.replace('_', ' ')}</span>
                                            <span class="font-mono">{count}</span>
                                        </div>
                                    {/each}
                                </div>
                            </div>
                            
                            <div class="space-y-2">
                                <div class="text-sm font-medium text-amber-800">Priority Distribution</div>
                                <div class="space-y-1 text-xs text-amber-700">
                                    <div class="flex justify-between">
                                        <span>High (7-10)</span>
                                        <span class="font-mono">{filteringAnalysis.priorityDistribution.high}</span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span>Normal (4-6)</span>
                                        <span class="font-mono">{filteringAnalysis.priorityDistribution.normal}</span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span>Low (1-3)</span>
                                        <span class="font-mono">{filteringAnalysis.priorityDistribution.low}</span>
                                    </div>
                                </div>
                            </div>
                            
                            {#if filteringAnalysis.recommendations.length > 0}
                                <div class="space-y-2">
                                    <div class="text-sm font-medium text-amber-800">Recommendations</div>
                                    <div class="space-y-1 text-xs text-amber-700">
                                        {#each filteringAnalysis.recommendations as rec}
                                            <div class="flex items-start gap-1">
                                                <div class="w-1.5 h-1.5 rounded-full bg-amber-400 mt-1.5 flex-shrink-0"></div>
                                                <span>{rec.message}</span>
                                            </div>
                                        {/each}
                                    </div>
                                </div>
                            {/if}
                        </div>
                    </CardContent>
                </Card>
            {/if}
            
            <!-- Scraping Progress Interface -->
            <div class="flex flex-col lg:flex-row gap-6 min-w-0">
                <!-- Main Results Area -->
                <div class="flex-1 min-w-0 space-y-4">
                    {#if loading && filteredScrapePages.length === 0}
                        <!-- Loading state for scrape pages -->
                        <div class="space-y-4">
                            <div class="flex items-center justify-between">
                                <div class="animate-pulse h-6 bg-gray-200 rounded w-32"></div>
                                <div class="animate-pulse h-8 bg-gray-200 rounded w-24"></div>
                            </div>
                            {#each Array(5) as _}
                                <Card class="animate-pulse">
                                    <CardContent class="pt-6">
                                        <div class="space-y-2">
                                            <div class="h-4 bg-gray-200 rounded w-3/4"></div>
                                            <div class="h-3 bg-gray-200 rounded w-1/2"></div>
                                            <div class="h-3 bg-gray-200 rounded w-1/4"></div>
                                        </div>
                                    </CardContent>
                                </Card>
                            {/each}
                        </div>
                    {:else}
                        <!-- Enhanced Bulk Action Toolbar -->
                        <BulkActionToolbar
                            selectedCount={selectedPages.length}
                            selectedPages={selectedPages}
                            showToolbar={showUrlProgressBulkActions && selectedPages.length > 0}
                            on:bulkAction={handleUrlProgressBulkAction}
                            on:clearSelection={handleSelectNone}
                            on:selectAll={handleSelectAll}
                            on:selectNone={handleSelectNone}
                        />
                        
                        <EnhancedURLGroupedResults
                            scrapePages={filteredScrapePages}
                            selectedPages={selectedPages}
                            loading={loadingScrapePages}
                            error={error}
                            searchQuery={enhancedFilters.searchQuery}
                            viewMode={urlProgressViewMode}
                            showBulkActions={showUrlProgressBulkActions}
                            showAllUrls={showAllUrls}
                            filteringAnalysis={filteringAnalysis}
                            on:viewModeChange={handleUrlProgressViewModeChange}
                            on:bulkActionsToggle={handleUrlProgressBulkActionsToggle}
                            on:showAllUrlsToggle={handleShowAllUrlsToggle}
                            on:pageAction={handleUrlProgressPageAction}
                            on:pageSelect={handlePageSelect}
                            on:bulkAction={handleUrlProgressBulkAction}
                            on:groupAction={handleUrlGroupAction}
                            on:groupSelect={handleUrlGroupSelect}
                            on:selectAll={handleSelectAll}
                            on:selectNone={handleSelectNone}
                        />
                    {/if}
                </div>
                
                <!-- Filters Sidebar -->
                <div class="lg:w-80 xl:w-80 shrink-0">
                    <!-- Mobile Filter Toggle -->
                    <div class="block lg:hidden mb-4">
                        <Button 
                            variant="outline" 
                            class="w-full" 
                            onclick={() => mobileFiltersOpen = true}
                            aria-label="Open filtering options"
                            aria-expanded={mobileFiltersOpen}
                            aria-controls="mobile-filters-panel"
                        >
                            <Search class="mr-2 h-4 w-4" aria-hidden="true" />
                            Show Filters
                        </Button>
                    </div>
                    
                    <!-- Desktop Enhanced Filters -->
                    <div class="hidden lg:block">
                        <EnhancedURLProgressFilters 
                            projectId={parseInt(projectId)}
                            sessions={sessions}
                            on:filtersChange={handleEnhancedFiltersChange}
                        />
                    </div>
                </div>
            </div>
            
        {/if}
    </div>
    
    <!-- Mobile Filters Modal (Simplified) -->
    {#if mobileFiltersOpen}
        <div 
            class="fixed inset-0 z-50 lg:hidden"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mobile-filters-title"
        >
            <!-- Backdrop -->
            <div 
                class="fixed inset-0 bg-background/80 backdrop-blur-sm" 
                onclick={() => mobileFiltersOpen = false}
                aria-label="Close filters dialog"
            ></div>
            
            <!-- Modal content -->
            <div 
                id="mobile-filters-panel"
                class="fixed bottom-0 left-0 right-0 bg-background border-t border-border rounded-t-lg shadow-lg"
                role="document"
            >
                <div class="flex items-center justify-between p-4 border-b border-border">
                    <h3 
                        id="mobile-filters-title" 
                        class="text-lg font-semibold"
                    >
                        Filters
                    </h3>
                    <button 
                        class="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 hover:bg-accent hover:text-accent-foreground h-10 w-10"
                        onclick={() => mobileFiltersOpen = false}
                        aria-label="Close filters dialog"
                        type="button"
                    >
                        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>
                <div class="max-h-[70vh] overflow-y-auto p-4">
                    <EnhancedURLProgressFilters 
                        projectId={parseInt(projectId)}
                        sessions={sessions}
                        on:filtersChange={handleEnhancedFiltersChange}
                    />
                </div>
            </div>
        </div>
    {/if}
    </ErrorBoundary>
</DashboardLayout>

