<script lang="ts">
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { isAuthenticated, auth } from '$lib/stores/auth';
    import { getApiUrl, formatDate, getRelativeTime } from '$lib/utils';
    import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
    import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
    import { Button } from '$lib/components/ui/button';
    import { Badge } from '$lib/components/ui/badge';
    import { Search, Filter, Calendar, ExternalLink, Star, Bookmark } from 'lucide-svelte';
    
    let query = '';
    let results: any[] = [];
    let loading = false;
    let error = '';
    let totalResults = 0;
    let currentPage = 1;
    let pageSize = 20;
    let filters = {
        project: '',
        dateFrom: '',
        dateTo: '',
        contentType: '',
        domain: ''
    };
    let showFilters = false;
    let projects: any[] = [];
    
    onMount(async () => {
        // Initialize auth and check if user is authenticated
        await auth.init();
        
        // Redirect to login if not authenticated
        if (!$isAuthenticated) {
            goto('/auth/login?redirect=/search');
            return;
        }
        
        // Load user projects for filtering
        await loadProjects();
        
        // Check for URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        const urlQuery = urlParams.get('q');
        if (urlQuery) {
            query = urlQuery;
            await performSearch();
        }
    });
    
    const loadProjects = async () => {
        try {
            const res = await fetch(getApiUrl('/api/v1/projects'), { 
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            if (res.ok) {
                projects = await res.json();
            }
        } catch (e) {
            console.error('Failed to load projects for filtering:', e);
        }
    };
    
    const performSearch = async () => {
        if (!query.trim()) {
            error = 'Please enter a search query';
            return;
        }
        
        loading = true;
        error = '';
        
        try {
            const searchParams = new URLSearchParams({
                q: query.trim(),
                page: currentPage.toString(),
                size: pageSize.toString(),
                ...Object.fromEntries(
                    Object.entries(filters).filter(([_, v]) => v !== '')
                )
            });
            
            const res = await fetch(getApiUrl(`/api/v1/search?${searchParams}`), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                const data = await res.json();
                results = data.results || data.items || [];
                totalResults = data.total || results.length;
                
                // Update URL with search query
                const url = new URL(window.location.href);
                url.searchParams.set('q', query);
                window.history.replaceState({}, '', url);
            } else if (res.status === 401) {
                error = 'You are not authorized to perform searches.';
            } else {
                const errorData = await res.json();
                error = errorData.detail || 'Search failed';
            }
        } catch (e) {
            error = 'Network error while searching.';
        } finally {
            loading = false;
        }
    };
    
    const handleKeyPress = (event: KeyboardEvent) => {
        if (event.key === 'Enter') {
            currentPage = 1;
            performSearch();
        }
    };
    
    const clearFilters = () => {
        filters = {
            project: '',
            dateFrom: '',
            dateTo: '',
            contentType: '',
            domain: ''
        };
        currentPage = 1;
        if (query.trim()) {
            performSearch();
        }
    };
    
    const saveSearch = async (query: string) => {
        try {
            const res = await fetch(getApiUrl('/api/v1/library/searches'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                },
                body: JSON.stringify({
                    query,
                    filters,
                    name: `Search: ${query.slice(0, 50)}${query.length > 50 ? '...' : ''}`
                })
            });
            
            if (res.ok) {
                // Show success message or update UI
                console.log('Search saved successfully');
            }
        } catch (e) {
            console.error('Failed to save search:', e);
        }
    };
    
    const starResult = async (resultId: string) => {
        try {
            const res = await fetch(getApiUrl('/api/v1/library/starred'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                },
                body: JSON.stringify({
                    item_type: 'page',
                    item_id: resultId
                })
            });
            
            if (res.ok) {
                // Update UI to show starred state
                console.log('Result starred successfully');
            }
        } catch (e) {
            console.error('Failed to star result:', e);
        }
    };
</script>

