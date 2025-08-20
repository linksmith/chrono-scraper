<script lang="ts">
    import { onMount } from 'svelte';
    import { browser } from '$app/environment';
    import { replaceState } from '$app/navigation';
    import { page } from '$app/stores';
    import { Button } from "$lib/components/ui/button";
    import { Badge } from "$lib/components/ui/badge";
    import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "$lib/components/ui/sheet";
    import { Separator } from "$lib/components/ui/separator";
    import { ScrollArea } from "$lib/components/ui/scroll-area";
    import { 
        Filter, 
        X, 
        RotateCcw,
        ChevronLeft,
        ChevronRight
    } from "lucide-svelte";
    
    import DateRangeFilter from "./DateRangeFilter.svelte";
    import EntityFilters from "./EntityFilters.svelte";
    import ContentFilters from "./ContentFilters.svelte";
    import PageManagementFilters from "./PageManagementFilters.svelte";
    import ProjectDomainFilters from "./ProjectDomainFilters.svelte";
    
    import { 
        filters, 
        resetFilters, 
        removeFilter, 
        hasActiveFilters, 
        activeFilterCount,
        filtersToUrlParams,
        urlParamsToFilters,
        type FilterState 
    } from "$lib/stores/filters";
    
    export const mode: 'search' | 'project' = 'search';
    export const projectId: string | null = null;
    export let onFilterChange: ((filters: FilterState) => void) | null = null;
    export let collapsed = false;
    
    // Mobile state
    let mobileFiltersOpen = false;
    let isDesktop = true;
    
    // Filter state
    let currentFilters: FilterState;
    
    // Subscribe to filter changes
    $: currentFilters = $filters;
    $: if (onFilterChange && currentFilters) {
        onFilterChange(currentFilters);
    }
    
    // Update URL when filters change
    $: if (browser && currentFilters && routerReady) {
        updateUrl(currentFilters);
    }
    
    let routerReady = false;

    onMount(() => {
        // Check screen size
        const checkScreenSize = () => {
            isDesktop = window.innerWidth >= 768;
        };
        
        checkScreenSize();
        window.addEventListener('resize', checkScreenSize);
        
        // Load filters from URL on mount and mark router ready after a tick
        if (browser) {
            const urlParams = new URLSearchParams(window.location.search);
            const filtersFromUrl = urlParamsToFilters(urlParams);
            filters.set(filtersFromUrl);
            queueMicrotask(() => { routerReady = true; });
        }
        
        return () => {
            window.removeEventListener('resize', checkScreenSize);
        };
    });
    
    function updateUrl(filterState: FilterState) {
        if (!browser) return;
        
        const url = new URL($page.url);
        const params = filtersToUrlParams(filterState);
        
        // Preserve non-filter params
        const preservedParams = ['q', 'page'];
        preservedParams.forEach(param => {
            const value = url.searchParams.get(param);
            if (value) {
                params.set(param, value);
            }
        });
        
        url.search = params.toString();
        replaceState(url, $page.state);
    }
    
    function handleResetFilters() {
        resetFilters();
        mobileFiltersOpen = false;
    }
    
    function handleRemoveFilter(filterType: keyof FilterState, value?: any) {
        removeFilter(filterType, value);
    }
    
    function toggleCollapsed() {
        collapsed = !collapsed;
    }
    
    // Generate active filter chips for display
    $: activeFilterChips = (() => {
        const chips: Array<{ label: string; type: keyof FilterState; value?: any }> = [];
        
        // Date range
        if (currentFilters.dateRange[0] || currentFilters.dateRange[1]) {
            const [start, end] = currentFilters.dateRange;
            let label = 'Date: ';
            if (start && end) {
                label += `${start.toLocaleDateString()} - ${end.toLocaleDateString()}`;
            } else if (start) {
                label += `From ${start.toLocaleDateString()}`;
            } else if (end) {
                label += `Until ${end.toLocaleDateString()}`;
            }
            chips.push({ label, type: 'dateRange' });
        }
        
        // Entities
        Object.entries(currentFilters.entities).forEach(([type, entities]) => {
            entities.forEach(entity => {
                chips.push({
                    label: `${type}: ${entity}`,
                    type: 'entities',
                    value: { type, value: entity }
                });
            });
        });
        
        // Content types
        currentFilters.contentTypes.forEach(contentType => {
            chips.push({
                label: `Type: ${contentType}`,
                type: 'contentTypes',
                value: contentType
            });
        });
        
        // Languages
        currentFilters.languages.forEach(language => {
            chips.push({
                label: `Lang: ${language}`,
                type: 'languages',
                value: language
            });
        });
        
        // Projects - we'll show IDs for now, but could be enhanced to show names
        currentFilters.projects.forEach(projectId => {
            chips.push({
                label: `Project ID: ${projectId}`,
                type: 'projects',
                value: projectId
            });
        });
        
        // Domains
        currentFilters.domains.forEach(domain => {
            chips.push({
                label: `Domain: ${domain}`,
                type: 'domains',
                value: domain
            });
        });
        
        // Word count
        if (currentFilters.wordCount[0] !== null || currentFilters.wordCount[1] !== null) {
            const [min, max] = currentFilters.wordCount;
            let label = 'Words: ';
            if (min !== null && max !== null) {
                label += `${min.toLocaleString()} - ${max.toLocaleString()}`;
            } else if (min !== null) {
                label += `${min.toLocaleString()}+`;
            } else if (max !== null) {
                label += `Up to ${max.toLocaleString()}`;
            }
            chips.push({ label, type: 'wordCount' });
        }
        
        // Metadata filters
        if (currentFilters.hasTitle !== null) {
            chips.push({
                label: `Has title: ${currentFilters.hasTitle ? 'Yes' : 'No'}`,
                type: 'hasTitle'
            });
        }
        
        if (currentFilters.hasAuthor !== null) {
            chips.push({
                label: `Has author: ${currentFilters.hasAuthor ? 'Yes' : 'No'}`,
                type: 'hasAuthor'
            });
        }
        
        // Page management filters
        if (currentFilters.starredOnly) {
            chips.push({
                label: 'Starred only',
                type: 'starredOnly'
            });
        }
        
        currentFilters.tags.forEach(tag => {
            chips.push({
                label: `Tag: ${tag}`,
                type: 'tags',
                value: tag
            });
        });
        
        currentFilters.reviewStatus.forEach(status => {
            chips.push({
                label: `Status: ${status}`,
                type: 'reviewStatus',
                value: status
            });
        });
        
        
        return chips;
    })();
