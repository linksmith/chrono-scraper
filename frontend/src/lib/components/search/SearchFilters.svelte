<script lang="ts">
    import { onMount } from 'svelte';
    import { browser } from '$app/environment';
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
    
    export let mode: 'search' | 'project' = 'search';
    export let projectId: string | null = null;
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
    $: if (browser && currentFilters) {
        updateUrl(currentFilters);
    }
    
    onMount(() => {
        // Check screen size
        const checkScreenSize = () => {
            isDesktop = window.innerWidth >= 768;
        };
        
        checkScreenSize();
        window.addEventListener('resize', checkScreenSize);
        
        // Load filters from URL on mount
        if (browser) {
            const urlParams = new URLSearchParams(window.location.search);
            const filtersFromUrl = urlParamsToFilters(urlParams);
            filters.set(filtersFromUrl);
        }
        
        return () => {
            window.removeEventListener('resize', checkScreenSize);
        };
    });
    
    function updateUrl(filterState: FilterState) {
        if (!browser) return;
        
        const url = new URL(window.location.href);
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
        window.history.replaceState({}, '', url);
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
                        <div class="p-3 border-b border-border">
                            <div class="space-y-2">
                                <span class="text-xs text-muted-foreground">Active filters:</span>
                                <div class="flex flex-wrap gap-1">
                                    {#each activeFilterChips.slice(0, 3) as chip}
                                        <Badge variant="secondary" class="text-xs">
                                            {chip.label}
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onclick={() => handleRemoveFilter(chip.type, chip.value)}
                                                class="ml-1 h-3 w-3 p-0 hover:bg-transparent"
                                            >
                                                <X class="h-2 w-2" />
                                            </Button>
                                        </Badge>
                                    {/each}
                                    {#if activeFilterChips.length > 3}
                                        <Badge variant="outline" class="text-xs">
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
        <SheetTrigger asChild let:builder>
            <Button builders={[builder]} variant="outline" size="sm" class="relative">
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
                <div class="py-3 border-b border-border">
                    <div class="space-y-2">
                        <span class="text-xs text-muted-foreground">Active filters:</span>
                        <div class="flex flex-wrap gap-1">
                            {#each activeFilterChips as chip}
                                <Badge variant="secondary" class="text-xs">
                                    {chip.label}
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onclick={() => handleRemoveFilter(chip.type, chip.value)}
                                        class="ml-1 h-3 w-3 p-0 hover:bg-transparent"
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
        transition: width 0.3s ease, transform 0.3s ease;
    }
    
    .filter-sidebar.collapsed {
        width: 60px;
    }
    
    @media (max-width: 768px) {
        .filter-sidebar {
            display: none;
        }
    }
</style>