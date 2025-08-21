<script lang="ts">
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { isAuthenticated, auth } from '$lib/stores/auth';
    import { getApiUrl, formatDate, getRelativeTime } from '$lib/utils';
    import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
    import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
    import { Button } from '$lib/components/ui/button';
    import { Badge } from '$lib/components/ui/badge';
    import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
    import { Input } from '$lib/components/ui/input';
    import { Plus, FileText, CheckCircle, Clock, BarChart3, Search, Filter, AlertTriangle } from 'lucide-svelte';
    
    let investigations: any[] = [];
    let loading = false;
    let error = '';
    let searchQuery = '';
    let statusFilter = '';
    let priorityFilter = '';
    let stats = {
        active: 0,
        completed: 0,
        overdue: 0,
        evidence_items: 0
    };
    
    onMount(async () => {
        // Initialize auth and check if user is authenticated
        await auth.init();
        
        // Redirect to login if not authenticated
        if (!$isAuthenticated) {
            goto('/auth/login?redirect=/investigations');
            return;
        }
        
        // Load investigations
        await loadInvestigations();
        await loadStats();
    });
    
    const loadInvestigations = async () => {
        loading = true;
        try {
            const params = new URLSearchParams();
            if (searchQuery) params.set('search', searchQuery);
            if (statusFilter) params.set('status', statusFilter);
            if (priorityFilter) params.set('priority', priorityFilter);
            
            const res = await fetch(getApiUrl(`/api/v1/investigations?${params}`), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                investigations = await res.json();
            } else if (res.status === 401) {
                error = 'You are not authorized to view investigations.';
            } else {
                error = 'Failed to load investigations.';
            }
        } catch (e) {
            error = 'Network error while loading investigations.';
        } finally {
            loading = false;
        }
    };
    
    const loadStats = async () => {
        try {
            const res = await fetch(getApiUrl('/api/v1/investigations/stats'), {
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
    
    const createNewInvestigation = () => {
        goto('/investigations/create');
    };
    
    const viewInvestigation = (investigationId: string) => {
        goto(`/investigations/${investigationId}`);
    };
    
    const getStatusColor = (status: string) => {
        switch (status) {
            case 'active': return 'default';
            case 'on_hold': return 'secondary';
            case 'completed': return 'outline';
            case 'archived': return 'destructive';
            default: return 'secondary';
        }
    };
    
    const getPriorityColor = (priority: string) => {
        switch (priority) {
            case 'urgent': return 'destructive';
            case 'high': return 'secondary';
            case 'medium': return 'default';
            case 'low': return 'outline';
            default: return 'secondary';
        }
    };
    
    const handleSearch = () => {
        loadInvestigations();
    };
    
    const handleFilterChange = () => {
        loadInvestigations();
    };
</script>

<svelte:head>
    <title>OSINT Investigations - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
    <div class="space-y-8">
        <!-- Header -->
        <div class="flex items-center justify-between">
            <div>
                <h2 class="text-3xl font-bold tracking-tight">OSINT Investigations</h2>
                <p class="text-muted-foreground">
                    Organize and manage your investigation cases
                </p>
            </div>
            <Button onclick={createNewInvestigation}>
                <Plus class="mr-2 h-4 w-4" />
                New Investigation
            </Button>
        </div>
        
        <!-- Statistics Cards -->
        <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Active Cases</CardTitle>
                    <FileText class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.active}</div>
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Completed</CardTitle>
                    <CheckCircle class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.completed}</div>
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Overdue</CardTitle>
                    <AlertTriangle class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.overdue}</div>
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Evidence Items</CardTitle>
                    <BarChart3 class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.evidence_items}</div>
                </CardContent>
            </Card>
        </div>
        
        <!-- Filters and Search -->
        <Card>
            <CardContent class="pt-6">
                <div class="flex flex-col md:flex-row gap-4">
                    <div class="flex-1 relative">
                        <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                        <Input
                            bind:value={searchQuery}
                            on:input={handleSearch}
                            placeholder="Search investigations..."
                            class="pl-10"
                        />
                    </div>
                    <div class="flex gap-2">
                        <Select bind:value={statusFilter} onValueChange={handleFilterChange}>
                            <SelectTrigger class="w-40">
                                <SelectValue placeholder="All Status" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="">All Status</SelectItem>
                                <SelectItem value="active">Active</SelectItem>
                                <SelectItem value="on_hold">On Hold</SelectItem>
                                <SelectItem value="completed">Completed</SelectItem>
                                <SelectItem value="archived">Archived</SelectItem>
                            </SelectContent>
                        </Select>
                        
                        <Select bind:value={priorityFilter} onValueChange={handleFilterChange}>
                            <SelectTrigger class="w-40">
                                <SelectValue placeholder="All Priority" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="">All Priority</SelectItem>
                                <SelectItem value="urgent">Urgent</SelectItem>
                                <SelectItem value="high">High</SelectItem>
                                <SelectItem value="medium">Medium</SelectItem>
                                <SelectItem value="low">Low</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </div>
            </CardContent>
        </Card>
        
        <!-- Error Message -->
        {#if error}
            <Card class="border-destructive">
                <CardContent class="pt-6">
                    <div class="flex items-center space-x-2 text-destructive">
                        <p>{error}</p>
                    </div>
                </CardContent>
            </Card>
        {/if}
        
        <!-- Investigations List -->
        {#if loading}
            <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {#each Array(6) as _}
                    <Card class="animate-pulse">
                        <CardHeader>
                            <div class="h-4 bg-gray-200 rounded w-3/4"></div>
                            <div class="h-3 bg-gray-200 rounded w-1/2"></div>
                        </CardHeader>
                        <CardContent>
                            <div class="space-y-2">
                                <div class="h-3 bg-gray-200 rounded"></div>
                                <div class="h-3 bg-gray-200 rounded w-5/6"></div>
                            </div>
                        </CardContent>
                    </Card>
                {/each}
            </div>
        {:else if investigations.length === 0}
            <Card>
                <CardContent class="pt-6">
                    <div class="flex flex-col items-center justify-center space-y-3 py-12">
                        <FileText class="h-12 w-12 text-muted-foreground" />
                        <div class="text-center">
                            <h3 class="text-lg font-semibold">No investigations yet</h3>
                            <p class="text-muted-foreground mb-4">
                                Create your first investigation to start organizing your research.
                            </p>
                            <Button onclick={createNewInvestigation}>
                                <Plus class="mr-2 h-4 w-4" />
                                Create Investigation
                            </Button>
                        </div>
                    </div>
                </CardContent>
            </Card>
        {:else}
            <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {#each investigations as investigation}
                    <Card class="hover:shadow-md transition-shadow cursor-pointer" on:click={() => viewInvestigation(investigation.id)}>
                        <CardHeader class="pb-2">
                            <div class="flex items-start justify-between">
                                <CardTitle class="text-lg line-clamp-2">{investigation.title || 'Untitled Investigation'}</CardTitle>
                                <Badge variant={getPriorityColor(investigation.priority)} class="text-xs">
                                    {investigation.priority || 'Medium'}
                                </Badge>
                            </div>
                            {#if investigation.description}
                                <CardDescription class="line-clamp-2">
                                    {investigation.description}
                                </CardDescription>
                            {/if}
                        </CardHeader>
                        <CardContent class="space-y-4">
                            <div class="flex items-center justify-between">
                                <Badge variant={getStatusColor(investigation.status)}>
                                    {investigation.status || 'Active'}
                                </Badge>
                                <div class="flex items-center text-sm text-muted-foreground">
                                    <Clock class="mr-1 h-3 w-3" />
                                    {getRelativeTime(investigation.created_at)}
                                </div>
                            </div>
                            
                            <div class="flex items-center justify-between text-sm">
                                <div class="flex items-center text-muted-foreground">
                                    <BarChart3 class="mr-1 h-3 w-3" />
                                    {investigation.evidence_count || 0} evidence
                                </div>
                                {#if investigation.deadline}
                                    <div class="flex items-center text-muted-foreground">
                                        <AlertTriangle class="mr-1 h-3 w-3" />
                                        Due {formatDate(investigation.deadline)}
                                    </div>
                                {/if}
                            </div>
                            
                            {#if investigation.tags && investigation.tags.length > 0}
                                <div class="flex flex-wrap gap-1">
                                    {#each investigation.tags.slice(0, 3) as tag}
                                        <Badge variant="outline" class="text-xs">
                                            {tag}
                                        </Badge>
                                    {/each}
                                    {#if investigation.tags.length > 3}
                                        <span class="text-xs text-muted-foreground">
                                            +{investigation.tags.length - 3} more
                                        </span>
                                    {/if}
                                </div>
                            {/if}
                        </CardContent>
                    </Card>
                {/each}
            </div>
        {/if}
    </div>
</DashboardLayout>

