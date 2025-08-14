<script lang="ts">
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { isAuthenticated, auth } from '$lib/stores/auth';
    import { getApiUrl, formatDate, getRelativeTime } from '$lib/utils';
    import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
    import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
    import { Button } from '$lib/components/ui/button';
    import { Badge } from '$lib/components/ui/badge';
    import { Input } from '$lib/components/ui/input';
    import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
    import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
    import { 
        Plus, 
        Search, 
        Settings, 
        Play,
        FileText,
        Database,
        Zap,
        Download,
        Copy,
        Edit,
        Trash2,
        BarChart3,
        Clock,
        CheckCircle,
        AlertTriangle
    } from 'lucide-svelte';
    
    let loading = false;
    let error = '';
    let searchQuery = '';
    let schemaTypeFilter = '';
    let methodFilter = '';
    let activeTab = 'schemas';
    
    let schemas: any[] = [];
    let templates: any[] = [];
    let jobs: any[] = [];
    
    let stats = {
        total_schemas: 0,
        active_schemas: 0,
        total_extractions: 0,
        avg_success_rate: 0,
        pending_jobs: 0,
        completed_jobs: 0
    };
    
    onMount(async () => {
        // Initialize auth and check if user is authenticated
        await auth.init();
        
        // Redirect to login if not authenticated
        if (!$isAuthenticated) {
            goto('/auth/login?redirect=/extraction');
            return;
        }
        
        // Load extraction data
        await loadData();
    });
    
    const loadData = async () => {
        loading = true;
        try {
            await Promise.all([
                loadSchemas(),
                loadTemplates(),
                loadJobs(),
                loadStats()
            ]);
        } catch (e) {
            error = 'Failed to load extraction data.';
        } finally {
            loading = false;
        }
    };
    
    const loadSchemas = async () => {
        try {
            const params = new URLSearchParams();
            if (searchQuery) params.set('search', searchQuery);
            if (schemaTypeFilter) params.set('schema_type', schemaTypeFilter);
            if (methodFilter) params.set('extraction_method', methodFilter);
            
            const res = await fetch(getApiUrl(`/api/v1/extraction/schemas?${params}`), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                schemas = await res.json();
            }
        } catch (e) {
            console.error('Failed to load schemas:', e);
        }
    };
    
    const loadTemplates = async () => {
        try {
            const params = searchQuery ? `?search=${encodeURIComponent(searchQuery)}` : '';
            const res = await fetch(getApiUrl(`/api/v1/extraction/templates${params}`), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                templates = await res.json();
            }
        } catch (e) {
            console.error('Failed to load templates:', e);
        }
    };
    
    const loadJobs = async () => {
        try {
            const res = await fetch(getApiUrl('/api/v1/extraction/jobs'), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                jobs = await res.json();
            }
        } catch (e) {
            console.error('Failed to load jobs:', e);
        }
    };
    
    const loadStats = async () => {
        try {
            const res = await fetch(getApiUrl('/api/v1/extraction/stats'), {
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
    
    const handleSearch = () => {
        switch (activeTab) {
            case 'schemas':
                loadSchemas();
                break;
            case 'templates':
                loadTemplates();
                break;
            case 'jobs':
                loadJobs();
                break;
        }
    };
    
    const handleFilterChange = () => {
        if (activeTab === 'schemas') {
            loadSchemas();
        }
    };
    
    const createNewSchema = () => {
        goto('/extraction/schemas/create');
    };
    
    const createFromTemplate = () => {
        goto('/extraction/templates');
    };
    
    const viewSchema = (schemaId: string) => {
        goto(`/extraction/schemas/${schemaId}`);
    };
    
    const editSchema = (schemaId: string) => {
        goto(`/extraction/schemas/${schemaId}/edit`);
    };
    
    const viewTemplate = (templateId: string) => {
        goto(`/extraction/templates/${templateId}`);
    };
    
    const viewJob = (jobId: string) => {
        goto(`/extraction/jobs/${jobId}`);
    };
    
    const runExtractionJob = async (schemaId: string) => {
        try {
            const res = await fetch(getApiUrl('/api/v1/extraction/jobs'), {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                },
                body: JSON.stringify({
                    schema_id: schemaId,
                    name: `Extraction Job - ${new Date().toLocaleString()}`
                })
            });
            
            if (res.ok) {
                const job = await res.json();
                await loadJobs();
                goto(`/extraction/jobs/${job.id}`);
            }
        } catch (e) {
            console.error('Failed to run extraction job:', e);
        }
    };
    
    const duplicateSchema = async (schemaId: string) => {
        try {
            const res = await fetch(getApiUrl(`/api/v1/extraction/schemas/${schemaId}/duplicate`), {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                await loadSchemas();
            }
        } catch (e) {
            console.error('Failed to duplicate schema:', e);
        }
    };
    
    const getSchemaTypeColor = (type: string) => {
        switch (type.toLowerCase()) {
            case 'article': return 'default';
            case 'product': return 'secondary';
            case 'person': return 'outline';
            case 'organization': return 'destructive';
            default: return 'secondary';
        }
    };
    
    const getMethodColor = (method: string) => {
        switch (method.toLowerCase()) {
            case 'rule_based': return 'default';
            case 'llm_extract': return 'secondary';
            case 'ml_model': return 'outline';
            case 'hybrid': return 'destructive';
            default: return 'secondary';
        }
    };
    
    const getJobStatusColor = (status: string) => {
        switch (status.toLowerCase()) {
            case 'pending': return 'secondary';
            case 'in_progress': return 'default';
            case 'completed': return 'outline';
            case 'failed': return 'destructive';
            default: return 'secondary';
        }
    };
    
    const formatSuccessRate = (rate: number) => {
        return Math.round(rate * 100);
    };
</script>

<svelte:head>
    <title>Extraction Schema Builder - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
    <div class="space-y-6">
        <!-- Header -->
        <div class="flex items-center justify-between">
            <div>
                <h2 class="text-3xl font-bold tracking-tight">Extraction Schema Builder</h2>
                <p class="text-muted-foreground">
                    Create and manage custom data extraction schemas
                </p>
            </div>
            <div class="flex gap-2">
                <Button variant="outline" onclick={createFromTemplate}>
                    <Database class="mr-2 h-4 w-4" />
                    From Template
                </Button>
                <Button onclick={createNewSchema}>
                    <Plus class="mr-2 h-4 w-4" />
                    New Schema
                </Button>
            </div>
        </div>
        
        <!-- Statistics Cards -->
        <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Active Schemas</CardTitle>
                    <Settings class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.active_schemas}</div>
                    <div class="text-xs text-muted-foreground">
                        of {stats.total_schemas} total schemas
                    </div>
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Total Extractions</CardTitle>
                    <Zap class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.total_extractions}</div>
                    <div class="text-xs text-muted-foreground">
                        {formatSuccessRate(stats.avg_success_rate)}% success rate
                    </div>
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Active Jobs</CardTitle>
                    <BarChart3 class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.pending_jobs}</div>
                    <div class="text-xs text-muted-foreground">
                        {stats.completed_jobs} completed
                    </div>
                </CardContent>
            </Card>
        </div>
        
        <!-- Search and Filters -->
        <Card>
            <CardContent class="pt-6">
                <div class="flex flex-col md:flex-row gap-4">
                    <div class="flex-1 relative">
                        <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                        <Input
                            bind:value={searchQuery}
                            on:input={handleSearch}
                            placeholder="Search schemas, templates, or jobs..."
                            class="pl-10"
                        />
                    </div>
                    {#if activeTab === 'schemas'}
                        <div class="flex gap-2">
                            <Select bind:value={schemaTypeFilter} onValueChange={handleFilterChange}>
                                <SelectTrigger class="w-40">
                                    <SelectValue placeholder="Schema Type" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="">All Types</SelectItem>
                                    <SelectItem value="article">Article</SelectItem>
                                    <SelectItem value="product">Product</SelectItem>
                                    <SelectItem value="person">Person</SelectItem>
                                    <SelectItem value="organization">Organization</SelectItem>
                                    <SelectItem value="event">Event</SelectItem>
                                    <SelectItem value="custom">Custom</SelectItem>
                                </SelectContent>
                            </Select>
                            
                            <Select bind:value={methodFilter} onValueChange={handleFilterChange}>
                                <SelectTrigger class="w-40">
                                    <SelectValue placeholder="Method" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="">All Methods</SelectItem>
                                    <SelectItem value="rule_based">Rule Based</SelectItem>
                                    <SelectItem value="llm_extract">LLM Extract</SelectItem>
                                    <SelectItem value="ml_model">ML Model</SelectItem>
                                    <SelectItem value="hybrid">Hybrid</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    {/if}
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
        
        <!-- Tabs -->
        <Tabs bind:value={activeTab} class="w-full">
            <TabsList class="grid w-full grid-cols-3">
                <TabsTrigger value="schemas">Schemas</TabsTrigger>
                <TabsTrigger value="templates">Templates</TabsTrigger>
                <TabsTrigger value="jobs">Jobs</TabsTrigger>
            </TabsList>
            
            <!-- Schemas Tab -->
            <TabsContent value="schemas" class="space-y-4">
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
                {:else if schemas.length === 0}
                    <Card>
                        <CardContent class="pt-6">
                            <div class="flex flex-col items-center justify-center space-y-3 py-12">
                                <Settings class="h-12 w-12 text-muted-foreground" />
                                <div class="text-center">
                                    <h3 class="text-lg font-semibold">No schemas yet</h3>
                                    <p class="text-muted-foreground mb-4">
                                        Create your first extraction schema to start extracting structured data.
                                    </p>
                                    <div class="flex gap-2 justify-center">
                                        <Button variant="outline" onclick={createFromTemplate}>
                                            <Database class="mr-2 h-4 w-4" />
                                            From Template
                                        </Button>
                                        <Button onclick={createNewSchema}>
                                            <Plus class="mr-2 h-4 w-4" />
                                            Create Schema
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                {:else}
                    <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {#each schemas as schema}
                            <Card class="hover:shadow-md transition-shadow">
                                <CardHeader class="pb-2">
                                    <div class="flex items-start justify-between">
                                        <CardTitle class="text-lg line-clamp-2">{schema.name}</CardTitle>
                                        <div class="flex items-center gap-1">
                                            <Button variant="ghost" size="sm" onclick={() => editSchema(schema.id)}>
                                                <Edit class="h-3 w-3" />
                                            </Button>
                                            <Button variant="ghost" size="sm" onclick={() => duplicateSchema(schema.id)}>
                                                <Copy class="h-3 w-3" />
                                            </Button>
                                        </div>
                                    </div>
                                    {#if schema.description}
                                        <CardDescription class="line-clamp-2">
                                            {schema.description}
                                        </CardDescription>
                                    {/if}
                                </CardHeader>
                                <CardContent class="space-y-3">
                                    <div class="flex items-center justify-between">
                                        <Badge variant={getSchemaTypeColor(schema.schema_type)}>
                                            {schema.schema_type}
                                        </Badge>
                                        <Badge variant={getMethodColor(schema.extraction_method)}>
                                            {schema.extraction_method}
                                        </Badge>
                                    </div>
                                    
                                    <div class="flex items-center justify-between text-sm">
                                        <div class="flex items-center text-muted-foreground">
                                            <Zap class="mr-1 h-3 w-3" />
                                            {schema.usage_count || 0} uses
                                        </div>
                                        <div class="flex items-center text-muted-foreground">
                                            <BarChart3 class="mr-1 h-3 w-3" />
                                            {formatSuccessRate(schema.success_rate || 0)}% success
                                        </div>
                                    </div>
                                    
                                    <div class="flex items-center justify-between text-xs text-muted-foreground">
                                        <span>Updated {getRelativeTime(schema.updated_at)}</span>
                                        <span class={schema.is_active ? 'text-green-600' : 'text-gray-500'}>
                                            {schema.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </div>
                                    
                                    <div class="flex gap-2 pt-2">
                                        <Button variant="outline" size="sm" class="flex-1" onclick={() => viewSchema(schema.id)}>
                                            <Settings class="mr-1 h-3 w-3" />
                                            Configure
                                        </Button>
                                        <Button size="sm" class="flex-1" onclick={() => runExtractionJob(schema.id)}>
                                            <Play class="mr-1 h-3 w-3" />
                                            Run
                                        </Button>
                                    </div>
                                </CardContent>
                            </Card>
                        {/each}
                    </div>
                {/if}
            </TabsContent>
            
            <!-- Templates Tab -->
            <TabsContent value="templates" class="space-y-4">
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
                {:else if templates.length === 0}
                    <Card>
                        <CardContent class="pt-6">
                            <div class="flex flex-col items-center justify-center space-y-3 py-12">
                                <Database class="h-12 w-12 text-muted-foreground" />
                                <div class="text-center">
                                    <h3 class="text-lg font-semibold">No templates available</h3>
                                    <p class="text-muted-foreground">
                                        Templates help you quickly create extraction schemas for common use cases.
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                {:else}
                    <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {#each templates as template}
                            <Card class="hover:shadow-md transition-shadow cursor-pointer" on:click={() => viewTemplate(template.id)}>
                                <CardHeader class="pb-2">
                                    <div class="flex items-start justify-between">
                                        <CardTitle class="text-lg line-clamp-2">{template.name}</CardTitle>
                                        {#if template.is_featured}
                                            <Badge variant="secondary" class="text-xs">Featured</Badge>
                                        {/if}
                                    </div>
                                    {#if template.description}
                                        <CardDescription class="line-clamp-2">
                                            {template.description}
                                        </CardDescription>
                                    {/if}
                                </CardHeader>
                                <CardContent class="space-y-3">
                                    <div class="flex items-center justify-between">
                                        <Badge variant="outline">
                                            {template.category}
                                        </Badge>
                                        <div class="flex items-center text-sm text-muted-foreground">
                                            <Download class="mr-1 h-3 w-3" />
                                            {template.download_count || 0}
                                        </div>
                                    </div>
                                    
                                    {#if template.use_cases && template.use_cases.length > 0}
                                        <div class="flex flex-wrap gap-1">
                                            {#each template.use_cases.slice(0, 2) as useCase}
                                                <Badge variant="outline" class="text-xs">
                                                    {useCase}
                                                </Badge>
                                            {/each}
                                            {#if template.use_cases.length > 2}
                                                <span class="text-xs text-muted-foreground">
                                                    +{template.use_cases.length - 2} more
                                                </span>
                                            {/if}
                                        </div>
                                    {/if}
                                    
                                    <div class="flex items-center justify-between text-xs text-muted-foreground">
                                        <span>Rating: {template.rating || 0}/5</span>
                                        <span>{template.is_public ? 'Public' : 'Private'}</span>
                                    </div>
                                </CardContent>
                            </Card>
                        {/each}
                    </div>
                {/if}
            </TabsContent>
            
            <!-- Jobs Tab -->
            <TabsContent value="jobs" class="space-y-4">
                {#if loading}
                    <div class="space-y-4">
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
                {:else if jobs.length === 0}
                    <Card>
                        <CardContent class="pt-6">
                            <div class="flex flex-col items-center justify-center space-y-3 py-12">
                                <Clock class="h-12 w-12 text-muted-foreground" />
                                <div class="text-center">
                                    <h3 class="text-lg font-semibold">No extraction jobs</h3>
                                    <p class="text-muted-foreground">
                                        Extraction jobs will appear here when you run schemas.
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                {:else}
                    <div class="space-y-4">
                        {#each jobs as job}
                            <Card class="hover:shadow-md transition-shadow cursor-pointer" on:click={() => viewJob(job.id)}>
                                <CardContent class="pt-6">
                                    <div class="flex items-start justify-between">
                                        <div class="flex-1">
                                            <h3 class="font-semibold">{job.name}</h3>
                                            {#if job.description}
                                                <p class="text-sm text-muted-foreground mt-1">
                                                    {job.description}
                                                </p>
                                            {/if}
                                            <div class="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                                                <span>Schema: {job.schema_name || 'Unknown'}</span>
                                                <span>Started {getRelativeTime(job.started_at || job.created_at)}</span>
                                            </div>
                                        </div>
                                        <div class="flex items-center gap-2">
                                            <Badge variant={getJobStatusColor(job.status)}>
                                                {job.status}
                                            </Badge>
                                        </div>
                                    </div>
                                    
                                    {#if job.total_pages > 0}
                                        <div class="mt-4">
                                            <div class="flex items-center justify-between text-sm mb-2">
                                                <span>Progress: {job.processed_pages || 0} of {job.total_pages}</span>
                                                <span>{Math.round(((job.processed_pages || 0) / job.total_pages) * 100)}%</span>
                                            </div>
                                            <div class="w-full bg-gray-200 rounded-full h-2">
                                                <div 
                                                    class="bg-blue-600 h-2 rounded-full transition-all duration-300"
                                                    style="width: {Math.round(((job.processed_pages || 0) / job.total_pages) * 100)}%"
                                                ></div>
                                            </div>
                                        </div>
                                    {/if}
                                    
                                    <div class="flex items-center justify-between mt-4 text-sm text-muted-foreground">
                                        <div class="flex items-center gap-4">
                                            <div class="flex items-center">
                                                <CheckCircle class="mr-1 h-3 w-3 text-green-600" />
                                                {job.successful_extractions || 0} success
                                            </div>
                                            <div class="flex items-center">
                                                <AlertTriangle class="mr-1 h-3 w-3 text-red-600" />
                                                {job.failed_extractions || 0} failed
                                            </div>
                                        </div>
                                        {#if job.estimated_completion}
                                            <span>ETA: {formatDate(job.estimated_completion)}</span>
                                        {/if}
                                    </div>
                                </CardContent>
                            </Card>
                        {/each}
                    </div>
                {/if}
            </TabsContent>
        </Tabs>
    </div>
</DashboardLayout>

<style>
    .line-clamp-2 {
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
</style>