<svelte:head>
    <title>Search - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
    <div class="space-y-6">
        <!-- Search Header -->
        <div class="space-y-4">
            <div>
                <h2 class="text-3xl font-bold tracking-tight">Search</h2>
                <p class="text-muted-foreground">
                    Search through your collected web data and archived content.
                </p>
            </div>
            
            <!-- Search Bar -->
            <div class="flex space-x-2">
                <div class="flex-1 relative">
                    <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                    <input
                        type="text"
                        bind:value={query}
                        on:keypress={handleKeyPress}
                        placeholder="Search for content, entities, or topics..."
                        class="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        data-testid="search-input"
                    />
                </div>
                <Button onclick={() => { currentPage = 1; performSearch(); }} disabled={loading}>
                    {#if loading}
                        <div class="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full"></div>
                    {:else}
                        Search
                    {/if}
                </Button>
                <Button variant="outline" onclick={() => showFilters = !showFilters}>
                    <Filter class="h-4 w-4 mr-2" />
                    Filters
                </Button>
                {#if query.trim()}
                    <Button variant="outline" onclick={() => saveSearch(query)}>
                        <Bookmark class="h-4 w-4 mr-2" />
                        Save
                    </Button>
                {/if}
            </div>
        </div>

        <!-- Filters Panel -->
        {#if showFilters}
            <Card>
                <CardHeader>
                    <CardTitle>Search Filters</CardTitle>
                </CardHeader>
                <CardContent>
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
                        <div>
                            <label for="projectFilter" class="block text-sm font-medium text-gray-700 mb-1">
                                Project
                            </label>
                            <select
                                id="projectFilter"
                                bind:value={filters.project}
                                class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                            >
                                <option value="">All Projects</option>
                                {#each projects as project}
                                    <option value={project.id}>{project.name}</option>
                                {/each}
                            </select>
                        </div>
                        
                        <div>
                            <label for="domainFilter" class="block text-sm font-medium text-gray-700 mb-1">
                                Domain
                            </label>
                            <input
                                id="domainFilter"
                                type="text"
                                bind:value={filters.domain}
                                placeholder="example.com"
                                class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                            />
                        </div>
                        
                        <div>
                            <label for="contentTypeFilter" class="block text-sm font-medium text-gray-700 mb-1">
                                Content Type
                            </label>
                            <select
                                id="contentTypeFilter"
                                bind:value={filters.contentType}
                                class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                            >
                                <option value="">All Types</option>
                                <option value="text/html">HTML Pages</option>
                                <option value="application/pdf">PDF Documents</option>
                                <option value="text/plain">Text Files</option>
                            </select>
                        </div>
                        
                        <div>
                            <label for="dateFromFilter" class="block text-sm font-medium text-gray-700 mb-1">
                                From Date
                            </label>
                            <input
                                id="dateFromFilter"
                                type="date"
                                bind:value={filters.dateFrom}
                                class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                            />
                        </div>
                        
                        <div>
                            <label for="dateToFilter" class="block text-sm font-medium text-gray-700 mb-1">
                                To Date
                            </label>
                            <input
                                id="dateToFilter"
                                type="date"
                                bind:value={filters.dateTo}
                                class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                            />
                        </div>
                    </div>
                    
                    <div class="flex justify-between items-center mt-4 pt-4 border-t">
                        <Button variant="outline" onclick={clearFilters}>
                            Clear Filters
                        </Button>
                        <Button onclick={() => { currentPage = 1; performSearch(); }}>
                            Apply Filters
                        </Button>
                    </div>
                </CardContent>
            </Card>
        {/if}

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

        <!-- Results -->
        {#if totalResults > 0}
            <div class="space-y-4">
                <!-- Results Header -->
                <div class="flex items-center justify-between">
                    <p class="text-sm text-muted-foreground">
                        {totalResults.toLocaleString()} result{totalResults !== 1 ? 's' : ''} found
                        {#if query.trim()}for "<strong>{query}</strong>"{/if}
                    </p>
                    <div class="flex items-center space-x-2 text-sm text-muted-foreground">
                        <span>Sort by:</span>
                        <select class="border border-gray-300 rounded px-2 py-1 text-xs">
                            <option value="relevance">Relevance</option>
                            <option value="date_desc">Newest First</option>
                            <option value="date_asc">Oldest First</option>
                        </select>
                    </div>
                </div>

                <!-- Results List -->
                <div class="space-y-4">
                    {#each results as result}
                        <Card class="hover:shadow-md transition-shadow">
                            <CardContent class="pt-6">
                                <div class="space-y-3">
                                    <!-- Result Header -->
                                    <div class="flex items-start justify-between">
                                        <div class="flex-1 space-y-1">
                                            <h3 class="text-lg font-semibold text-blue-600 hover:text-blue-800">
                                                <a href={result.url || result.original_url} target="_blank" rel="noopener noreferrer" class="flex items-center">
                                                    {result.title || result.url || 'Untitled'}
                                                    <ExternalLink class="ml-1 h-3 w-3" />
                                                </a>
                                            </h3>
                                            <p class="text-sm text-green-600">{result.url || result.original_url}</p>
                                        </div>
                                        <div class="flex items-center space-x-2">
                                            <Button variant="ghost" size="sm" onclick={() => starResult(result.id)}>
                                                <Star class="h-4 w-4" />
                                            </Button>
                                        </div>
                                    </div>

                                    <!-- Result Content -->
                                    {#if result.content || result.description}
                                        <p class="text-sm text-gray-700 line-clamp-3">
                                            {result.content || result.description}
                                        </p>
                                    {/if}

                                    <!-- Result Metadata -->
                                    <div class="flex items-center justify-between text-xs text-muted-foreground">
                                        <div class="flex items-center space-x-4">
                                            {#if result.scraped_at || result.created_at}
                                                <div class="flex items-center">
                                                    <Calendar class="mr-1 h-3 w-3" />
                                                    {formatDate(result.scraped_at || result.created_at)}
                                                </div>
                                            {/if}
                                            {#if result.project_name}
                                                <Badge variant="outline" class="text-xs">
                                                    {result.project_name}
                                                </Badge>
                                            {/if}
                                            {#if result.content_type}
                                                <Badge variant="secondary" class="text-xs">
                                                    {result.content_type}
                                                </Badge>
                                            {/if}
                                        </div>
                                        {#if result.scraped_at || result.created_at}
                                            <span class="text-xs">
                                                {getRelativeTime(result.scraped_at || result.created_at)}
                                            </span>
                                        {/if}
                                    </div>

                                    <!-- Entities (if available) -->
                                    {#if result.entities && result.entities.length > 0}
                                        <div class="flex flex-wrap gap-1">
                                            {#each result.entities.slice(0, 5) as entity}
                                                <Badge variant="outline" class="text-xs">
                                                    {entity.name || entity.text}
                                                </Badge>
                                            {/each}
                                            {#if result.entities.length > 5}
                                                <span class="text-xs text-muted-foreground">
                                                    +{result.entities.length - 5} more
                                                </span>
                                            {/if}
                                        </div>
                                    {/if}
                                </div>
                            </CardContent>
                        </Card>
                    {/each}
                </div>

                <!-- Pagination -->
                {#if Math.ceil(totalResults / pageSize) > 1}
                    <div class="flex items-center justify-center space-x-2 pt-6">
                        <Button
                            variant="outline"
                            disabled={currentPage === 1}
                            on:click={() => { currentPage--; performSearch(); }}
                        >
                            Previous
                        </Button>
                        
                        <span class="text-sm text-muted-foreground">
                            Page {currentPage} of {Math.ceil(totalResults / pageSize)}
                        </span>
                        
                        <Button
                            variant="outline"
                            disabled={currentPage >= Math.ceil(totalResults / pageSize)}
                            on:click={() => { currentPage++; performSearch(); }}
                        >
                            Next
                        </Button>
                    </div>
                {/if}
            </div>
        {:else if query.trim() && !loading}
            <Card>
                <CardContent class="pt-6">
                    <div class="flex flex-col items-center justify-center space-y-3 py-12">
                        <Search class="h-12 w-12 text-muted-foreground" />
                        <div class="text-center">
                            <h3 class="text-lg font-semibold">No results found</h3>
                            <p class="text-muted-foreground mb-4">
                                Try adjusting your search terms or filters.
                            </p>
                            <Button variant="outline" onclick={clearFilters}>
                                Clear Filters
                            </Button>
                        </div>
                    </div>
                </CardContent>
            </Card>
        {:else if !query.trim()}
            <Card>
                <CardContent class="pt-6">
                    <div class="flex flex-col items-center justify-center space-y-3 py-12">
                        <Search class="h-12 w-12 text-muted-foreground" />
                        <div class="text-center">
                            <h3 class="text-lg font-semibold">Start searching</h3>
                            <p class="text-muted-foreground">
                                Enter a search query to find content in your projects.
                            </p>
                        </div>
                    </div>
                </CardContent>
            </Card>
        {/if}
    </div>
</DashboardLayout>

<style>
    .line-clamp-3 {
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
    
    input, select, textarea {
        border: 1px solid #d1d5db;
        border-radius: 0.375rem;
        font-size: 0.875rem;
        line-height: 1.25rem;
    }
    
    input:focus, select:focus, textarea:focus {
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
    }
</style>