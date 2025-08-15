<script lang="ts">
    import { Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem } from "$lib/components/ui/command";
    import { Popover, PopoverContent, PopoverTrigger } from "$lib/components/ui/popover";
    import { Button } from "$lib/components/ui/button";
    import { Badge } from "$lib/components/ui/badge";
    import { Input } from "$lib/components/ui/input";
    import { 
        Users, 
        Building2, 
        MapPin, 
        Calendar, 
        Plus, 
        X,
        ChevronDown
    } from "lucide-svelte";
    import { filters, type FilterState } from "$lib/stores/filters";
    import { onMount } from "svelte";
    
    export let entities: FilterState['entities'] = {
        person: [],
        organization: [],
        location: [],
        event: []
    };
    
    // Entity type configuration
    const entityTypes = [
        { 
            key: 'person' as const, 
            label: 'People', 
            icon: Users, 
            color: 'bg-blue-100 text-blue-800 border-blue-200',
            placeholder: 'Search for people...'
        },
        { 
            key: 'organization' as const, 
            label: 'Organizations', 
            icon: Building2, 
            color: 'bg-green-100 text-green-800 border-green-200',
            placeholder: 'Search for organizations...'
        },
        { 
            key: 'location' as const, 
            label: 'Locations', 
            icon: MapPin, 
            color: 'bg-orange-100 text-orange-800 border-orange-200',
            placeholder: 'Search for locations...'
        },
        { 
            key: 'event' as const, 
            label: 'Events', 
            icon: Calendar, 
            color: 'bg-purple-100 text-purple-800 border-purple-200',
            placeholder: 'Search for events...'
        }
    ];
    
    // State for each entity type
    let searchQueries: Record<string, string> = {};
    let searchResults: Record<string, any[]> = {};
    let openPopovers: Record<string, boolean> = {};
    let loading: Record<string, boolean> = {};
    
    // Available entities from facets
    let availableEntities: Record<string, any[]> = {
        person: [],
        organization: [],
        location: [],
        event: []
    };
    
    onMount(async () => {
        // Load available entities from facets
        await loadEntityFacets();
    });
    
    async function loadEntityFacets() {
        try {
            const response = await fetch('/api/v1/search/facets', {
                credentials: 'include'
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.entities) {
                    availableEntities = data.entities;
                }
            }
        } catch (error) {
            console.error('Failed to load entity facets:', error);
        }
    }
    
    async function searchEntities(entityType: string, query: string) {
        if (!query.trim()) {
            searchResults[entityType] = availableEntities[entityType] || [];
            return;
        }
        
        loading[entityType] = true;
        
        try {
            // Search in available entities first (client-side filtering)
            const available = availableEntities[entityType] || [];
            const filtered = available.filter(entity => 
                entity.name.toLowerCase().includes(query.toLowerCase()) ||
                (entity.aliases && entity.aliases.some((alias: string) => 
                    alias.toLowerCase().includes(query.toLowerCase())
                ))
            );
            
            // If we have enough results, use them
            if (filtered.length >= 5) {
                searchResults[entityType] = filtered.slice(0, 10);
            } else {
                // Otherwise, search backend for more entities
                const response = await fetch(
                    `/api/v1/entities/search?q=${encodeURIComponent(query)}&type=${entityType}&limit=10`,
                    { credentials: 'include' }
                );
                
                if (response.ok) {
                    const data = await response.json();
                    searchResults[entityType] = data.entities || filtered;
                } else {
                    searchResults[entityType] = filtered;
                }
            }
        } catch (error) {
            console.error(`Failed to search ${entityType} entities:`, error);
            searchResults[entityType] = [];
        } finally {
            loading[entityType] = false;
        }
    }
    
    function addEntity(entityType: keyof FilterState['entities'], entity: any) {
        const entityName = typeof entity === 'string' ? entity : (entity.name || entity.primary_name);
        
        if (!entities[entityType].includes(entityName)) {
            entities = {
                ...entities,
                [entityType]: [...entities[entityType], entityName]
            };
            
            filters.update(f => ({
                ...f,
                entities: entities
            }));
        }
        
        // Clear search and close popover
        searchQueries[entityType] = '';
        openPopovers[entityType] = false;
    }
    
    function removeEntity(entityType: keyof FilterState['entities'], entityName: string) {
        entities = {
            ...entities,
            [entityType]: entities[entityType].filter(name => name !== entityName)
        };
        
        filters.update(f => ({
            ...f,
            entities: entities
        }));
    }
    
    function handleSearchInput(entityType: string, event: Event) {
        const target = event.target as HTMLInputElement;
        searchQueries[entityType] = target.value;
        searchEntities(entityType, target.value);
    }
    
    function handleKeydown(entityType: keyof FilterState['entities'], event: KeyboardEvent) {
        if (event.key === 'Enter' && searchQueries[entityType].trim()) {
            event.preventDefault();
            addEntity(entityType, searchQueries[entityType].trim());
        }
    }
    
    // Initialize search results
    entityTypes.forEach(type => {
        searchQueries[type.key] = '';
        searchResults[type.key] = [];
        openPopovers[type.key] = false;
        loading[type.key] = false;
    });
    
    $: totalSelectedEntities = Object.values(entities).reduce((sum, arr) => sum + arr.length, 0);
