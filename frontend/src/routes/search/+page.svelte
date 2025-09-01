
<script lang="ts">
    import { onMount } from 'svelte';
    import { goto, replaceState } from '$app/navigation';
    import { page } from '$app/stores';
    import { isAuthenticated, auth } from '$lib/stores/auth';
    import { browser } from '$app/environment';
    import { getApiUrl, apiFetch } from '$lib/utils';
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
    import { pageManagementActions } from '$lib/stores/page-management';
    import { SharedPagesApiService } from '$lib/services/sharedPagesApi';
    
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
        
        // Enable shared pages API for search context
        pageManagementActions.enableSharedPagesApi();
        
        // Check for URL parameters and set initial query
        const urlParams = new URLSearchParams($page.url.searchParams.toString());
        const urlQuery = urlParams.get('q');
        if (urlQuery) {
            searchQuery = urlQuery;
            performSearch();
        }
    });


    async function performSearch() {
        loading = true;
        error = '';
        // Don't clear results immediately to avoid flash - keep them during loading
        
        try {
            const fs = currentFilters ?? getStore(filters);
            
            // Build search request for SharedPagesApiService
            const searchRequest = {
                query: searchQuery.trim() || undefined,
                project_ids: fs.project ? [parseInt(fs.project)] : undefined,
                review_statuses: fs.reviewStatus?.length ? fs.reviewStatus : undefined,
                tags: fs.tags?.length ? fs.tags : undefined,
                starred_only: fs.starredOnly || undefined,
                exclude_irrelevant: fs.excludeIrrelevant || undefined,
                language: fs.language || undefined,
                content_type: fs.contentType?.length ? fs.contentType : undefined,
                date_range: fs.dateRange && (fs.dateRange.from || fs.dateRange.to) ? {
                    start: fs.dateRange.from || undefined,
                    end: fs.dateRange.to || undefined,
                    field: 'scraped_at'
                } : undefined,
                sort_by: fs.sortBy || 'scraped_at',
                sort_order: fs.sortOrder || 'desc',
                skip: 0,
                limit: 50
            };

            // Use SharedPagesApiService for search
            const response = await SharedPagesApiService.searchPages(searchRequest);
            
            // Debug logging to help identify response structure issues
            console.log('Search response received:', {
                hasResponse: !!response,
                hasSuccess: !!response?.success,
                hasData: !!response?.data,
                hasPages: !!response?.data?.pages,
                responseKeys: response ? Object.keys(response) : [],
                dataKeys: response?.data ? Object.keys(response.data) : []
            });
            
            if (response && response.success && response.data && response.data.pages) {
                // Smooth transition - only update results after successful fetch
                const pages = response.data.pages;
                console.log('Search results received:', pages.length, 'pages');
                
                // Transform results to ensure consistent format with highlighting
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

                searchResults = pages.map(result => {
                    const content = result.content_preview || result.meta_description || '';
                    // For shared pages, find the primary project association
                    const primaryAssociation = result.project_associations?.[0];
                    
                    return {
                        id: result.id,
                        title: result.title || 'Untitled',
                        url: result.original_url || result.wayback_url,
                        original_url: result.original_url,
                        wayback_url: result.wayback_url,
                        is_starred: primaryAssociation?.is_starred || false,
                        review_status: primaryAssociation?.review_status || 'unreviewed',
                        page_category: primaryAssociation?.page_category || result.page_category,
                        priority_level: primaryAssociation?.priority_level || result.priority_level,
                        tags: primaryAssociation?.tags || [],
                        content,
                        highlighted_snippet_html: result.highlighted_snippet_html || highlight(content, q),
                        capture_date: result.capture_date,
                        scraped_at: result.scraped_at,
                        author: result.author,
                        language: result.language,
                        meta_description: result.meta_description,
                        project_name: primaryAssociation?.project_name || 'Shared Page',
                        // New shared pages properties
                        project_associations: result.project_associations,
                        total_projects: result.total_projects,
                        all_tags: result.all_tags
                    };
                });
                
                // Update URL
                if (typeof window !== 'undefined') {
                    const url = new URL(window.location.href);
                    url.searchParams.set('q', searchQuery);
                    replaceState(url, $page.state);
                }
            } else {
                console.error('Search failed:', response);
                const errorMessage = response?.error?.message 
                    || response?.error?.detail
                    || response?.error
                    || 'Unknown error - check console for details';
                error = `Search failed: ${errorMessage}`;
            }
        } catch (e) {
            console.error('Search error:', e);
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
    
    let routerReady = false;
    onMount(() => {
        queueMicrotask(() => { routerReady = true; });
    });

    function updateSearchQuery() {
        // Update URL with search query using SvelteKit navigation API
        if (!browser || !routerReady) return;
        const url = new URL(window.location.href);
        if (searchQuery.trim()) {
            url.searchParams.set('q', searchQuery);
        } else {
            url.searchParams.delete('q');
        }
        replaceState(url, $page.state);
    }
    
    // Update URL when search query changes
    $: if (browser && routerReady && searchQuery !== undefined) {
        updateSearchQuery();
    }
    
    // Page management actions using the new service
    async function handlePageAction(event: CustomEvent) {
        console.log('🗺️ Search page handlePageAction called:', event.detail);
        const { type, pageId, isStarred, reviewStatus } = event.detail;
        
        if (type === 'view') {
            // Handle view action locally
            showPageManagement = true;
            return;
        }
        
        try {
            // For shared pages, we need to determine the project context
            const page = searchResults.find(r => Number(r.id) === Number(pageId));
            const primaryProjectId = page?.project_associations?.[0]?.project_id;
            
            if (primaryProjectId) {
                // Temporarily set project context for this action
                pageManagementActions.enableSharedPagesApi(primaryProjectId);
            }
            
            // Optimistic update for star to avoid double refresh
            if (type === 'star') {
                const wasStarredOnlyActive = !!currentFilters?.starredOnly;
                searchResults = searchResults
                    .map((r) =>
                        Number(r.id) === Number(pageId) ? { ...r, is_starred: !!isStarred } : r
                    )
                    .filter((r) => !wasStarredOnlyActive || !!r.is_starred);
            } else if (type === 'review') {
                // Optimistic update for review to avoid flashing
                const activeStatuses: string[] = currentFilters?.reviewStatus ?? [];
                const hasActiveReviewFilter = activeStatuses.length > 0;
                const allowed = new Set(activeStatuses.map((s) => (s || '').toLowerCase()));

                searchResults = searchResults
                    .map((r) =>
                        Number(r.id) === Number(pageId)
                            ? { ...r, review_status: reviewStatus }
                            : r
                    )
                    .filter((r) => {
                        if (!hasActiveReviewFilter) return true;
                        const status = (r.review_status || '').toLowerCase();
                        return allowed.has(status);
                    });
            }
            
            await PageActionsService.handlePageAction(event.detail);
            
            // Reset to general search context
            pageManagementActions.enableSharedPagesApi();
            
            // No immediate refetch to prevent flashing; rely on optimistic update
        } catch (error) {
            console.error('Page action error:', error);
            // Reset to general search context
            pageManagementActions.enableSharedPagesApi();
            // Restore from server if optimistic update fails
            await performSearch();
        }
    }
    
    async function handleUpdateTags(event: CustomEvent) {
        try {
            const { pageId, tags } = event.detail;
            
            // For shared pages, we need to determine the project context
            const page = searchResults.find(r => Number(r.id) === Number(pageId));
            const primaryProjectId = page?.project_associations?.[0]?.project_id;
            
            if (primaryProjectId) {
                // Temporarily set project context for this action
                pageManagementActions.enableSharedPagesApi(primaryProjectId);
            }
            
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
            
            // Reset to general search context
            pageManagementActions.enableSharedPagesApi();
            
            // Refresh search results to ensure tags persist across reloads
            await performSearch();
        } catch (error) {
            console.error('Tag update error:', error);
            // Reset to general search context
            pageManagementActions.enableSharedPagesApi();
            // On failure, softly re-fetch this one result set to restore state
            await performSearch();
        }
    }
</script>

<svelte:head>
    <title>Search - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
    <div class="flex flex-col lg:flex-row gap-4 lg:gap-6">
        <!-- Main Content -->
        <div class="flex-1 space-y-4 lg:space-y-6 order-1 lg:order-none">
            <!-- Search Header -->
            <div class="space-y-4">
                <div>
                    <h2 class="text-2xl sm:text-3xl font-bold tracking-tight">Search</h2>
                    <p class="text-muted-foreground text-sm sm:text-base">
                        Search through your collected web data and archived content.
                    </p>
                </div>
                
                <!-- Search Bar -->
                <div class="flex flex-col sm:flex-row gap-3 sm:gap-2">
                    <div class="flex-1 relative">
                        <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                        <Input
                            bind:value={searchQuery}
                            onkeypress={handleKeyPress}
                            placeholder="Search for content, entities, or topics..."
                            class="pl-10 h-11 sm:h-10"
                            disabled={loading}
                        />
                    </div>
                    <div class="flex items-center space-x-2">
                        <!-- Mobile filters button will be shown by SearchFilters component -->
                        <div class="lg:hidden flex-1 sm:flex-initial">
                            <SearchFilters mode="search" onFilterChange={handleFilterChange} />
                        </div>
                        <Button onclick={performSearch} disabled={loading} class="h-11 sm:h-10 px-6 sm:px-4">
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
        <div class="hidden lg:block w-80 shrink-0">
            <SearchFilters mode="search" onFilterChange={handleFilterChange} />
        </div>
    </div>
</DashboardLayout>

