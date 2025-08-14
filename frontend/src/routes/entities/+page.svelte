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
    import { Progress } from '$lib/components/ui/progress';
    import { 
        Search, 
        Filter, 
        User, 
        Building, 
        MapPin, 
        Calendar,
        Link2,
        Eye,
        Merge,
        Plus,
        BarChart3,
        Zap,
        Globe,
        Users
    } from 'lucide-svelte';
    
    let loading = false;
    let error = '';
    let searchQuery = '';
    let entityTypeFilter = '';
    let statusFilter = '';
    let confidenceFilter = '';
    
    let entities: any[] = [];
    let stats = {
        total_entities: 0,
        persons: 0,
        organizations: 0,
        locations: 0,
        avg_confidence: 0,
        linked_entities: 0,
        unlinked_entities: 0
    };
    
    let currentPage = 1;
    let totalPages = 1;
    let totalEntities = 0;
    let pageSize = 20;
    
    onMount(async () => {
        // Initialize auth and check if user is authenticated
        await auth.init();
        
        // Redirect to login if not authenticated
        if (!$isAuthenticated) {
            goto('/auth/login?redirect=/entities');
            return;
        }
        
        // Load entities data
        await loadEntities();
        await loadStats();
    });
    
    const loadEntities = async () => {
        loading = true;
        try {
            const params = new URLSearchParams();
            if (searchQuery) params.set('search', searchQuery);
            if (entityTypeFilter) params.set('entity_type', entityTypeFilter);
            if (statusFilter) params.set('status', statusFilter);
            if (confidenceFilter) params.set('confidence', confidenceFilter);
            params.set('page', currentPage.toString());
            params.set('size', pageSize.toString());
            
            const res = await fetch(getApiUrl(`/api/v1/entities?${params}`), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                const data = await res.json();
                entities = data.items || data.entities || [];
                totalEntities = data.total || entities.length;
                totalPages = Math.ceil(totalEntities / pageSize);
            } else if (res.status === 401) {
                error = 'You are not authorized to view entities.';
            } else {
                error = 'Failed to load entities.';
            }
        } catch (e) {
            error = 'Network error while loading entities.';
        } finally {
            loading = false;
        }
    };
    
    const loadStats = async () => {
        try {
            const res = await fetch(getApiUrl('/api/v1/entities/stats'), {
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
        currentPage = 1;
        loadEntities();
    };
    
    const handleFilterChange = () => {
        currentPage = 1;
        loadEntities();
    };
    
    const clearFilters = () => {
        searchQuery = '';
        entityTypeFilter = '';
        statusFilter = '';
        confidenceFilter = '';
        currentPage = 1;
        loadEntities();
    };
    
    const viewEntity = (entityId: string) => {
        goto(`/entities/${entityId}`);
    };
    
    const linkEntities = () => {
        goto('/entities/link');
    };
    
    const createEntity = () => {
        goto('/entities/create');
    };
    
    const getEntityTypeIcon = (type: string) => {
        switch (type.toLowerCase()) {
            case 'person': return User;
            case 'organization': return Building;
            case 'location': return MapPin;
            case 'event': return Calendar;
            default: return Globe;
        }
    };
    
    const getEntityTypeColor = (type: string) => {
        switch (type.toLowerCase()) {
            case 'person': return 'default';
            case 'organization': return 'secondary';
            case 'location': return 'outline';
            case 'event': return 'destructive';
            default: return 'secondary';
        }
    };
    
    const getStatusColor = (status: string) => {
        switch (status.toLowerCase()) {
            case 'linked': return 'default';
            case 'verified': return 'outline';
            case 'pending': return 'secondary';
            case 'disputed': return 'destructive';
            default: return 'secondary';
        }
    };
    
    const getConfidenceColor = (confidence: number) => {
        if (confidence >= 0.8) return 'text-green-600';
        if (confidence >= 0.6) return 'text-yellow-600';
        return 'text-red-600';
    };
    
    const formatConfidence = (confidence: number) => {
        return Math.round(confidence * 100);
    };
</script>

<svelte:head>
    <title>Entity Management - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
    <div class="space-y-6">
        <!-- Header -->
        <div class="flex items-center justify-between">
            <div>
                <h2 class="text-3xl font-bold tracking-tight">Entity Management</h2>
                <p class="text-muted-foreground">
                    Manage and link extracted entities from your projects
                </p>
            </div>
            <div class="flex gap-2">
                <Button variant="outline" onclick={linkEntities}>
                    <Link2 class="mr-2 h-4 w-4" />
                    Link Entities
                </Button>
                <Button onclick={createEntity}>
                    <Plus class="mr-2 h-4 w-4" />
                    Create Entity
                </Button>
            </div>
        </div>
        
        <!-- Statistics Cards -->
        <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Total Entities</CardTitle>
                    <BarChart3 class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.total_entities}</div>
                    <div class="text-xs text-muted-foreground">
                        {stats.linked_entities} linked, {stats.unlinked_entities} unlinked
                    </div>
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Persons</CardTitle>
                    <User class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.persons}</div>
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Organizations</CardTitle>
                    <Building class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.organizations}</div>
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Avg. Confidence</CardTitle>
                    <Zap class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{formatConfidence(stats.avg_confidence)}%</div>
                </CardContent>
            </Card>
        </div>
        
        <!-- Filters -->
        <Card>
            <CardContent class="pt-6">
                <div class="flex flex-col md:flex-row gap-4">
                    <div class="flex-1 relative">
                        <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                        <Input
                            bind:value={searchQuery}
                            on:input={handleSearch}
                            placeholder="Search entities by name, text, or properties..."
                            class="pl-10"
                        />
                    </div>
                    <div class="flex gap-2">
                        <Select bind:value={entityTypeFilter} onValueChange={handleFilterChange}>
                            <SelectTrigger class="w-40">
                                <SelectValue placeholder="Entity Type" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="">All Types</SelectItem>
                                <SelectItem value="person">Person</SelectItem>
                                <SelectItem value="organization">Organization</SelectItem>
                                <SelectItem value="location">Location</SelectItem>
                                <SelectItem value="event">Event</SelectItem>
                                <SelectItem value="misc">Miscellaneous</SelectItem>
                            </SelectContent>
                        </Select>
                        
                        <Select bind:value={statusFilter} onValueChange={handleFilterChange}>
                            <SelectTrigger class="w-32">
                                <SelectValue placeholder="Status" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="">All Status</SelectItem>
                                <SelectItem value="linked">Linked</SelectItem>
                                <SelectItem value="verified">Verified</SelectItem>
                                <SelectItem value="pending">Pending</SelectItem>
                                <SelectItem value="disputed">Disputed</SelectItem>
                            </SelectContent>
                        </Select>
                        
                        <Select bind:value={confidenceFilter} onValueChange={handleFilterChange}>
                            <SelectTrigger class="w-32">
                                <SelectValue placeholder="Confidence" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="">All</SelectItem>
                                <SelectItem value="high">High (80%+)</SelectItem>
                                <SelectItem value="medium">Medium (60-80%)</SelectItem>
                                <SelectItem value="low">Low (&lt;60%)</SelectItem>
                            </SelectContent>
                        </Select>
                        
                        <Button variant="outline" onclick={clearFilters}>
                            Clear
                        </Button>
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
        
        <!-- Results Header -->
        {#if totalEntities > 0}
            <div class="flex items-center justify-between">
                <p class="text-sm text-muted-foreground">
                    {totalEntities.toLocaleString()} entities found
                </p>
                <div class="flex items-center gap-2">
                    <span class="text-sm text-muted-foreground">Sort by:</span>
                    <Select>
                        <SelectTrigger class="w-32">
                            <SelectValue placeholder="Relevance" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="relevance">Relevance</SelectItem>
                            <SelectItem value="confidence">Confidence</SelectItem>
                            <SelectItem value="mentions">Mentions</SelectItem>
                            <SelectItem value="created">Created</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </div>
        {/if}
        
        <!-- Entities List -->
        {#if loading}
            <div class="space-y-4">
                {#each Array(10) as _}
                    <Card class="animate-pulse">
                        <CardContent class="pt-6">
                            <div class="flex items-start space-x-4">
                                <div class="w-12 h-12 bg-gray-200 rounded-full"></div>
                                <div class="flex-1 space-y-2">
                                    <div class="h-4 bg-gray-200 rounded w-3/4"></div>
                                    <div class="h-3 bg-gray-200 rounded w-1/2"></div>
                                    <div class="h-3 bg-gray-200 rounded w-1/4"></div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                {/each}
            </div>
        {:else if entities.length === 0}
            <Card>
                <CardContent class="pt-6">
                    <div class="flex flex-col items-center justify-center space-y-3 py-12">
                        <Users class="h-12 w-12 text-muted-foreground" />
                        <div class="text-center">
                            <h3 class="text-lg font-semibold">No entities found</h3>
                            <p class="text-muted-foreground mb-4">
                                Try adjusting your search or filters, or create a new entity.
                            </p>
                            <Button onclick={createEntity}>
                                <Plus class="mr-2 h-4 w-4" />
                                Create Entity
                            </Button>
                        </div>
                    </div>
                </CardContent>
            </Card>
        {:else}
            <div class="space-y-4">
                {#each entities as entity}
                    <Card class="hover:shadow-md transition-shadow cursor-pointer" on:click={() => viewEntity(entity.id)}>
                        <CardContent class="pt-6">
                            <div class="flex items-start space-x-4">
                                <!-- Entity Icon -->
                                <div class="w-12 h-12 bg-muted rounded-full flex items-center justify-center">
                                    <svelte:component this={getEntityTypeIcon(entity.entity_type)} class="h-6 w-6 text-muted-foreground" />
                                </div>
                                
                                <!-- Entity Info -->
                                <div class="flex-1 space-y-2">
                                    <div class="flex items-start justify-between">
                                        <div>
                                            <h3 class="font-semibold text-lg">{entity.name || entity.text}</h3>
                                            {#if entity.canonical_name && entity.canonical_name !== entity.name}
                                                <p class="text-sm text-muted-foreground">
                                                    Also known as: {entity.canonical_name}
                                                </p>
                                            {/if}
                                        </div>
                                        <div class="flex items-center gap-2">
                                            <Badge variant={getEntityTypeColor(entity.entity_type)}>
                                                {entity.entity_type}
                                            </Badge>
                                            <Badge variant={getStatusColor(entity.status || 'pending')}>
                                                {entity.status || 'Pending'}
                                            </Badge>
                                        </div>
                                    </div>
                                    
                                    <!-- Confidence Score -->
                                    <div class="flex items-center space-x-2">
                                        <span class="text-sm text-muted-foreground">Confidence:</span>
                                        <div class="flex-1 max-w-32">
                                            <Progress value={formatConfidence(entity.confidence_score || 0)} />
                                        </div>
                                        <span class={`text-sm font-medium ${getConfidenceColor(entity.confidence_score || 0)}`}>
                                            {formatConfidence(entity.confidence_score || 0)}%
                                        </span>
                                    </div>
                                    
                                    <!-- Entity Details -->
                                    <div class="flex items-center justify-between text-sm text-muted-foreground">
                                        <div class="flex items-center space-x-4">
                                            <div class="flex items-center">
                                                <Eye class="mr-1 h-3 w-3" />
                                                {entity.mention_count || 0} mentions
                                            </div>
                                            {#if entity.properties && Object.keys(entity.properties).length > 0}
                                                <div class="flex items-center">
                                                    <BarChart3 class="mr-1 h-3 w-3" />
                                                    {Object.keys(entity.properties).length} properties
                                                </div>
                                            {/if}
                                            {#if entity.linked_entities_count}
                                                <div class="flex items-center">
                                                    <Link2 class="mr-1 h-3 w-3" />
                                                    {entity.linked_entities_count} linked
                                                </div>
                                            {/if}
                                        </div>
                                        <div class="flex items-center">
                                            <Calendar class="mr-1 h-3 w-3" />
                                            {getRelativeTime(entity.first_seen || entity.created_at)}
                                        </div>
                                    </div>
                                    
                                    <!-- Additional Properties -->
                                    {#if entity.properties}
                                        <div class="flex flex-wrap gap-1">
                                            {#each Object.entries(entity.properties).slice(0, 3) as [key, value]}
                                                <Badge variant="outline" class="text-xs">
                                                    {key}: {value}
                                                </Badge>
                                            {/each}
                                            {#if Object.keys(entity.properties).length > 3}
                                                <span class="text-xs text-muted-foreground">
                                                    +{Object.keys(entity.properties).length - 3} more
                                                </span>
                                            {/if}
                                        </div>
                                    {/if}
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                {/each}
            </div>
            
            <!-- Pagination -->
            {#if totalPages > 1}
                <div class="flex items-center justify-center space-x-2 pt-6">
                    <Button
                        variant="outline"
                        disabled={currentPage === 1}
                        on:click={() => { currentPage--; loadEntities(); }}
                    >
                        Previous
                    </Button>
                    
                    <span class="text-sm text-muted-foreground">
                        Page {currentPage} of {totalPages}
                    </span>
                    
                    <Button
                        variant="outline"
                        disabled={currentPage >= totalPages}
                        on:click={() => { currentPage++; loadEntities(); }}
                    >
                        Next
                    </Button>
                </div>
            {/if}
        {/if}
    </div>
</DashboardLayout>