<script lang="ts">
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { page } from '$app/stores';
    import { isAuthenticated, auth } from '$lib/stores/auth';
    import { getApiUrl } from '$lib/utils';
    import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
    import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
    import { Button } from '$lib/components/ui/button';
    import { Input } from '$lib/components/ui/input';
    import { Search } from 'lucide-svelte';
    import SearchFilters from '$lib/components/search/SearchFilters.svelte';
    import { filters, filtersToUrlParams, type FilterState } from '$lib/stores/filters';
    
    let searchQuery = '';
    let searchResults: any[] = [];
    let loading = false;
    let error = '';
    let currentFilters: FilterState;
    let debounceTimeout: NodeJS.Timeout;
    
    // Subscribe to filter changes
    $: currentFilters = $filters;
    
    onMount(async () => {
        // Initialize auth and check if user is authenticated
        await auth.init();
        
        // Redirect to login if not authenticated
        if (!$isAuthenticated) {
            goto('/auth/login?redirect=/search');
            return;
        }
        
        // Check for URL parameters and set initial query
        const urlParams = new URLSearchParams($page.url.searchParams.toString());
        const urlQuery = urlParams.get('q');
        if (urlQuery) {
            searchQuery = urlQuery;
            performSearch();
        }
    });

    function buildSearchUrl(query: string, filterState: FilterState): string {
        const params = filtersToUrlParams(filterState);
        if (query.trim()) {
            params.set('q', query);
        }
        return `/api/v1/search/pages?${params.toString()}`;
    }

    async function performSearch() {
        if (!searchQuery.trim() && !currentFilters) return;
        
        loading = true;
        error = '';
        searchResults = [];
        
        try {
            const searchUrl = buildSearchUrl(searchQuery, currentFilters);
            const response = await fetch(searchUrl, {
                credentials: 'include'
            });
            
            if (response.ok) {
                const data = await response.json();
                searchResults = data.pages || [];
                console.log('Search results received:', searchResults.length, 'pages');
                
                // Transform results to ensure consistent format
                searchResults = searchResults.map(result => ({
                    id: result.id,
                    title: result.title || 'Untitled',
                    url: result.original_url || result.wayback_url,
                    content: result.content_preview || result.meta_description || '',
                    scraped_at: result.scraped_at,
                    project_name: result.project?.name || 'Unknown Project'
                }));
                
                // Update URL
                const url = new URL(window.location.href);
                url.searchParams.set('q', searchQuery);
                window.history.replaceState({}, '', url);
            } else {
                console.error('Search failed:', response.status, response.statusText);
                error = `Search failed: ${response.status} ${response.statusText}`;
            }
        } catch (e) {
            error = 'Search error occurred';
        } finally {
            loading = false;
        }
    }

    function handleKeyPress(event: KeyboardEvent) {
        if (event.key === 'Enter') {
            performSearch();
        }
    }
    
    function handleFilterChange(newFilters: FilterState) {
        // Debounce search when filters change
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(() => {
            performSearch();
        }, 300);
    }
    
    function updateSearchQuery() {
        // Update URL with search query
        const url = new URL(window.location.href);
        if (searchQuery.trim()) {
            url.searchParams.set('q', searchQuery);
        } else {
            url.searchParams.delete('q');
        }
        window.history.replaceState({}, '', url);
    }
    
    // Update URL when search query changes
    $: if (searchQuery !== undefined) {
        updateSearchQuery();
    }
</script>

<svelte:head>
    <title>Search - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
    <div class="flex gap-6">
        <!-- Main Content -->
        <div class="flex-1 space-y-6">
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
                        <Input
                            bind:value={searchQuery}
                            onkeypress={handleKeyPress}
                            placeholder="Search for content, entities, or topics..."
                            class="pl-10"
                            disabled={loading}
                        />
                    </div>
                    <div class="flex items-center space-x-2">
                        <!-- Mobile filters button will be shown by SearchFilters component -->
                        <SearchFilters mode="search" onFilterChange={handleFilterChange} />
                        <Button onclick={performSearch} disabled={loading}>
                            {#if loading}
                                <div class="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full"></div>
                            {:else}
                                Search
                            {/if}
                        </Button>
                    </div>
                </div>
            </div>

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
        {#if searchResults.length > 0}
            <div class="space-y-4">
                <p class="text-sm text-muted-foreground">
                    Found {searchResults.length} result{searchResults.length !== 1 ? 's' : ''}
                    for "<strong>{searchQuery}</strong>"
                </p>

                <div class="space-y-3">
                    {#each searchResults as result}
                        <Card class="hover:shadow-md transition-shadow">
                            <CardContent class="pt-6">
                                <div class="space-y-3">
                                    <div class="flex items-start justify-between">
                                        <div class="flex-1 space-y-1">
                                            <h3 class="text-lg font-semibold text-blue-600 hover:text-blue-800">
                                                <a href={result.url} target="_blank" rel="noopener noreferrer">
                                                    {result.title || 'Untitled'}
                                                </a>
                                            </h3>
                                            <p class="text-sm text-green-600">{result.url}</p>
                                        </div>
                                    </div>

                                    {#if result.content}
                                        <p class="text-sm text-gray-700 line-clamp-3">
                                            {result.content}
                                        </p>
                                    {/if}

                                    <div class="flex items-center text-xs text-muted-foreground">
                                        {#if result.scraped_at}
                                            <span>{new Date(result.scraped_at).toLocaleDateString()}</span>
                                        {/if}
                                        {#if result.project_name}
                                            <span class="ml-2 px-2 py-1 bg-gray-100 rounded text-xs">
                                                {result.project_name}
                                            </span>
                                        {/if}
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    {/each}
                </div>
            </div>
        {:else if searchQuery.trim() && !loading}
            <Card>
                <CardContent class="pt-6">
                    <div class="flex flex-col items-center justify-center space-y-3 py-12">
                        <Search class="h-12 w-12 text-muted-foreground" />
                        <div class="text-center">
                            <h3 class="text-lg font-semibold">No results found</h3>
                            <p class="text-muted-foreground">
                                Try different search terms.
                            </p>
                        </div>
                    </div>
                </CardContent>
            </Card>
        {:else if !searchQuery.trim()}
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
    </div>
</DashboardLayout>

