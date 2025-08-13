<script lang="ts">
    import { onMount } from 'svelte';
    import { page } from '$app/stores';
    import { goto } from '$app/navigation';
    import { isAuthenticated, auth } from '$lib/stores/auth';
    import { getApiUrl, formatDate, getRelativeTime, getFileSize, getStatusColor } from '$lib/utils';
    import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
    import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
    import { Button } from '$lib/components/ui/button';
    import { Badge } from '$lib/components/ui/badge';
    import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
    import { Input } from '$lib/components/ui/input';
    import { Progress } from '$lib/components/ui/progress';
    import { 
        Settings, 
        Play, 
        Pause,
        BarChart3,
        Globe,
        Calendar,
        Users,
        Database,
        Search,
        Download,
        ExternalLink,
        Edit,
        Share,
        Archive,
        Trash2,
        Clock,
        Activity,
        FileText,
        AlertTriangle,
        CheckCircle,
        Eye
    } from 'lucide-svelte';
    
    let projectId: string;
    let project: any = null;
    let pages: any[] = [];
    let domains: any[] = [];
    let sessions: any[] = [];
    let loading = false;
    let error = '';
    let activeTab = 'overview';
    let searchQuery = '';
    
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
    
    $: projectId = $page.params.id;
    
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
    });
    
    const loadProject = async () => {
        loading = true;
        try {
            await Promise.all([
                loadProjectDetails(),
                loadProjectStats(),
                loadPages(),
                loadDomains(),
                loadSessions()
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
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
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
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                stats = await res.json();
            }
        } catch (e) {
            console.error('Failed to load stats:', e);
        }
    };
    
    const loadPages = async () => {
        try {
            const params = searchQuery ? `?search=${encodeURIComponent(searchQuery)}` : '';
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/pages${params}`), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                const data = await res.json();
                pages = data.items || data.pages || [];
            }
        } catch (e) {
            console.error('Failed to load pages:', e);
        }
    };
    
    const loadDomains = async () => {
        try {
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/domains`), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                domains = await res.json();
            }
        } catch (e) {
            console.error('Failed to load domains:', e);
        }
    };
    
    const loadSessions = async () => {
        try {
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/sessions`), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                sessions = await res.json();
            }
        } catch (e) {
            console.error('Failed to load sessions:', e);
        }
    };
    
    const startScraping = async () => {
        try {
            const res = await fetch(getApiUrl(`/api/v1/projects/${projectId}/scrape`), {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
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
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
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
    
    const handleSearch = () => {
        if (activeTab === 'pages') {
            loadPages();
        }
    };
    
    const editProject = () => {
        goto(`/projects/${projectId}/edit`);
    };
    
    const shareProject = () => {
        goto(`/projects/${projectId}/share`);
    };
    
    const viewPage = (pageId: string) => {
        goto(`/projects/${projectId}/pages/${pageId}`);
    };
    
    const viewDomain = (domainId: string) => {
        goto(`/projects/${projectId}/domains/${domainId}`);
    };
    
    const viewSession = (sessionId: string) => {
        goto(`/projects/${projectId}/sessions/${sessionId}`);
    };
    
    const getDomainStatusColor = (status: string) => {
        switch (status?.toLowerCase()) {
            case 'active': return 'default';
            case 'paused': return 'secondary';
            case 'completed': return 'outline';
            case 'error': return 'destructive';
            default: return 'secondary';
        }
    };
    
    const getSessionStatusColor = (status: string) => {
        switch (status?.toLowerCase()) {
            case 'running': return 'default';
            case 'paused': return 'secondary';
            case 'completed': return 'outline';
            case 'failed': return 'destructive';
            default: return 'secondary';
        }
    };
    
    const formatProgress = (current: number, total: number) => {
        if (total === 0) return 0;
        return Math.round((current / total) * 100);
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
                        {#if stats.last_scrape}
                            <div class="flex items-center">
                                <Clock class="mr-1 h-3 w-3" />
                                Last scraped {getRelativeTime(stats.last_scrape)}
                            </div>
                        {/if}
                    </div>
                </div>
                <div class="flex gap-2">
                    <Button variant="outline" on:click={shareProject}>
                        <Share class="mr-2 h-4 w-4" />
                        Share
                    </Button>
                    <Button variant="outline" on:click={editProject}>
                        <Edit class="mr-2 h-4 w-4" />
                        Edit
                    </Button>
                    {#if project.status === 'indexing' || project.status === 'active'}
                        <Button variant="outline" on:click={pauseScraping}>
                            <Pause class="mr-2 h-4 w-4" />
                            Pause
                        </Button>
                    {:else}
                        <Button on:click={startScraping}>
                            <Play class="mr-2 h-4 w-4" />
                            Start Scraping
                        </Button>
                    {/if}
                </div>
            </div>
            
            <!-- Statistics Cards -->
            <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Total Pages</CardTitle>
                        <FileText class="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold">{stats.total_pages}</div>
                        <div class="text-xs text-muted-foreground">
                            {stats.indexed_pages} indexed, {stats.failed_pages} failed
                        </div>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Domains</CardTitle>
                        <Globe class="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold">{stats.total_domains}</div>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Success Rate</CardTitle>
                        <BarChart3 class="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold">{Math.round(stats.success_rate * 100)}%</div>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle class="text-sm font-medium">Storage Used</CardTitle>
                        <Database class="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div class="text-2xl font-bold">{getFileSize(stats.storage_used)}</div>
                    </CardContent>
                </Card>
            </div>
            
            <!-- Tabs -->
            <Tabs bind:value={activeTab} class="w-full">
                <TabsList class="grid w-full grid-cols-4">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="pages">Pages</TabsTrigger>
                    <TabsTrigger value="domains">Domains</TabsTrigger>
                    <TabsTrigger value="sessions">Sessions</TabsTrigger>
                </TabsList>
                
                <!-- Overview Tab -->
                <TabsContent value="overview" class="space-y-6">
                    <!-- Project Progress -->
                    {#if stats.total_pages > 0}
                        <Card>
                            <CardHeader>
                                <CardTitle>Scraping Progress</CardTitle>
                            </CardHeader>
                            <CardContent class="space-y-4">
                                <div class="space-y-2">
                                    <div class="flex justify-between text-sm">
                                        <span>Indexed Pages</span>
                                        <span>{stats.indexed_pages} / {stats.total_pages}</span>
                                    </div>
                                    <Progress value={formatProgress(stats.indexed_pages, stats.total_pages)} />
                                </div>
                                {#if stats.failed_pages > 0}
                                    <div class="space-y-2">
                                        <div class="flex justify-between text-sm text-red-600">
                                            <span>Failed Pages</span>
                                            <span>{stats.failed_pages}</span>
                                        </div>
                                        <Progress value={formatProgress(stats.failed_pages, stats.total_pages)} class="bg-red-100" />
                                    </div>
                                {/if}
                            </CardContent>
                        </Card>
                    {/if}
                    
                    <!-- Recent Activity -->
                    <Card>
                        <CardHeader>
                            <CardTitle>Recent Activity</CardTitle>
                        </CardHeader>
                        <CardContent>
                            {#if sessions.length > 0}
                                <div class="space-y-4">
                                    {#each sessions.slice(0, 5) as session}
                                        <div class="flex items-center justify-between p-3 border rounded-lg">
                                            <div class="flex items-center space-x-3">
                                                <Activity class="h-4 w-4 text-muted-foreground" />
                                                <div>
                                                    <p class="font-medium">{session.name || 'Scraping Session'}</p>
                                                    <p class="text-sm text-muted-foreground">
                                                        {getRelativeTime(session.started_at || session.created_at)}
                                                    </p>
                                                </div>
                                            </div>
                                            <Badge variant={getSessionStatusColor(session.status)}>
                                                {session.status}
                                            </Badge>
                                        </div>
                                    {/each}
                                </div>
                            {:else}
                                <div class="text-center py-8">
                                    <Activity class="h-12 w-12 text-muted-foreground mx-auto mb-3" />
                                    <p class="text-muted-foreground">No recent activity</p>
                                </div>
                            {/if}
                        </CardContent>
                    </Card>
                </TabsContent>
                
                <!-- Pages Tab -->
                <TabsContent value="pages" class="space-y-4">
                    <!-- Search -->
                    <div class="relative">
                        <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                        <Input
                            bind:value={searchQuery}
                            on:input={handleSearch}
                            placeholder="Search pages..."
                            class="pl-10"
                        />
                    </div>
                    
                    {#if pages.length === 0}
                        <Card>
                            <CardContent class="pt-6">
                                <div class="flex flex-col items-center justify-center space-y-3 py-12">
                                    <FileText class="h-12 w-12 text-muted-foreground" />
                                    <div class="text-center">
                                        <h3 class="text-lg font-semibold">No pages found</h3>
                                        <p class="text-muted-foreground">
                                            Start scraping to collect pages.
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    {:else}
                        <div class="space-y-4">
                            {#each pages as page}
                                <Card class="hover:shadow-md transition-shadow cursor-pointer" on:click={() => viewPage(page.id)}>
                                    <CardContent class="pt-6">
                                        <div class="flex items-start justify-between">
                                            <div class="flex-1">
                                                <h3 class="font-semibold line-clamp-2">{page.title || page.url}</h3>
                                                <p class="text-sm text-muted-foreground mt-1 line-clamp-1">
                                                    {page.url}
                                                </p>
                                                <div class="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                                                    <span>Scraped {getRelativeTime(page.scraped_at)}</span>
                                                    {#if page.word_count}
                                                        <span>{page.word_count} words</span>
                                                    {/if}
                                                    {#if page.content_type}
                                                        <span>{page.content_type}</span>
                                                    {/if}
                                                </div>
                                            </div>
                                            <div class="flex items-center gap-2">
                                                <Button variant="ghost" size="sm">
                                                    <Eye class="h-3 w-3" />
                                                </Button>
                                                <Button variant="ghost" size="sm">
                                                    <ExternalLink class="h-3 w-3" />
                                                </Button>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            {/each}
                        </div>
                    {/if}
                </TabsContent>
                
                <!-- Domains Tab -->
                <TabsContent value="domains" class="space-y-4">
                    {#if domains.length === 0}
                        <Card>
                            <CardContent class="pt-6">
                                <div class="flex flex-col items-center justify-center space-y-3 py-12">
                                    <Globe class="h-12 w-12 text-muted-foreground" />
                                    <div class="text-center">
                                        <h3 class="text-lg font-semibold">No domains configured</h3>
                                        <p class="text-muted-foreground">
                                            Add domains to start scraping.
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    {:else}
                        <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                            {#each domains as domain}
                                <Card class="hover:shadow-md transition-shadow cursor-pointer" on:click={() => viewDomain(domain.id)}>
                                    <CardHeader class="pb-2">
                                        <div class="flex items-start justify-between">
                                            <CardTitle class="text-lg line-clamp-1">{domain.domain}</CardTitle>
                                            <Badge variant={getDomainStatusColor(domain.status)}>
                                                {domain.status || 'Active'}
                                            </Badge>
                                        </div>
                                        {#if domain.description}
                                            <CardDescription class="line-clamp-2">
                                                {domain.description}
                                            </CardDescription>
                                        {/if}
                                    </CardHeader>
                                    <CardContent class="space-y-3">
                                        <div class="flex items-center justify-between text-sm">
                                            <div class="flex items-center text-muted-foreground">
                                                <FileText class="mr-1 h-3 w-3" />
                                                {domain.page_count || 0} pages
                                            </div>
                                            <div class="flex items-center text-muted-foreground">
                                                <Clock class="mr-1 h-3 w-3" />
                                                {getRelativeTime(domain.last_scraped || domain.created_at)}
                                            </div>
                                        </div>
                                        
                                        {#if domain.match_type}
                                            <div class="flex items-center justify-between text-xs text-muted-foreground">
                                                <span>Match: {domain.match_type}</span>
                                                {#if domain.crawl_delay}
                                                    <span>Delay: {domain.crawl_delay}s</span>
                                                {/if}
                                            </div>
                                        {/if}
                                    </CardContent>
                                </Card>
                            {/each}
                        </div>
                    {/if}
                </TabsContent>
                
                <!-- Sessions Tab -->
                <TabsContent value="sessions" class="space-y-4">
                    {#if sessions.length === 0}
                        <Card>
                            <CardContent class="pt-6">
                                <div class="flex flex-col items-center justify-center space-y-3 py-12">
                                    <Activity class="h-12 w-12 text-muted-foreground" />
                                    <div class="text-center">
                                        <h3 class="text-lg font-semibold">No scraping sessions</h3>
                                        <p class="text-muted-foreground">
                                            Scraping sessions will appear here.
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    {:else}
                        <div class="space-y-4">
                            {#each sessions as session}
                                <Card class="hover:shadow-md transition-shadow cursor-pointer" on:click={() => viewSession(session.id)}>
                                    <CardContent class="pt-6">
                                        <div class="flex items-start justify-between">
                                            <div class="flex-1">
                                                <h3 class="font-semibold">{session.name || 'Scraping Session'}</h3>
                                                <div class="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                                                    <span>Started {getRelativeTime(session.started_at || session.created_at)}</span>
                                                    {#if session.pages_scraped}
                                                        <span>{session.pages_scraped} pages scraped</span>
                                                    {/if}
                                                    {#if session.duration}
                                                        <span>{Math.round(session.duration / 60)} minutes</span>
                                                    {/if}
                                                </div>
                                            </div>
                                            <div class="flex items-center gap-2">
                                                <Badge variant={getSessionStatusColor(session.status)}>
                                                    {session.status}
                                                </Badge>
                                            </div>
                                        </div>
                                        
                                        {#if session.progress !== undefined}
                                            <div class="mt-4">
                                                <div class="flex items-center justify-between text-sm mb-2">
                                                    <span>Progress</span>
                                                    <span>{Math.round(session.progress * 100)}%</span>
                                                </div>
                                                <Progress value={session.progress * 100} />
                                            </div>
                                        {/if}
                                    </CardContent>
                                </Card>
                            {/each}
                        </div>
                    {/if}
                </TabsContent>
            </Tabs>
        {/if}
    </div>
</DashboardLayout>

<style>
    .line-clamp-1 {
        display: -webkit-box;
        -webkit-line-clamp: 1;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
    
    .line-clamp-2 {
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
</style>