<script lang="ts">
    import { onMount } from 'svelte';
    import { goto, replaceState } from '$app/navigation';
    import { page } from '$app/stores';
    import { isAuthenticated, auth } from '$lib/stores/auth';
    import { browser } from '$app/environment';
    import { getApiUrl } from '$lib/utils';
    import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
    import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
    import { Button } from '$lib/components/ui/button';
    import { Input } from '$lib/components/ui/input';
    import { Search } from 'lucide-svelte';
    import SearchFilters from '$lib/components/search/SearchFilters.svelte';
    import UnifiedSearchResults from '$lib/components/search/UnifiedSearchResults.svelte';
    import { filters, filtersToUrlParams, type FilterState } from '$lib/stores/filters';
    import { get as getStore } from 'svelte/store';
    import { PageActionsService } from '$lib/services/pageActions';
    
    let searchQuery = '';
    let searchResults: any[] = [];
    let loading = false;
    let error = '';
    let currentFilters: FilterState;
    let debounceTimeout: NodeJS.Timeout;
    
    // Page management state
    let viewMode: 'list' | 'grid' = 'list';
    let showPageManagement = false;
    
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
        
        loading = true;
        error = '';
        searchResults = [];
        
        try {
            const fs = currentFilters ?? getStore(filters);
            const searchUrl = buildSearchUrl(searchQuery, fs);
            const response = await fetch(searchUrl, {
                credentials: 'include'
            });
            
            if (response.ok) {
                const data = await response.json();
                searchResults = data.pages || [];
                console.log('Search results received:', searchResults.length, 'pages');
                
                // Transform results to ensure consistent format
                const q = searchQuery;
                const escapeHtml = (s: string) => s
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;');
                const highlight = (text: string, query: string) => {
                    if (!text || !query) return escapeHtml(text || '');
                    const terms = query.split(/\s+/).filter(Boolean).map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
                    if (terms.length === 0) return escapeHtml(text);
                    const regex = new RegExp(`(${terms.join('|')})`, 'gi');
                    return escapeHtml(text).replace(regex, '<mark>$1</mark>');
                };

                searchResults = searchResults.map(result => {
                    const content = result.content_preview || result.meta_description || '';
                    return {
                        id: result.id,
                        title: result.title || 'Untitled',
                        url: result.original_url || result.wayback_url,
                        original_url: result.original_url,
                        wayback_url: result.wayback_url,
                        is_starred: !!result.is_starred,
                        review_status: result.review_status,
                        page_category: result.page_category,
                        priority_level: result.priority_level,
                        tags: result.tags,
                        content,
                        highlighted_snippet_html: highlight(content, q),
                        capture_date: result.capture_date,
                        scraped_at: result.scraped_at,
                        author: result.author,
                        language: result.language,
                        meta_description: result.meta_description,
                        project_name: result.project?.name || 'Unknown Project'
                    };
                });
                
                // Update URL
                if (typeof window !== 'undefined') {
                    const url = new URL(window.location.href);
                    url.searchParams.set('q', searchQuery);
                    replaceState(url, $page.state);
                }
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
        if (!browser) return;
        const url = new URL(window.location.href);
        if (searchQuery.trim()) {
            url.searchParams.set('q', searchQuery);
        } else {
            url.searchParams.delete('q');
        }
        window.history.replaceState({}, '', url);
    }
    
    // Update URL when search query changes
    $: if (browser && searchQuery !== undefined) {
        updateSearchQuery();
    }
    
    // Page management actions using the new service
    async function handlePageAction(event: CustomEvent) {
        console.log('🗺️ Search page handlePageAction called:', event.detail);
        const { type, pageId, isStarred } = event.detail;
        
        if (type === 'view') {
            // Handle view action locally
            showPageManagement = true;
            return;
        }
        
        try {
            // Optimistic update for star to avoid double refresh
            if (type === 'star') {
                searchResults = searchResults.map((r) =>
                    Number(r.id) === Number(pageId) ? { ...r, is_starred: !!isStarred } : r
                );
            }
            await PageActionsService.handlePageAction(event.detail);
            // Only re-fetch for non-optimistic actions
            if (type !== 'star') {
                await performSearch();
            }
        } catch (error) {
            console.error('Page action error:', error);
            // Restore from server if optimistic update fails
            await performSearch();
        }
    }
    
    async function handleUpdateTags(event: CustomEvent) {
        try {
            const { pageId, tags } = event.detail;
            // Optimistic update: update tags locally to avoid flash
            searchResults = searchResults.map((r) =>
                Number(r.id) === Number(pageId) ? { ...r, tags: [...tags] } : r
            );

            // Respect current filters: if tag filters are active, remove items that no longer match
            if (currentFilters?.tags?.length) {
                const required = new Set(currentFilters.tags);
                searchResults = searchResults.filter((r) => {
                    const pageTags: string[] = Array.isArray(r.tags) ? r.tags : [];
                    // require every filter tag to be present on the page
                    for (const t of required) {
                        if (!pageTags.includes(t)) return false;
                    }
                    return true;
                });
            }
            await PageActionsService.handleUpdateTags(event.detail);
        } catch (error) {
            console.error('Tag update error:', error);
            // On failure, softly re-fetch this one result set to restore state
            await performSearch();
        }
    }
</script>

<svelte:head>
    <title>Search - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
    <div class="flex gap-6">
        <!-- Main Content -->
        <div class="flex-1 space-y-6 order-1 md:order-none">
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
                        <div class="md:hidden">
                            <SearchFilters mode="search" onFilterChange={handleFilterChange} />
                        </div>
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

        <!-- Unified Search Results -->
        <UnifiedSearchResults
            results={searchResults}
            {loading}
            {error}
            searchQuery={searchQuery}
            bind:viewMode
            bind:showPageManagement
            refreshCallback={performSearch}
            loadPageContentCallback={PageActionsService.loadPageContent}
            loadTagSuggestionsCallback={PageActionsService.loadTagSuggestions}
            on:pageAction={handlePageAction}
            on:updateTags={handleUpdateTags}
        />

        </div>
        <!-- Filters Sidebar (desktop) -->
        <div class="hidden md:block w-80 shrink-0">
            <SearchFilters mode="search" onFilterChange={handleFilterChange} />
        </div>
    </div>
</DashboardLayout>

