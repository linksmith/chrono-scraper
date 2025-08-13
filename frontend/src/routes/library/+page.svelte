<script lang="ts">
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { isAuthenticated, auth } from '$lib/stores/auth';
    import { getApiUrl, formatDate, getRelativeTime, getFileSize } from '$lib/utils';
    import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
    import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
    import { Button } from '$lib/components/ui/button';
    import { Badge } from '$lib/components/ui/badge';
    import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
    import { Input } from '$lib/components/ui/input';
    import { 
        Star, 
        Bookmark, 
        Clock, 
        Search, 
        ExternalLink, 
        Folder, 
        Plus,
        Filter,
        Calendar,
        Download,
        Eye,
        Trash2,
        Heart
    } from 'lucide-svelte';
    
    let loading = false;
    let error = '';
    let searchQuery = '';
    let activeTab = 'starred';
    
    let starredItems: any[] = [];
    let savedSearches: any[] = [];
    let collections: any[] = [];
    let searchHistory: any[] = [];
    
    let stats = {
        starred_count: 0,
        saved_searches: 0,
        collections: 0,
        total_items: 0
    };
    
    onMount(async () => {
        // Initialize auth and check if user is authenticated
        await auth.init();
        
        // Redirect to login if not authenticated
        if (!$isAuthenticated) {
            goto('/auth/login?redirect=/library');
            return;
        }
        
        // Load library data
        await loadLibraryData();
    });
    
    const loadLibraryData = async () => {
        loading = true;
        try {
            await Promise.all([
                loadStarredItems(),
                loadSavedSearches(),
                loadCollections(),
                loadSearchHistory(),
                loadStats()
            ]);
        } catch (e) {
            error = 'Failed to load library data.';
        } finally {
            loading = false;
        }
    };
    
    const loadStarredItems = async () => {
        try {
            const params = searchQuery ? `?search=${encodeURIComponent(searchQuery)}` : '';
            const res = await fetch(getApiUrl(`/api/v1/library/starred${params}`), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                starredItems = await res.json();
            }
        } catch (e) {
            console.error('Failed to load starred items:', e);
        }
    };
    
    const loadSavedSearches = async () => {
        try {
            const params = searchQuery ? `?search=${encodeURIComponent(searchQuery)}` : '';
            const res = await fetch(getApiUrl(`/api/v1/library/searches${params}`), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                savedSearches = await res.json();
            }
        } catch (e) {
            console.error('Failed to load saved searches:', e);
        }
    };
    
    const loadCollections = async () => {
        try {
            const params = searchQuery ? `?search=${encodeURIComponent(searchQuery)}` : '';
            const res = await fetch(getApiUrl(`/api/v1/library/collections${params}`), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                collections = await res.json();
            }
        } catch (e) {
            console.error('Failed to load collections:', e);
        }
    };
    
    const loadSearchHistory = async () => {
        try {
            const params = searchQuery ? `?search=${encodeURIComponent(searchQuery)}` : '';
            const res = await fetch(getApiUrl(`/api/v1/library/history${params}`), {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                searchHistory = await res.json();
            }
        } catch (e) {
            console.error('Failed to load search history:', e);
        }
    };
    
    const loadStats = async () => {
        try {
            const res = await fetch(getApiUrl('/api/v1/library/stats'), {
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
            case 'starred':
                loadStarredItems();
                break;
            case 'searches':
                loadSavedSearches();
                break;
            case 'collections':
                loadCollections();
                break;
            case 'history':
                loadSearchHistory();
                break;
        }
    };
    
    const unstarItem = async (itemId: string) => {
        try {
            const res = await fetch(getApiUrl(`/api/v1/library/starred/${itemId}`), {
                method: 'DELETE',
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                await loadStarredItems();
                await loadStats();
            }
        } catch (e) {
            console.error('Failed to unstar item:', e);
        }
    };
    
    const deleteSavedSearch = async (searchId: string) => {
        try {
            const res = await fetch(getApiUrl(`/api/v1/library/searches/${searchId}`), {
                method: 'DELETE',
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
            if (res.ok) {
                await loadSavedSearches();
                await loadStats();
            }
        } catch (e) {
            console.error('Failed to delete saved search:', e);
        }
    };
    
    const createNewCollection = () => {
        goto('/library/collections/create');
    };
    
    const viewCollection = (collectionId: string) => {
        goto(`/library/collections/${collectionId}`);
    };
    
    const runSavedSearch = (searchQuery: string) => {
        goto(`/search?q=${encodeURIComponent(searchQuery)}`);
    };
    
    const getItemTypeColor = (type: string) => {
        switch (type) {
            case 'page': return 'default';
            case 'project': return 'secondary';
            case 'investigation': return 'outline';
            default: return 'secondary';
        }
    };
</script>

<svelte:head>
    <title>Personal Library - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
    <div class="space-y-6">
        <!-- Header -->
        <div class="flex items-center justify-between">
            <div>
                <h2 class="text-3xl font-bold tracking-tight">Personal Library</h2>
                <p class="text-muted-foreground">
                    Your saved content, searches, and collections
                </p>
            </div>
            <Button on:click={createNewCollection}>
                <Plus class="mr-2 h-4 w-4" />
                New Collection
            </Button>
        </div>
        
        <!-- Statistics Cards -->
        <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Starred Items</CardTitle>
                    <Star class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.starred_count}</div>
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Saved Searches</CardTitle>
                    <Bookmark class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.saved_searches}</div>
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Collections</CardTitle>
                    <Folder class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.collections}</div>
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">Total Items</CardTitle>
                    <Heart class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{stats.total_items}</div>
                </CardContent>
            </Card>
        </div>
        
        <!-- Search Bar -->
        <div class="relative">
            <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
            <Input
                bind:value={searchQuery}
                on:input={handleSearch}
                placeholder="Search your library..."
                class="pl-10"
            />
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
        
        <!-- Tabs -->
        <Tabs bind:value={activeTab} class="w-full">
            <TabsList class="grid w-full grid-cols-4">
                <TabsTrigger value="starred">Starred</TabsTrigger>
                <TabsTrigger value="searches">Saved Searches</TabsTrigger>
                <TabsTrigger value="collections">Collections</TabsTrigger>
                <TabsTrigger value="history">Recent</TabsTrigger>
            </TabsList>
            
            <!-- Starred Items -->
            <TabsContent value="starred" class="space-y-4">
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
                {:else if starredItems.length === 0}
                    <Card>
                        <CardContent class="pt-6">
                            <div class="flex flex-col items-center justify-center space-y-3 py-12">
                                <Star class="h-12 w-12 text-muted-foreground" />
                                <div class="text-center">
                                    <h3 class="text-lg font-semibold">No starred items</h3>
                                    <p class="text-muted-foreground">
                                        Star pages and content to save them here.
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                {:else}
                    <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {#each starredItems as item}
                            <Card class="hover:shadow-md transition-shadow">
                                <CardHeader class="pb-2">
                                    <div class="flex items-start justify-between">
                                        <CardTitle class="text-lg line-clamp-2">{item.title || item.url || 'Untitled'}</CardTitle>
                                        <Button variant="ghost" size="sm" on:click={() => unstarItem(item.id)}>
                                            <Star class="h-4 w-4 text-yellow-500 fill-current" />
                                        </Button>
                                    </div>
                                    {#if item.description}
                                        <CardDescription class="line-clamp-2">
                                            {item.description}
                                        </CardDescription>
                                    {/if}
                                </CardHeader>
                                <CardContent class="space-y-3">
                                    <div class="flex items-center justify-between">
                                        <Badge variant={getItemTypeColor(item.item_type)}>
                                            {item.item_type}
                                        </Badge>
                                        <div class="flex items-center text-sm text-muted-foreground">
                                            <Calendar class="mr-1 h-3 w-3" />
                                            {getRelativeTime(item.starred_at)}
                                        </div>
                                    </div>
                                    
                                    {#if item.url}
                                        <div class="flex items-center gap-2">
                                            <Button variant="outline" size="sm" class="flex-1">
                                                <Eye class="mr-1 h-3 w-3" />
                                                View
                                            </Button>
                                            <Button variant="outline" size="sm">
                                                <ExternalLink class="h-3 w-3" />
                                            </Button>
                                        </div>
                                    {/if}
                                    
                                    {#if item.tags && item.tags.length > 0}
                                        <div class="flex flex-wrap gap-1">
                                            {#each item.tags.slice(0, 3) as tag}
                                                <Badge variant="outline" class="text-xs">
                                                    {tag}
                                                </Badge>
                                            {/each}
                                            {#if item.tags.length > 3}
                                                <span class="text-xs text-muted-foreground">
                                                    +{item.tags.length - 3} more
                                                </span>
                                            {/if}
                                        </div>
                                    {/if}
                                </CardContent>
                            </Card>
                        {/each}
                    </div>
                {/if}
            </TabsContent>
            
            <!-- Saved Searches -->
            <TabsContent value="searches" class="space-y-4">
                {#if loading}
                    <div class="space-y-4">
                        {#each Array(5) as _}
                            <Card class="animate-pulse">
                                <CardContent class="pt-6">
                                    <div class="space-y-2">
                                        <div class="h-4 bg-gray-200 rounded w-3/4"></div>
                                        <div class="h-3 bg-gray-200 rounded w-1/2"></div>
                                    </div>
                                </CardContent>
                            </Card>
                        {/each}
                    </div>
                {:else if savedSearches.length === 0}
                    <Card>
                        <CardContent class="pt-6">
                            <div class="flex flex-col items-center justify-center space-y-3 py-12">
                                <Bookmark class="h-12 w-12 text-muted-foreground" />
                                <div class="text-center">
                                    <h3 class="text-lg font-semibold">No saved searches</h3>
                                    <p class="text-muted-foreground">
                                        Save useful search queries to quickly access them later.
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                {:else}
                    <div class="space-y-4">
                        {#each savedSearches as search}
                            <Card class="hover:shadow-md transition-shadow">
                                <CardContent class="pt-6">
                                    <div class="flex items-start justify-between">
                                        <div class="flex-1">
                                            <h3 class="font-semibold">{search.name || search.query}</h3>
                                            <p class="text-sm text-muted-foreground mt-1">
                                                Query: {search.query}
                                            </p>
                                            <div class="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                                                <span>Saved {getRelativeTime(search.created_at)}</span>
                                                {#if search.last_run}
                                                    <span>Last run {getRelativeTime(search.last_run)}</span>
                                                {/if}
                                            </div>
                                        </div>
                                        <div class="flex items-center gap-2">
                                            <Button variant="outline" size="sm" on:click={() => runSavedSearch(search.query)}>
                                                <Search class="mr-1 h-3 w-3" />
                                                Run
                                            </Button>
                                            <Button variant="ghost" size="sm" on:click={() => deleteSavedSearch(search.id)}>
                                                <Trash2 class="h-3 w-3" />
                                            </Button>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        {/each}
                    </div>
                {/if}
            </TabsContent>
            
            <!-- Collections -->
            <TabsContent value="collections" class="space-y-4">
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
                {:else if collections.length === 0}
                    <Card>
                        <CardContent class="pt-6">
                            <div class="flex flex-col items-center justify-center space-y-3 py-12">
                                <Folder class="h-12 w-12 text-muted-foreground" />
                                <div class="text-center">
                                    <h3 class="text-lg font-semibold">No collections yet</h3>
                                    <p class="text-muted-foreground mb-4">
                                        Create collections to organize your research materials.
                                    </p>
                                    <Button on:click={createNewCollection}>
                                        <Plus class="mr-2 h-4 w-4" />
                                        Create Collection
                                    </Button>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                {:else}
                    <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {#each collections as collection}
                            <Card class="hover:shadow-md transition-shadow cursor-pointer" on:click={() => viewCollection(collection.id)}>
                                <CardHeader class="pb-2">
                                    <div class="flex items-start justify-between">
                                        <CardTitle class="text-lg line-clamp-2">{collection.name}</CardTitle>
                                        <Folder class="h-5 w-5 text-muted-foreground" />
                                    </div>
                                    {#if collection.description}
                                        <CardDescription class="line-clamp-2">
                                            {collection.description}
                                        </CardDescription>
                                    {/if}
                                </CardHeader>
                                <CardContent class="space-y-3">
                                    <div class="flex items-center justify-between text-sm">
                                        <span class="text-muted-foreground">
                                            {collection.item_count || 0} items
                                        </span>
                                        <span class="text-muted-foreground">
                                            {getRelativeTime(collection.updated_at)}
                                        </span>
                                    </div>
                                    
                                    {#if collection.tags && collection.tags.length > 0}
                                        <div class="flex flex-wrap gap-1">
                                            {#each collection.tags.slice(0, 3) as tag}
                                                <Badge variant="outline" class="text-xs">
                                                    {tag}
                                                </Badge>
                                            {/each}
                                            {#if collection.tags.length > 3}
                                                <span class="text-xs text-muted-foreground">
                                                    +{collection.tags.length - 3} more
                                                </span>
                                            {/if}
                                        </div>
                                    {/if}
                                </CardContent>
                            </Card>
                        {/each}
                    </div>
                {/if}
            </TabsContent>
            
            <!-- Search History -->
            <TabsContent value="history" class="space-y-4">
                {#if loading}
                    <div class="space-y-4">
                        {#each Array(10) as _}
                            <Card class="animate-pulse">
                                <CardContent class="pt-6">
                                    <div class="space-y-2">
                                        <div class="h-3 bg-gray-200 rounded w-3/4"></div>
                                        <div class="h-3 bg-gray-200 rounded w-1/4"></div>
                                    </div>
                                </CardContent>
                            </Card>
                        {/each}
                    </div>
                {:else if searchHistory.length === 0}
                    <Card>
                        <CardContent class="pt-6">
                            <div class="flex flex-col items-center justify-center space-y-3 py-12">
                                <Clock class="h-12 w-12 text-muted-foreground" />
                                <div class="text-center">
                                    <h3 class="text-lg font-semibold">No search history</h3>
                                    <p class="text-muted-foreground">
                                        Your recent searches will appear here.
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                {:else}
                    <div class="space-y-2">
                        {#each searchHistory as item}
                            <Card class="hover:shadow-sm transition-shadow">
                                <CardContent class="pt-4">
                                    <div class="flex items-center justify-between">
                                        <div class="flex-1">
                                            <p class="font-medium">{item.query}</p>
                                            <p class="text-sm text-muted-foreground">
                                                {item.results_count} results • {getRelativeTime(item.searched_at)}
                                            </p>
                                        </div>
                                        <Button variant="ghost" size="sm" on:click={() => runSavedSearch(item.query)}>
                                            <Search class="h-3 w-3" />
                                        </Button>
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