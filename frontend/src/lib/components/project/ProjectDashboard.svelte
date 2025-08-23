<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '$lib/components/ui/card';
    import { Badge } from '$lib/components/ui/badge';
    import { Button } from '$lib/components/ui/button';
    import { Progress } from '$lib/components/ui/progress';
    import RealTimeProgress from '$lib/components/scraping/RealTimeProgress.svelte';
    import ScrapingControls from '$lib/components/scraping/ScrapingControls.svelte';
    import { Database, Activity, BarChart3, Globe, Play, Info } from 'lucide-svelte';
    import { getApiUrl, getFileSize, formatDate, getRelativeTime } from '$lib/utils';

    export let projectId: string;
    export let project: any = null;
    export let stats: any = {};
    export let sessions: any[] = [];

    // Local copies for smart refresh
    let localStats: any = stats || {};
    let localSessions: any[] = sessions || [];
    $: activeSession = localSessions.find(s => s.status === 'running' || s.status === 'pending') || localSessions[0];

    // Progressive disclosure
    let showAdvanced = false;

    let refreshTimer: number | null = null;

    onMount(() => {
        setupRefreshTimer();
    });

    onDestroy(() => {
        if (refreshTimer) {
            clearInterval(refreshTimer);
            refreshTimer = null;
        }
    });

    function setupRefreshTimer() {
        if (refreshTimer) {
            clearInterval(refreshTimer);
            refreshTimer = null;
        }
        const hasActive = !!(localSessions && localSessions.some(s => s.status === 'running' || s.status === 'pending'));
        if (!hasActive) {
            refreshTimer = window.setInterval(async () => {
                await Promise.all([refreshStats(), refreshSessions()]);
            }, 30000);
        }
    }

    async function refreshStats() {
        try {
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/stats`), { credentials: 'include' });
            if (res.ok) {
                localStats = await res.json();
            }
        } catch (e) {}
    }

    async function refreshSessions() {
        try {
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/sessions`), { credentials: 'include' });
            if (res.ok) {
                localSessions = await res.json();
                const hasActive = localSessions.some(s => s.status === 'running' || s.status === 'pending');
                if (hasActive && refreshTimer) {
                    clearInterval(refreshTimer);
                    refreshTimer = null;
                }
            }
        } catch (e) {}
    }

    async function startScraping() {
        try {
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/scrape`), {
                method: 'POST',
                credentials: 'include'
            });
            // parent can refresh data
        } catch (e) {}
    }
</script>

<div class="space-y-6">
    <!-- Project Header -->
    <div class="flex items-center justify-between">
        <div>
            <h2 class="text-2xl font-bold">{project?.name || 'Project Dashboard'}</h2>
            {#if project?.updated_at}
                <p class="text-sm text-muted-foreground">Updated {getRelativeTime(project.updated_at)}</p>
            {/if}
        </div>
        {#if project?.status}
            <div class="flex items-center gap-2">
                <Badge>{project.status}</Badge>
                <span class="inline-flex items-center text-xs text-muted-foreground">
                    <Info class="h-3 w-3 mr-1" />
                    {project.status === 'indexing' ? 'Scraping/indexing in progress' : project.status === 'paused' ? 'Scraping paused; you can resume anytime' : project.status === 'indexed' ? 'Index up-to-date' : 'Configure domains and start a session'}
                </span>
            </div>
        {/if}
    </div>

    <!-- Quick Stats Row -->
    <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
            <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle class="text-sm font-medium">Total Pages</CardTitle>
                <BarChart3 class="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
                <div class="text-2xl font-bold">{localStats.total_pages || 0}</div>
                <p class="text-xs text-muted-foreground">Indexed: {localStats.indexed_pages || 0}</p>
            </CardContent>
        </Card>
        <Card>
            <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle class="text-sm font-medium">Failed Pages</CardTitle>
                <Activity class="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
                <div class="text-2xl font-bold text-red-600">{localStats.failed_pages || 0}</div>
            </CardContent>
        </Card>
        <Card>
            <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle class="text-sm font-medium">Domains</CardTitle>
                <Globe class="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
                <div class="text-2xl font-bold">{localStats.total_domains || 0}</div>
            </CardContent>
        </Card>
        <Card>
            <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle class="text-sm font-medium">Storage Used</CardTitle>
                <Database class="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
                <div class="text-2xl font-bold">{getFileSize(localStats.storage_used || 0)}</div>
            </CardContent>
        </Card>
    </div>

    <!-- Advanced (progressive disclosure) -->
    <div>
        <Button variant="outline" size="sm" onclick={() => showAdvanced = !showAdvanced}>
            {showAdvanced ? 'Hide' : 'Show'} Advanced Details
        </Button>
        {#if showAdvanced}
            <div class="mt-3 grid gap-4 md:grid-cols-2">
                <Card>
                    <CardHeader>
                        <CardTitle>Success Rate</CardTitle>
                        <CardDescription>Completed vs total pages</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold">{Math.round(((localStats.indexed_pages || 0) / Math.max(localStats.total_pages || 1, 1)) * 100)}%</div>
                        <div class="mt-2">
                            <Progress value={((localStats.indexed_pages || 0) / Math.max(localStats.total_pages || 1, 1)) * 100} />
                        </div>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <CardTitle>Storage & Throughput</CardTitle>
                        <CardDescription>Approximate usage and rate</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div class="text-sm text-muted-foreground">Storage: {getFileSize(localStats.storage_used || 0)}</div>
                        <div class="text-sm text-muted-foreground">Domains: {localStats.total_domains || 0}</div>
                    </CardContent>
                </Card>
            </div>
        {/if}
    </div>

    <!-- Live Session Status & Controls -->
    <Card>
        <CardHeader>
            <CardTitle class="flex items-center justify-between">
                <span>Live Session</span>
                {#if !activeSession}
                    <Button onclick={startScraping} size="sm"><Play class="h-4 w-4 mr-2" />Start Scraping</Button>
                {/if}
            </CardTitle>
            <CardDescription>
                {#if activeSession}
                    Session #{activeSession.id} • {activeSession.status}
                {:else}
                    No active session
                {/if}
            </CardDescription>
        </CardHeader>
        <CardContent>
            {#if activeSession}
                <ScrapingControls projectId={projectId} scrapeSessionId={activeSession.id} sessionStatus={activeSession.status} />
            {:else}
                <p class="text-sm text-muted-foreground">Start a new scraping session to see live progress.</p>
            {/if}
        </CardContent>
    </Card>

    <!-- Progress Monitoring & Activity in two columns -->
    <div class="grid gap-6 lg:grid-cols-2">
        <div>
            {#if activeSession}
                <RealTimeProgress projectId={projectId} scrapeSessionId={activeSession.id} />
            {:else}
                <Card>
                    <CardHeader><CardTitle>Real-Time Progress</CardTitle></CardHeader>
                    <CardContent>
                        <p class="text-sm text-muted-foreground">No active session. Start scraping to monitor progress here.</p>
                    </CardContent>
                </Card>
            {/if}
        </div>

        <!-- Recent Sessions (Collapsible simplified) -->
        <div>
            <Card>
                <CardHeader>
                    <CardTitle>Recent Sessions</CardTitle>
                    <CardDescription>Latest scraping runs</CardDescription>
                </CardHeader>
                <CardContent>
                    {#if localSessions && localSessions.length > 0}
                        <details class="lg:open">
                            <summary class="cursor-pointer select-none text-sm text-muted-foreground">Show/Hide recent sessions</summary>
                            <div class="mt-3 space-y-3">
                                {#each localSessions.slice(0, 5) as session}
                                    <div class="flex items-center justify-between p-3 border rounded-lg">
                                        <div>
                                            <div class="font-medium">Session #{session.id}</div>
                                            <div class="text-xs text-muted-foreground">{getRelativeTime(session.started_at || session.created_at)}</div>
                                        </div>
                                        <Badge>{session.status}</Badge>
                                    </div>
                                {/each}
                            </div>
                        </details>
                    {:else}
                        <div class="text-sm text-muted-foreground">No sessions yet.</div>
                    {/if}
                </CardContent>
            </Card>
        </div>
    </div>
</div>

<style>
</style>


