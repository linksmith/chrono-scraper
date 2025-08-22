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
        Ban
    } from 'lucide-svelte';
    import URLProgressResults from '$lib/components/project/URLProgressResults.svelte';
    import URLGroupedResults from '$lib/components/project/URLGroupedResults.svelte';
    import URLProgressFilters from '$lib/components/project/URLProgressFilters.svelte';
    import { websocketStore, connectionState, MessageType } from '$lib/stores/websocket';
    import { pageManagementActions } from '$lib/stores/page-management';
    
    let projectId: string;
    let project: any = null;
    let domains: any[] = [];
    let sessions: any[] = [];
    
    // Check for active sessions
    $: hasActiveSession = sessions.some(s => s.status === 'running' || s.status === 'pending');
    let scrapePages: any[] = [];
    let scrapePagesStats = { total: 0, pending: 0, in_progress: 0, completed: 0, failed: 0, skipped: 0 };
    let loading = false;
    let loadingScrapePages = false; // Separate loading flag to prevent infinite loops
    let error = '';
    let searchQuery = '';
    let debounceTimeout: NodeJS.Timeout;
    
    // URL Progress specific state
    let urlProgressViewMode: 'list' | 'grid' = 'list';
    let showUrlProgressBulkActions = false;
    let urlProgressFilters = {
        status: [],
        sessionId: null,
        searchQuery: '',
        dateRange: { from: null, to: null },
        contentType: [],
        hasErrors: null
    };
    let filteredScrapePages: any[] = [];
    
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
    
    // WebSocket event listener reference
    let handleWebSocketMessage: (event: CustomEvent) => void;
    
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
        
        // Set up event listeners for real-time scrape page updates
        handleWebSocketMessage = async (event: CustomEvent) => {
            const message = event.detail;
            console.log('WebSocket message received:', message);
            
            // Handle scrape page status updates
            if (message.type === MessageType.TASK_PROGRESS || message.type === MessageType.PROJECT_UPDATE) {
                if (message.payload?.project_id === parseInt(projectId)) {
                    try {
                        // Refresh scrape pages data and stats when updates are received
                        await Promise.all([
                            loadScrapePages(urlProgressFilters),
                            loadProjectStats(),
                            loadSessions() // Update sessions to refresh button state
                        ]);
                    } catch (error) {
                        console.error('Error updating data from WebSocket message:', error);
                    }
                }
            }
        };
        
        // Add WebSocket event listener
        window.addEventListener('websocket-message', handleWebSocketMessage);
    });
    
    // Cleanup on component destroy
    onDestroy(() => {
        if (handleWebSocketMessage) {
            window.removeEventListener('websocket-message', handleWebSocketMessage);
        }
        websocketStore.unsubscribeFromChannel(`project_${projectId}`);
    });
    
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

    const loadScrapePages = async (filters = urlProgressFilters) => {
        // Prevent multiple concurrent calls
        if (loadingScrapePages) {
            console.log('loadScrapePages already running, skipping...');
            return;
        }
        
        loadingScrapePages = true;
        try {
            // Build query parameters
            const params = new URLSearchParams();
            params.set('limit', '1000');
            
            if (filters.status && filters.status.length > 0) {
                // Note: API currently supports single status, we'll use the first one
                params.set('status', filters.status[0]);
            }
            
            if (filters.sessionId) {
                params.set('session_id', filters.sessionId.toString());
            }
            
            console.log('Fetching scrape pages with params:', params.toString());
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/scrape-pages?${params.toString()}`), {
                credentials: 'include'
            });
            
            if (res.ok) {
                const data = await res.json();
                let pages = data.scrape_pages || [];
                const statusCounts = data.status_counts || {};
                
                // Calculate total from status counts
                const total = Object.values(statusCounts).reduce((sum: number, count: any) => sum + (count || 0), 0);
                
                scrapePagesStats = {
                    total: total,
                    pending: statusCounts.pending || 0,
                    in_progress: statusCounts.in_progress || 0,
                    completed: statusCounts.completed || 0,
                    failed: statusCounts.failed || 0,
                    skipped: statusCounts.skipped || 0
                };
                
                // Apply client-side filters that aren't supported by the API yet
                if (filters.searchQuery) {
                    const query = filters.searchQuery.toLowerCase();
                    pages = pages.filter(page => 
                        page.original_url?.toLowerCase().includes(query) ||
                        page.domain_name?.toLowerCase().includes(query) ||
                        page.error_message?.toLowerCase().includes(query)
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
                
                scrapePages = pages;
                filteredScrapePages = pages;
                console.log('Scrape pages loaded successfully:', scrapePages.length, scrapePagesStats);
            } else {
                console.error('Failed to load scrape pages:', res.status, res.statusText);
                // Don't reset arrays on failed requests to prevent infinite loops
                if (scrapePages.length === 0) {
                    // Only set empty arrays on first load failure
                    scrapePages = [];
                    filteredScrapePages = [];
                }
            }
        } catch (e) {
            console.error('Failed to load scrape pages:', e);
            // Don't reset arrays on network errors to prevent infinite loops
            if (scrapePages.length === 0) {
                // Only set empty arrays on first load failure
                scrapePages = [];
                filteredScrapePages = [];
            }
        } finally {
            loadingScrapePages = false;
        }
    };
    
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
    

    // URL Progress handlers
    function handleUrlProgressFiltersChange(event: CustomEvent) {
        urlProgressFilters = event.detail;
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(() => {
            loadScrapePages(urlProgressFilters);
        }, 300);
    }

    function handleUrlProgressViewModeChange(event: CustomEvent) {
        urlProgressViewMode = event.detail.mode;
    }

    function handleUrlProgressBulkActionsToggle(event: CustomEvent) {
        showUrlProgressBulkActions = event.detail;
    }

    async function handleUrlProgressPageAction(event: CustomEvent) {
        const { type, pageId } = event.detail;
        
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
            }
            // Reload data after action
            await loadScrapePages(urlProgressFilters);
        } catch (e) {
            console.error('URL progress action failed:', e);
        }
    }

    async function handleUrlProgressBulkAction(event: CustomEvent) {
        const { action, pageIds } = event.detail;
        
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
                console.log('Bulk action result:', result);
                // Reload data after bulk action
                await loadScrapePages(urlProgressFilters);
            }
        } catch (e) {
            console.error('Bulk action failed:', e);
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
            <div class="flex items-start justify-between">
                <div class="space-y-1">
                    <div class="flex items-center gap-3">
                        <h2 class="text-3xl font-bold tracking-tight">{project.name}</h2>
                        <Badge variant={getStatusColor(project.status)}>
                            {project.status || 'No Index'}
                        </Badge>
                    </div>
                    {#if project.description}
                        <p class="text-muted-foreground">
                            {project.description}
                        </p>
                    {/if}
                    <div class="flex items-center gap-4 text-sm text-muted-foreground">
                        <div class="flex items-center">
                            <Calendar class="mr-1 h-3 w-3" />
                            Created {formatDate(project.created_at)}
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
                                Last scraped {getRelativeTime(stats.last_scrape)}
                            </div>
                        {/if}
                    </div>
                </div>
                <div class="flex gap-2">
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
                        >
                            <Play class="mr-2 h-4 w-4" />
                            Start Scraping
                        </button>
                    {/if}
                    <!-- No buttons shown when project is completed and no active sessions -->
                </div>
            </div>
            
            
            
            <!-- Search Existing Pages -->
            <div class="space-y-3">
                <div>
                    <h3 class="text-lg font-semibold">Search Scraped Content</h3>
                    <p class="text-sm text-muted-foreground">Search through pages that have already been scraped and indexed</p>
                </div>
                <div class="flex space-x-2">
                    <div class="flex-1 relative">
                        <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                        <Input
                            bind:value={searchQuery}
                            on:keydown={(e) => e.key === 'Enter' && handleSearchRedirect()}
                            placeholder="Search content, titles, or URLs in scraped pages..."
                            class="pl-10"
                        />
                    </div>
                    <Button onclick={handleSearchRedirect} disabled={!searchQuery.trim()}>
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
            
            <!-- Scraping Statistics -->
            <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-6">
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
            </div>
            
            <!-- Scraping Progress Interface -->
            <div class="flex gap-6 min-w-0">
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
                        <URLGroupedResults
                            scrapePages={filteredScrapePages}
                            loading={loading}
                            error={error}
                            searchQuery={urlProgressFilters.searchQuery}
                            viewMode={urlProgressViewMode}
                            showBulkActions={showUrlProgressBulkActions}
                            on:viewModeChange={handleUrlProgressViewModeChange}
                            on:bulkActionsToggle={handleUrlProgressBulkActionsToggle}
                            on:pageAction={handleUrlProgressPageAction}
                            on:pageSelect={(e) => console.log('Page selected:', e.detail)}
                            on:bulkAction={handleUrlProgressBulkAction}
                            on:groupAction={handleUrlGroupAction}
                            on:groupSelect={handleUrlGroupSelect}
                        />
                    {/if}
                </div>
                
                <!-- Filters Sidebar (desktop) -->
                <div class="hidden md:block w-80 xl:w-80 lg:w-72 md:w-64 shrink-0">
                    <URLProgressFilters 
                        projectId={parseInt(projectId)}
                        sessions={sessions}
                        on:filtersChange={handleUrlProgressFiltersChange}
                    />
                </div>
            </div>
            
        {/if}
    </div>
</DashboardLayout>