</script>

<div class="space-y-4">
    <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
            <Users class="h-4 w-4 text-muted-foreground" />
            <span class="text-sm font-medium">Entities</span>
            {#if totalSelectedEntities > 0}
                <Badge variant="secondary" class="text-xs">
                    {totalSelectedEntities}
                </Badge>
            {/if}
        </div>
    </div>
    
    {#each entityTypes as entityType}
        <div class="space-y-2">
            <!-- Entity type header -->
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-2">
                    <svelte:component this={entityType.icon} class="h-3 w-3 text-muted-foreground" />
                    <span class="text-xs font-medium text-muted-foreground">{entityType.label}</span>
                    {#if entities[entityType.key].length > 0}
                        <Badge variant="outline" class="text-xs h-4 px-1">
                            {entities[entityType.key].length}
                        </Badge>
                    {/if}
                </div>
            </div>
            
            <!-- Selected entities -->
            {#if entities[entityType.key].length > 0}
                <div class="flex flex-wrap gap-1">
                    {#each entities[entityType.key] as entityName}
                        <Badge variant="secondary" class="{entityType.color} text-xs">
                            {entityName}
                            <Button
                                variant="ghost"
                                size="sm"
                                onclick={() => removeEntity(entityType.key, entityName)}
                                class="ml-1 h-3 w-3 p-0 hover:bg-transparent"
                            >
                                <X class="h-2 w-2" />
                            </Button>
                        </Badge>
                    {/each}
                </div>
            {/if}
            
            <!-- Entity search -->
            <Popover bind:open={openPopovers[entityType.key]}>
                <PopoverTrigger asChild let:builder>
                    <Button
                        builders={[builder]}
                        variant="outline"
                        size="sm"
                        class="w-full justify-start text-xs h-8"
                    >
                        <Plus class="h-3 w-3 mr-1" />
                        Add {entityType.label.toLowerCase()}
                        <ChevronDown class="h-3 w-3 ml-auto" />
                    </Button>
                </PopoverTrigger>
                <PopoverContent class="w-80 p-0" align="start">
                    <Command>
                        <CommandInput
                            placeholder={entityType.placeholder}
                            bind:value={searchQueries[entityType.key]}
                            onInput={(e) => handleSearchInput(entityType.key, e)}
                            onKeydown={(e) => handleKeydown(entityType.key, e)}
                        />
                        <CommandList>
                            {#if loading[entityType.key]}
                                <div class="p-2 text-center text-xs text-muted-foreground">
                                    Searching...
                                </div>
                            {:else if searchResults[entityType.key].length === 0}
                                <CommandEmpty>
                                    {#if searchQueries[entityType.key].trim()}
                                        <div class="text-center p-2">
                                            <p class="text-xs text-muted-foreground mb-2">No entities found</p>
                                            <Button
                                                size="sm"
                                                onclick={() => addEntity(entityType.key, searchQueries[entityType.key].trim())}
                                                class="text-xs h-6"
                                            >
                                                Add "{searchQueries[entityType.key].trim()}"
                                            </Button>
                                        </div>
                                    {:else}
                                        <p class="text-xs text-muted-foreground">Type to search entities</p>
                                    {/if}
                                </CommandEmpty>
                            {:else}
                                <CommandGroup>
                                    {#each searchResults[entityType.key] as entity}
                                        <CommandItem
                                            onSelect={() => addEntity(entityType.key, entity)}
                                            class="cursor-pointer"
                                        >
                                            <div class="flex items-center space-x-2">
                                                <svelte:component this={entityType.icon} class="h-3 w-3" />
                                                <div class="flex-1">
                                                    <div class="text-xs font-medium">
                                                        {entity.name || entity.primary_name}
                                                    </div>
                                                    {#if entity.description}
                                                        <div class="text-xs text-muted-foreground truncate">
                                                            {entity.description}
                                                        </div>
                                                    {/if}
                                                </div>
                                                {#if entity.occurrence_count}
                                                    <Badge variant="outline" class="text-xs h-4 px-1">
                                                        {entity.occurrence_count}
                                                    </Badge>
                                                {/if}
                                            </div>
                                        </CommandItem>
                                    {/each}
                                </CommandGroup>
                            {/if}
                        </CommandList>
                    </Command>
                </PopoverContent>
            </Popover>
        </div>
    {/each}
    
    <!-- Show available entities hint -->
    {#if totalSelectedEntities === 0}
        <div class="text-xs text-muted-foreground p-2 bg-muted/50 rounded">
            <p>Filter by people, organizations, locations, and events found in your content.</p>
        </div>
    {/if}
</div>