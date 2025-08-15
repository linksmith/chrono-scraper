<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { writable } from 'svelte/stores';
    import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
    import { Badge } from '$lib/components/ui/badge';
    import { Progress } from '$lib/components/ui/progress';
    import { 
        Activity, 
        Globe, 
        Clock, 
        CheckCircle, 
        AlertTriangle, 
        Pause, 
        Play,
        Database,
        Eye,
        Download,
        Search,
        FileText,
        BarChart3,
        RefreshCw,
        RotateCcw
    } from 'lucide-svelte';
    import { getApiUrl } from '$lib/utils';
    import ScrapingControls from './ScrapingControls.svelte';

    export let projectId: string;
    export let scrapeSessionId: number;

    // Stores for progress data
    let sessionStats = writable({
        total_urls: 0,
        pending_urls: 0,
        in_progress_urls: 0,
        completed_urls: 0,
        failed_urls: 0,
        skipped_urls: 0,
        progress_percentage: 0,
        pages_per_minute: 0,
        estimated_completion: null,
        active_domains: 0,
        completed_domains: 0,
        failed_domains: 0,
        error_summary: {},
        performance_metrics: {}
    });

    let cdxProgress = writable({
        current_page: 0,
        total_pages: null,
        results_found: 0,
        results_processed: 0,
        duplicates_filtered: 0,
        list_pages_filtered: 0,
        high_value_pages: 0,
        pages_per_minute: 0,
        estimated_completion: null
    });

    let pageProgress = writable([]);
    let recentActivity = writable([]);

    let websocket: WebSocket | null = null;
    let connectionStatus = 'disconnected';
    let reconnectAttempts = 0;
    let maxReconnectAttempts = 5;

    // UI state
    let showDetails = false;
    let expandedDomains = new Set();
    let filterStatus = 'all'; // all, completed, failed, in_progress
    let sortBy = 'timestamp'; // timestamp, status, domain
    let currentSessionStatus = 'pending';
    let retryingPages = new Set(); // Track which pages are being retried

    function connectWebSocket() {
        try {
            const wsUrl = `ws://localhost:8000/ws/scrape/${scrapeSessionId}`;
            websocket = new WebSocket(wsUrl);
            
            websocket.onopen = () => {
                console.log('WebSocket connected');
                connectionStatus = 'connected';
                reconnectAttempts = 0;
            };
            
            websocket.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    handleProgressUpdate(message);
                } catch (error) {
                    console.error('Failed to parse WebSocket message:', error);
                }
            };
            
            websocket.onclose = () => {
                console.log('WebSocket disconnected');
                connectionStatus = 'disconnected';
                attemptReconnect();
            };
            
            websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                connectionStatus = 'error';
            };
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            connectionStatus = 'error';
        }
    }

    function attemptReconnect() {
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            connectionStatus = 'reconnecting';
            setTimeout(() => {
                console.log(`Reconnecting... attempt ${reconnectAttempts}`);
                connectWebSocket();
            }, Math.pow(2, reconnectAttempts) * 1000); // Exponential backoff
        }
    }

    function handleProgressUpdate(message: any) {
        console.log('Progress update received:', message);
        
        switch (message.type) {
            case 'session_stats':
                sessionStats.set(message.data);
                if (message.data.session_status) {
                    currentSessionStatus = message.data.session_status;
                }
                break;
                
            case 'cdx_discovery':
                cdxProgress.set(message.data);
                addRecentActivity({
                    type: 'cdx_discovery',
                    message: `Found ${message.data.results_found} pages on ${message.data.domain_name}`,
                    timestamp: message.timestamp,
                    domain: message.data.domain_name
                });
                break;
                
            case 'page_progress':
                pageProgress.update(pages => {
                    const existingIndex = pages.findIndex(p => p.scrape_page_id === message.data.scrape_page_id);
                    if (existingIndex >= 0) {
                        pages[existingIndex] = message.data;
                    } else {
                        pages.push(message.data);
                    }
                    return pages;
                });
                
                addRecentActivity({
                    type: 'page_progress',
                    message: `${message.data.status === 'completed' ? 'Completed' : 'Processing'} ${new URL(message.data.page_url).pathname}`,
                    timestamp: message.timestamp,
                    status: message.data.status,
                    domain: message.data.domain_name
                });
                break;
                
            case 'processing_stage':
                addRecentActivity({
                    type: 'processing_stage',
                    message: `${message.data.stage}: ${message.data.stage_status} for ${new URL(message.data.page_url).pathname}`,
                    timestamp: message.timestamp,
                    stage: message.data.stage,
                    status: message.data.stage_status
                });
                break;
        }
    }

    function addRecentActivity(activity: any) {
        recentActivity.update(activities => {
            activities.unshift({
                ...activity,
                id: Date.now() + Math.random()
            });
            return activities.slice(0, 50); // Keep only last 50 activities
        });
    }

    function getStatusIcon(status: string) {
        switch (status) {
            case 'completed': return CheckCircle;
            case 'failed': return AlertTriangle;
            case 'in_progress': return Activity;
            case 'pending': return Clock;
            default: return Clock;
        }
    }

    function getStatusColor(status: string) {
        switch (status) {
            case 'completed': return 'text-green-600';
            case 'failed': return 'text-red-600';
            case 'in_progress': return 'text-blue-600';
            case 'pending': return 'text-gray-600';
            default: return 'text-gray-600';
        }
    }

    function getStageIcon(stage: string) {
        switch (stage) {
            case 'content_fetch': return Download;
            case 'content_extract': return FileText;
            case 'entity_recognition': return Search;
            case 'indexing': return Database;
            default: return Activity;
        }
    }

    function formatTimeEstimate(timestamp: string | null) {
        if (!timestamp) return 'Unknown';
        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = date.getTime() - now.getTime();
        const diffMins = Math.round(diffMs / 60000);
        
        if (diffMins < 1) return 'Less than 1 minute';
        if (diffMins < 60) return `${diffMins} minutes`;
        const hours = Math.floor(diffMins / 60);
        const mins = diffMins % 60;
        return `${hours}h ${mins}m`;
    }

    function toggleDomain(domainId: string) {
        if (expandedDomains.has(domainId)) {
            expandedDomains.delete(domainId);
        } else {
            expandedDomains.add(domainId);
        }
        expandedDomains = expandedDomains; // Trigger reactivity
    }

    async function retryPage(pageId: number, pageUrl: string) {
        if (retryingPages.has(pageId)) return;
        
        try {
            retryingPages.add(pageId);
            retryingPages = retryingPages; // Trigger reactivity
            
            const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/pages/${pageId}/retry`), {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const result = await response.json();
                addRecentActivity({
                    type: 'page_retry',
                    message: `Retrying page: ${new URL(pageUrl).pathname}`,
                    timestamp: new Date().toISOString(),
                    status: 'retry_queued'
                });
            } else {
                const errorData = await response.json();
                addRecentActivity({
                    type: 'page_retry_error',
                    message: `Failed to retry page: ${errorData.detail || 'Unknown error'}`,
                    timestamp: new Date().toISOString(),
                    status: 'error'
                });
            }
        } catch (error) {
            console.error('Failed to retry page:', error);
            addRecentActivity({
                type: 'page_retry_error',
                message: `Network error retrying page: ${new URL(pageUrl).pathname}`,
                timestamp: new Date().toISOString(),
                status: 'error'
            });
        } finally {
            retryingPages.delete(pageId);
            retryingPages = retryingPages; // Trigger reactivity
        }
    }

    async function retryAllFailed() {
        try {
            const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/retry-failed`), {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const result = await response.json();
                addRecentActivity({
                    type: 'bulk_retry',
                    message: `Retrying ${result.pages_to_retry} failed pages`,
                    timestamp: new Date().toISOString(),
                    status: 'retry_queued'
                });
            } else {
                const errorData = await response.json();
                addRecentActivity({
                    type: 'bulk_retry_error',
                    message: `Failed to retry pages: ${errorData.detail || 'Unknown error'}`,
                    timestamp: new Date().toISOString(),
                    status: 'error'
                });
            }
        } catch (error) {
            console.error('Failed to retry all failed pages:', error);
            addRecentActivity({
                type: 'bulk_retry_error',
                message: 'Network error retrying failed pages',
                timestamp: new Date().toISOString(),
                status: 'error'
            });
        }
    }

    onMount(() => {
        connectWebSocket();
    });

    onDestroy(() => {
        if (websocket) {
            websocket.close();
        }
    });

    // Reactive statements for filtered data
    $: filteredPages = $pageProgress.filter(page => {
        if (filterStatus === 'all') return true;
        return page.status === filterStatus;
    }).sort((a, b) => {
        if (sortBy === 'timestamp') {
            return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
        }
        if (sortBy === 'status') {
            return a.status.localeCompare(b.status);
        }
        if (sortBy === 'domain') {
            return a.domain_name.localeCompare(b.domain_name);
        }
        return 0;
    });

    $: recentActivities = $recentActivity.slice(0, 10);
    $: failedPagesCount = filteredPages.filter(page => page.status === 'failed').length;