</script>

<!-- Desktop Sidebar -->
{#if isDesktop}
    <div class="relative">
        <!-- Sidebar -->
        <div class="filter-sidebar {collapsed ? 'collapsed' : ''}" class:collapsed>
            <div class="bg-background border-l border-border h-full">
                <!-- Header -->
                <div class="p-4 border-b border-border">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center space-x-2">
                            <Filter class="h-4 w-4" />
                            {#if !collapsed}
                                <span class="font-medium">Filters</span>
                                {#if $activeFilterCount > 0}
                                    <Badge variant="secondary" class="text-xs">
                                        {$activeFilterCount}
                                    </Badge>
                                {/if}
                            {/if}
                        </div>
                        
                        <div class="flex items-center space-x-1">
                            {#if !collapsed && $hasActiveFilters}
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onclick={handleResetFilters}
                                    class="h-6 px-2 text-xs"
                                    title="Reset all filters"
                                >
                                    <RotateCcw class="h-3 w-3" />
                                </Button>
                            {/if}
                            <Button
                                variant="ghost"
                                size="sm"
                                onclick={toggleCollapsed}
                                class="h-6 w-6 p-0"
                                title={collapsed ? 'Expand filters' : 'Collapse filters'}
                            >
                                {#if collapsed}
                                    <ChevronLeft class="h-3 w-3" />
                                {:else}
                                    <ChevronRight class="h-3 w-3" />
                                {/if}
                            </Button>
                        </div>
                    </div>
                </div>
                
                {#if !collapsed}
                    <!-- Active Filters Summary -->
                    {#if activeFilterChips.length > 0}
                        <div class="p-3 border-b border-border animate-in slide-in-from-top-2 duration-200">
                            <div class="space-y-2">
                                <span class="text-xs text-muted-foreground">Active filters:</span>
                                <div class="flex flex-wrap gap-1">
                                    {#each activeFilterChips.slice(0, 3) as chip}
                                        <Badge variant="secondary" class="text-xs animate-in fade-in scale-in-95 duration-200">
                                            {chip.label}
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onclick={() => handleRemoveFilter(chip.type, chip.value)}
                                                class="ml-1 h-3 w-3 p-0 hover:bg-destructive/80 hover:text-destructive-foreground transition-colors"
                                            >
                                                <X class="h-2 w-2" />
                                            </Button>
                                        </Badge>
                                    {/each}
                                    {#if activeFilterChips.length > 3}
                                        <Badge variant="outline" class="text-xs animate-in fade-in scale-in-95 duration-200 delay-75">
                                            +{activeFilterChips.length - 3} more
                                        </Badge>
                                    {/if}
                                </div>
                            </div>
                        </div>
                    {/if}
                    
                    <!-- Filter Content -->
                    <ScrollArea class="flex-1 p-4">
                        <div class="space-y-6">
                            <PageManagementFilters />
                            <Separator />
                            <ProjectDomainFilters 
                                bind:projects={currentFilters.projects}
                                bind:domains={currentFilters.domains}
                            />
                            <Separator />
                            <DateRangeFilter bind:dateRange={currentFilters.dateRange} />
                            <Separator />
                            <EntityFilters bind:entities={currentFilters.entities} />
                            <Separator />
                            <ContentFilters 
                                bind:contentTypes={currentFilters.contentTypes}
                                bind:languages={currentFilters.languages}
                                bind:wordCount={currentFilters.wordCount}
                                bind:hasTitle={currentFilters.hasTitle}
                                bind:hasAuthor={currentFilters.hasAuthor}
                            />
                        </div>
                    </ScrollArea>
                {/if}
            </div>
        </div>
    </div>
{:else}
    <!-- Mobile Filter Button & Sheet -->
    <Sheet bind:open={mobileFiltersOpen}>
        <SheetTrigger asChild>
            <Button variant="outline" size="sm" class="relative">
                <Filter class="h-4 w-4 mr-2" />
                Filters
                {#if $activeFilterCount > 0}
                    <Badge variant="destructive" class="ml-2 h-4 w-4 p-0 text-xs rounded-full">
                        {$activeFilterCount}
                    </Badge>
                {/if}
            </Button>
        </SheetTrigger>
        
        <SheetContent side="right" class="w-80 sm:w-96">
            <SheetHeader>
                <SheetTitle class="flex items-center justify-between">
                    <div class="flex items-center space-x-2">
                        <Filter class="h-4 w-4" />
                        <span>Filters</span>
                        {#if $activeFilterCount > 0}
                            <Badge variant="secondary" class="text-xs">
                                {$activeFilterCount}
                            </Badge>
                        {/if}
                    </div>
                    {#if $hasActiveFilters}
                        <Button
                            variant="ghost"
                            size="sm"
                            onclick={handleResetFilters}
                            class="h-6 px-2 text-xs"
                        >
                            <RotateCcw class="h-3 w-3 mr-1" />
                            Reset
                        </Button>
                    {/if}
                </SheetTitle>
            </SheetHeader>
            
            <!-- Active Filters Summary -->
            {#if activeFilterChips.length > 0}
                <div class="py-3 border-b border-border animate-in slide-in-from-top-2 duration-200">
                    <div class="space-y-2">
                        <span class="text-xs text-muted-foreground">Active filters:</span>
                        <div class="flex flex-wrap gap-1">
                            {#each activeFilterChips as chip}
                                <Badge variant="secondary" class="text-xs animate-in fade-in scale-in-95 duration-200">
                                    {chip.label}
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onclick={() => handleRemoveFilter(chip.type, chip.value)}
                                        class="ml-1 h-3 w-3 p-0 hover:bg-destructive/80 hover:text-destructive-foreground transition-colors"
                                    >
                                        <X class="h-2 w-2" />
                                    </Button>
                                </Badge>
                            {/each}
                        </div>
                    </div>
                </div>
            {/if}
            
            <!-- Filter Content -->
            <ScrollArea class="flex-1 py-4">
                <div class="space-y-6">
                    <PageManagementFilters />
                    <Separator />
                    <ProjectDomainFilters 
                        bind:projects={currentFilters.projects}
                        bind:domains={currentFilters.domains}
                    />
                    <Separator />
                    <DateRangeFilter bind:dateRange={currentFilters.dateRange} />
                    <Separator />
                    <EntityFilters bind:entities={currentFilters.entities} />
                    <Separator />
                    <ContentFilters 
                        bind:contentTypes={currentFilters.contentTypes}
                        bind:languages={currentFilters.languages}
                        bind:wordCount={currentFilters.wordCount}
                        bind:hasTitle={currentFilters.hasTitle}
                        bind:hasAuthor={currentFilters.hasAuthor}
                    />
                </div>
            </ScrollArea>
            
            <!-- Apply button for mobile -->
            <div class="pt-4 border-t border-border">
                <Button 
                    onclick={() => { mobileFiltersOpen = false; }}
                    class="w-full"
                >
                    Apply Filters
                </Button>
            </div>
        </SheetContent>
    </Sheet>
{/if}

<style>
    .filter-sidebar {
        position: sticky;
        top: 20px;
        width: 320px;
        height: calc(100vh - 40px);
        transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1), transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        overflow: hidden;
    }
    
    .filter-sidebar.collapsed {
        width: 60px;
    }
    
    /* Smooth content transitions */
    .filter-sidebar .bg-background {
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    .filter-sidebar.collapsed .bg-background {
        border-radius: 0.5rem;
    }
    
    @media (max-width: 768px) {
        .filter-sidebar {
            display: none;
        }
    }
</style>