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
    import { Search, Grid, List, Filter, ChevronDown } from 'lucide-svelte';
    import SearchFilters from '$lib/components/search/SearchFilters.svelte';
    import { PageReviewCard, MarkdownViewer } from '$lib/components/page-management';
    import { filters, filtersToUrlParams, type FilterState } from '$lib/stores/filters';
    import { pageManagementActions, pageManagementStore } from '$lib/stores/page-management';
    
    let searchQuery = '';
    let searchResults: any[] = [];
    let loading = false;
    let error = '';
    let currentFilters: FilterState;
    let debounceTimeout: NodeJS.Timeout;
    
    // Page management state
    let viewMode: 'list' | 'grid' = 'list';
    let showPageManagement = false;
    let selectedPageId: number | null = null;
    let pageContent: any = null;
    let contentLoading = false;
    
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
    
    // Page management actions
    async function handlePageAction(event: CustomEvent) {
        const { type, pageId } = event.detail;
        
        try {
            switch (type) {
                case 'star':
                    await pageManagementActions.toggleStar(pageId, event.detail);
                    break;
                case 'review':
                    await pageManagementActions.reviewPage(pageId, {
                        review_status: event.detail.reviewStatus
                    });
                    break;
                case 'view':
                    selectedPageId = pageId;
                    showPageManagement = true;
                    await loadPageContent(pageId);
                    break;
                case 'more':
                    // Open additional options menu
                    break;
            }
            
            // Refresh search results to show updated page status
            performSearch();
        } catch (error) {
            console.error('Page action error:', error);
        }
    }
    
    async function handleUpdateTags(event: CustomEvent) {
        const { pageId, tags } = event.detail;
        try {
            await pageManagementActions.updatePageTags(pageId, tags);
            performSearch();
        } catch (error) {
            console.error('Tag update error:', error);
        }
    }
    
    async function loadPageContent(pageId: number, format: 'markdown' | 'html' | 'text' = 'markdown') {
        contentLoading = true;
        try {
            pageContent = await pageManagementActions.loadPageContent(pageId, format);
        } catch (error) {
            console.error('Content loading error:', error);
        } finally {
            contentLoading = false;
        }
    }
    
    async function loadTagSuggestions() {
        await pageManagementActions.loadTagSuggestions();
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
                        <!-- View Mode Toggle -->
                        <div class="flex bg-muted rounded-md p-1">
                            <Button
                                variant={viewMode === 'list' ? 'default' : 'ghost'}
                                size="sm"
                                class="h-8 px-2"
                                onclick={() => viewMode = 'list'}
                            >
                                <List class="h-4 w-4" />
                            </Button>
                            <Button
                                variant={viewMode === 'grid' ? 'default' : 'ghost'}
                                size="sm"
                                class="h-8 px-2"
                                onclick={() => viewMode = 'grid'}
                            >
                                <Grid class="h-4 w-4" />
                            </Button>
                        </div>

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
                <div class="flex items-center justify-between">
                    <p class="text-sm text-muted-foreground">
                        Found {searchResults.length} result{searchResults.length !== 1 ? 's' : ''}
                        for "<strong>{searchQuery}</strong>"
                    </p>
                    
                    <Button 
                        variant="outline" 
                        size="sm"
                        onclick={() => showPageManagement = !showPageManagement}
                    >
                        <Filter class="h-4 w-4 mr-2" />
                        {showPageManagement ? 'Hide' : 'Show'} Page Management
                    </Button>
                </div>

                <!-- Results Grid/List -->
                <div class={viewMode === 'grid' ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4' : 'space-y-4'}>
                    {#each searchResults as result}
                        <PageReviewCard
                            page={{
                                id: result.id,
                                title: result.title,
                                url: result.url,
                                review_status: result.review_status || 'unreviewed',
                                page_category: result.page_category,
                                priority_level: result.priority_level || 'medium',
                                tags: result.tags || [],
                                word_count: result.word_count,
                                content_snippet: result.content,
                                scraped_at: result.scraped_at,
                                reviewed_at: result.reviewed_at,
                                author: result.author,
                                language: result.language,
                                meta_description: result.meta_description
                            }}
                            isStarred={result.is_starred || false}
                            tagSuggestions={$pageManagementStore.tagSuggestions}
                            compact={viewMode === 'grid'}
                            on:action={handlePageAction}
                            on:updateTags={handleUpdateTags}
                            on:loadTagSuggestions={loadTagSuggestions}
                            on:loadContent={(e) => loadPageContent(e.detail.pageId)}
                        />
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
    
    <!-- Page Content Viewer Modal/Sidebar -->
    {#if showPageManagement && selectedPageId}
        <div class="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-end">
            <div class="w-full max-w-4xl bg-background h-full overflow-y-auto">
                <div class="p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-xl font-semibold">Page Content</h2>
                        <Button
                            variant="ghost"
                            size="sm"
                            onclick={() => { showPageManagement = false; selectedPageId = null; pageContent = null; }}
                        >
                            ✕
                        </Button>
                    </div>
                    
                    <MarkdownViewer
                        pageId={selectedPageId}
                        {pageContent}
                        loading={contentLoading}
                        on:loadContent={(e) => loadPageContent(e.detail.pageId, e.detail.format)}
                        on:copy={() => console.log('Content copied')}
                        on:download={() => console.log('Content downloaded')}
                        on:openUrl={(e) => window.open(e.detail.url, '_blank')}
                    />
                </div>
            </div>
        </div>
    {/if}
</DashboardLayout>