</script>

<div class="space-y-6">
    <!-- Connection Status -->
    <div class="flex items-center justify-between">
        <h2 class="text-2xl font-bold">Real-Time Progress</h2>
        <div class="flex items-center space-x-2">
            <div class="flex items-center space-x-1">
                <div class="w-2 h-2 rounded-full {connectionStatus === 'connected' ? 'bg-green-500' : connectionStatus === 'reconnecting' ? 'bg-yellow-500' : 'bg-red-500'}"></div>
                <span class="text-sm text-gray-600 capitalize">{connectionStatus}</span>
            </div>
            {#if connectionStatus === 'reconnecting'}
                <span class="text-xs text-gray-500">Attempt {reconnectAttempts}/{maxReconnectAttempts}</span>
            {/if}
        </div>
    </div>

    <!-- Scraping Controls -->
    <ScrapingControls 
        {projectId} 
        {scrapeSessionId} 
        sessionStatus={currentSessionStatus}
        on:sessionStarted={() => connectWebSocket()}
        on:sessionPaused={() => {}}
        on:sessionResumed={() => {}}
        on:sessionStopped={() => {}}
        on:retryStarted={() => {}}
    />

    <!-- Session Statistics -->
    <Card>
        <CardHeader>
            <CardTitle class="flex items-center space-x-2">
                <BarChart3 class="h-5 w-5" />
                <span>Session Overview</span>
            </CardTitle>
        </CardHeader>
        <CardContent>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div class="text-center">
                    <div class="text-2xl font-bold text-blue-600">{$sessionStats.total_urls}</div>
                    <div class="text-sm text-gray-600">Total URLs</div>
                </div>
                <div class="text-center">
                    <div class="text-2xl font-bold text-green-600">{$sessionStats.completed_urls}</div>
                    <div class="text-sm text-gray-600">Completed</div>
                </div>
                <div class="text-center">
                    <div class="text-2xl font-bold text-red-600">{$sessionStats.failed_urls}</div>
                    <div class="text-sm text-gray-600">Failed</div>
                </div>
                <div class="text-center">
                    <div class="text-2xl font-bold text-yellow-600">{$sessionStats.in_progress_urls}</div>
                    <div class="text-sm text-gray-600">In Progress</div>
                </div>
            </div>
            
            <div class="space-y-2">
                <div class="flex justify-between text-sm">
                    <span>Progress</span>
                    <span>{$sessionStats.progress_percentage.toFixed(1)}%</span>
                </div>
                <Progress value={$sessionStats.progress_percentage} class="h-2" />
            </div>
            
            {#if $sessionStats.pages_per_minute > 0}
                <div class="flex justify-between text-sm text-gray-600 mt-2">
                    <span>Speed: {$sessionStats.pages_per_minute.toFixed(1)} pages/min</span>
                    {#if $sessionStats.estimated_completion}
                        <span>ETA: {formatTimeEstimate($sessionStats.estimated_completion)}</span>
                    {/if}
                </div>
            {/if}
        </CardContent>
    </Card>

    <!-- CDX Discovery Progress -->
    <Card>
        <CardHeader>
            <CardTitle class="flex items-center space-x-2">
                <Globe class="h-5 w-5" />
                <span>CDX Discovery</span>
            </CardTitle>
        </CardHeader>
        <CardContent>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div class="text-center">
                    <div class="text-xl font-bold">{$cdxProgress.results_found}</div>
                    <div class="text-sm text-gray-600">Found</div>
                </div>
                <div class="text-center">
                    <div class="text-xl font-bold text-green-600">{$cdxProgress.high_value_pages}</div>
                    <div class="text-sm text-gray-600">High Value</div>
                </div>
                <div class="text-center">
                    <div class="text-xl font-bold text-orange-600">{$cdxProgress.duplicates_filtered}</div>
                    <div class="text-sm text-gray-600">Duplicates</div>
                </div>
                <div class="text-center">
                    <div class="text-xl font-bold text-red-600">{$cdxProgress.list_pages_filtered}</div>
                    <div class="text-sm text-gray-600">List Pages</div>
                </div>
            </div>
        </CardContent>
    </Card>

    <!-- Filter Controls -->
    <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-center space-x-2">
            <label class="text-sm font-medium">Filter:</label>
            <select bind:value={filterStatus} class="px-3 py-1 border rounded">
                <option value="all">All Pages</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="in_progress">In Progress</option>
                <option value="pending">Pending</option>
            </select>
        </div>
        
        <div class="flex items-center space-x-2">
            <label class="text-sm font-medium">Sort by:</label>
            <select bind:value={sortBy} class="px-3 py-1 border rounded">
                <option value="timestamp">Timestamp</option>
                <option value="status">Status</option>
                <option value="domain">Domain</option>
            </select>
        </div>
        
        <div class="flex items-center space-x-2">
            {#if failedPagesCount > 0}
                <button onclick={retryAllFailed} class="px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 flex items-center space-x-1">
                    <RotateCcw class="h-3 w-3" />
                    <span>Retry All Failed ({failedPagesCount})</span>
                </button>
            {/if}
            <button onclick={() => showDetails = !showDetails} class="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700">
                {showDetails ? 'Hide' : 'Show'} Details
            </button>
        </div>
    </div>

    <div class="grid gap-6 {showDetails ? 'md:grid-cols-2' : 'md:grid-cols-1'}">
        <!-- Recent Activity -->
        <Card>
            <CardHeader>
                <CardTitle class="flex items-center space-x-2">
                    <Activity class="h-5 w-5" />
                    <span>Recent Activity</span>
                </CardTitle>
            </CardHeader>
            <CardContent>
                <div class="space-y-2 max-h-96 overflow-y-auto">
                    {#each recentActivities as activity}
                        <div class="flex items-center space-x-3 p-2 border rounded">
                            <svelte:component this={getStageIcon(activity.stage || activity.type)} 
                                            class="h-4 w-4 {getStatusColor(activity.status || 'pending')}" />
                            <div class="flex-1 min-w-0">
                                <div class="text-sm truncate">{activity.message}</div>
                                <div class="text-xs text-gray-500">{activity.domain} • {new Date(activity.timestamp).toLocaleTimeString()}</div>
                            </div>
                            {#if activity.status}
                                <Badge variant={activity.status === 'completed' ? 'default' : activity.status === 'failed' ? 'destructive' : 'secondary'}>
                                    {activity.status}
                                </Badge>
                            {/if}
                        </div>
                    {/each}
                    
                    {#if recentActivities.length === 0}
                        <div class="text-center text-gray-500 py-8">
                            <Activity class="h-8 w-8 mx-auto mb-2 opacity-50" />
                            <p>No activity yet</p>
                        </div>
                    {/if}
                </div>
            </CardContent>
        </Card>

        <!-- Detailed Page Progress -->
        {#if showDetails}
            <Card>
                <CardHeader>
                    <CardTitle class="flex items-center space-x-2">
                        <Eye class="h-5 w-5" />
                        <span>Page Details ({filteredPages.length})</span>
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div class="space-y-2 max-h-96 overflow-y-auto">
                        {#each filteredPages as pageItem}
                            <div class="flex items-center space-x-3 p-3 border rounded hover:bg-gray-50">
                                <svelte:component this={getStatusIcon(pageItem.status)} 
                                                class="h-4 w-4 {getStatusColor(pageItem.status)}" />
                                <div class="flex-1 min-w-0">
                                    <div class="text-sm font-medium truncate" title={pageItem.page_url}>
                                        {new URL(pageItem.page_url).pathname}
                                    </div>
                                    <div class="text-xs text-gray-500">
                                        {pageItem.domain_name} • {pageItem.processing_stage}
                                        {#if pageItem.stage_progress}
                                            • {(pageItem.stage_progress * 100).toFixed(0)}%
                                        {/if}
                                        {#if pageItem.retry_count > 0}
                                            • Retry {pageItem.retry_count}
                                        {/if}
                                    </div>
                                </div>
                                <div class="flex items-center space-x-2">
                                    {#if pageItem.status === 'failed'}
                                        <button 
                                            onclick={() => retryPage(pageItem.scrape_page_id, pageItem.page_url)}
                                            disabled={retryingPages.has(pageItem.scrape_page_id)}
                                            class="p-1 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                                            title="Retry this page"
                                        >
                                            {#if retryingPages.has(pageItem.scrape_page_id)}
                                                <RefreshCw class="h-3 w-3 animate-spin text-blue-600" />
                                            {:else}
                                                <RotateCcw class="h-3 w-3 text-red-600" />
                                            {/if}
                                        </button>
                                    {/if}
                                    <Badge variant={pageItem.status === 'completed' ? 'default' : pageItem.status === 'failed' ? 'destructive' : 'secondary'}>
                                        {pageItem.status}
                                    </Badge>
                                </div>
                            </div>
                        {/each}
                        
                        {#if filteredPages.length === 0}
                            <div class="text-center text-gray-500 py-8">
                                <FileText class="h-8 w-8 mx-auto mb-2 opacity-50" />
                                <p>No pages match the current filter</p>
                            </div>
                        {/if}
                    </div>
                </CardContent>
            </Card>
        {/if}
    </div>
</div>