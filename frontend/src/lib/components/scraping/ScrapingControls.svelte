<script lang="ts">
    import { createEventDispatcher } from 'svelte';
    import { Badge } from '$lib/components/ui/badge';
    import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
    import { 
        Play, 
        Pause, 
        Square, 
        RefreshCw, 
        Settings,
        AlertTriangle,
        CheckCircle,
        Clock
    } from 'lucide-svelte';
    import { getApiUrl } from '$lib/utils';

    export let projectId: string;
    export let scrapeSessionId: number | null = null;
    export let sessionStatus: string = 'pending';
    export let canControl: boolean = true;

    const dispatch = createEventDispatcher();

    let isLoading = false;
    let error = '';

    async function startScraping() {
        if (!canControl || isLoading) return;
        
        try {
            isLoading = true;
            error = '';
            
            const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/scrape`), {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const result = await response.json();
                dispatch('sessionStarted', result);
            } else {
                const errorData = await response.json();
                error = errorData.detail || 'Failed to start scraping';
            }
        } catch (e) {
            error = 'Network error while starting scraping';
            console.error('Start scraping error:', e);
        } finally {
            isLoading = false;
        }
    }

    async function pauseScraping() {
        if (!canControl || isLoading || !scrapeSessionId) return;
        
        try {
            isLoading = true;
            error = '';
            
            const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/pause`), {
                method: 'POST',
                credentials: 'include'
            });
            
            if (response.ok) {
                const result = await response.json();
                dispatch('sessionPaused', result);
            } else {
                const errorData = await response.json();
                error = errorData.detail || 'Failed to pause scraping';
            }
        } catch (e) {
            error = 'Network error while pausing scraping';
            console.error('Pause scraping error:', e);
        } finally {
            isLoading = false;
        }
    }

    async function resumeScraping() {
        if (!canControl || isLoading || !scrapeSessionId) return;
        
        try {
            isLoading = true;
            error = '';
            
            const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/resume`), {
                method: 'POST',
                credentials: 'include'
            });
            
            if (response.ok) {
                const result = await response.json();
                dispatch('sessionResumed', result);
            } else {
                const errorData = await response.json();
                error = errorData.detail || 'Failed to resume scraping';
            }
        } catch (e) {
            error = 'Network error while resuming scraping';
            console.error('Resume scraping error:', e);
        } finally {
            isLoading = false;
        }
    }

    async function stopScraping() {
        if (!canControl || isLoading || !scrapeSessionId) return;
        
        try {
            isLoading = true;
            error = '';
            
            const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/stop`), {
                method: 'POST',
                credentials: 'include'
            });
            
            if (response.ok) {
                const result = await response.json();
                dispatch('sessionStopped', result);
            } else {
                const errorData = await response.json();
                error = errorData.detail || 'Failed to stop scraping';
            }
        } catch (e) {
            error = 'Network error while stopping scraping';
            console.error('Stop scraping error:', e);
        } finally {
            isLoading = false;
        }
    }

    async function retryFailed() {
        if (!canControl || isLoading) return;
        
        try {
            isLoading = true;
            error = '';
            
            const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/retry-failed`), {
                method: 'POST',
                credentials: 'include'
            });
            
            if (response.ok) {
                const result = await response.json();
                dispatch('retryStarted', result);
            } else {
                const errorData = await response.json();
                error = errorData.detail || 'Failed to retry failed pages';
            }
        } catch (e) {
            error = 'Network error while retrying failed pages';
            console.error('Retry failed error:', e);
        } finally {
            isLoading = false;
        }
    }

    function getStatusIcon(status: string) {
        switch (status) {
            case 'running':
            case 'in_progress':
                return Play;
            case 'paused':
                return Pause;
            case 'completed':
                return CheckCircle;
            case 'failed':
                return AlertTriangle;
            case 'pending':
            default:
                return Clock;
        }
    }

    function getStatusColor(status: string) {
        switch (status) {
            case 'running':
            case 'in_progress':
                return 'text-blue-600';
            case 'paused':
                return 'text-yellow-600';
            case 'completed':
                return 'text-green-600';
            case 'failed':
                return 'text-red-600';
            case 'pending':
            default:
                return 'text-gray-600';
        }
    }

    function getStatusBadgeVariant(status: string) {
        switch (status) {
            case 'running':
            case 'in_progress':
                return 'default';
            case 'paused':
                return 'secondary';
            case 'completed':
                return 'default';
            case 'failed':
                return 'destructive';
            case 'pending':
            default:
                return 'outline';
        }
    }

    $: canStart = sessionStatus === 'pending' || sessionStatus === 'failed' || sessionStatus === 'completed';
    $: canPause = sessionStatus === 'running' || sessionStatus === 'in_progress';
    $: canResume = sessionStatus === 'paused';
    $: canStop = sessionStatus === 'running' || sessionStatus === 'in_progress' || sessionStatus === 'paused';
    $: canRetry = sessionStatus === 'completed' || sessionStatus === 'failed' || sessionStatus === 'running';
</script>

<Card>
    <CardHeader>
        <CardTitle class="flex items-center justify-between">
            <div class="flex items-center space-x-2">
                <Settings class="h-5 w-5" />
                <span>Scraping Controls</span>
            </div>
            <div class="flex items-center space-x-2">
                <svelte:component this={getStatusIcon(sessionStatus)} 
                                class="h-4 w-4 {getStatusColor(sessionStatus)}" />
                <Badge variant={getStatusBadgeVariant(sessionStatus)}>
                    {sessionStatus}
                </Badge>
            </div>
        </CardTitle>
    </CardHeader>
    <CardContent>
        {#if error}
            <div class="mb-4 p-3 bg-red-50 border border-red-200 rounded text-red-800 text-sm">
                <div class="flex items-center space-x-2">
                    <AlertTriangle class="h-4 w-4" />
                    <span>{error}</span>
                </div>
            </div>
        {/if}

        <div class="flex flex-wrap items-center gap-2">
            {#if canStart}
                <button 
                    onclick={startScraping}
                    disabled={!canControl || isLoading}
                    class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-9 px-4 py-2"
                >
                    {#if isLoading}
                        <RefreshCw class="h-4 w-4 mr-2 animate-spin" />
                    {:else}
                        <Play class="h-4 w-4 mr-2" />
                    {/if}
                    Start Scraping
                </button>
            {/if}

            {#if canPause}
                <button 
                    onclick={pauseScraping}
                    disabled={!canControl || isLoading}
                    class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-yellow-600 text-white hover:bg-yellow-700 h-9 px-4 py-2"
                >
                    {#if isLoading}
                        <RefreshCw class="h-4 w-4 mr-2 animate-spin" />
                    {:else}
                        <Pause class="h-4 w-4 mr-2" />
                    {/if}
                    Pause
                </button>
            {/if}

            {#if canResume}
                <button 
                    onclick={resumeScraping}
                    disabled={!canControl || isLoading}
                    class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-green-600 text-white hover:bg-green-700 h-9 px-4 py-2"
                >
                    {#if isLoading}
                        <RefreshCw class="h-4 w-4 mr-2 animate-spin" />
                    {:else}
                        <Play class="h-4 w-4 mr-2" />
                    {/if}
                    Resume
                </button>
            {/if}

            {#if canStop}
                <button 
                    onclick={stopScraping}
                    disabled={!canControl || isLoading}
                    class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-red-600 text-white hover:bg-red-700 h-9 px-4 py-2"
                >
                    {#if isLoading}
                        <RefreshCw class="h-4 w-4 mr-2 animate-spin" />
                    {:else}
                        <Square class="h-4 w-4 mr-2" />
                    {/if}
                    Stop
                </button>
            {/if}

            {#if canRetry}
                <button 
                    onclick={retryFailed}
                    disabled={!canControl || isLoading}
                    class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-9 px-4 py-2"
                >
                    {#if isLoading}
                        <RefreshCw class="h-4 w-4 mr-2 animate-spin" />
                    {:else}
                        <RefreshCw class="h-4 w-4 mr-2" />
                    {/if}
                    Retry Failed
                </button>
            {/if}
        </div>

        <div class="mt-4 text-sm text-gray-600">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div>
                    <strong>Status:</strong> {sessionStatus || 'Not started'}
                </div>
                {#if scrapeSessionId}
                    <div>
                        <strong>Session ID:</strong> {scrapeSessionId}
                    </div>
                {/if}
            </div>
        </div>
    </CardContent>
</Card>