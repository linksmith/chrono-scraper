<script lang="ts">
    import { onMount } from 'svelte';
    import { Checkbox } from "$lib/components/ui/checkbox";
    import { Badge } from "$lib/components/ui/badge";
    import { Button } from "$lib/components/ui/button";
    import { Input } from "$lib/components/ui/input";
    import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "$lib/components/ui/collapsible";
    import { 
        Building, 
        Globe, 
        ChevronDown,
        ChevronRight,
        X,
        Search,
        Loader2
    } from "lucide-svelte";
    import { filters } from "$lib/stores/filters";
    import { getApiUrl } from "$lib/utils";
    
    export let projects: number[] = [];
    export let domains: string[] = [];
    
    // Available options from API
    let availableProjects: { id: number; name: string; pageCount?: number }[] = [];
    let availableDomains: { name: string; projectId: number; pageCount?: number }[] = [];
    
    // Loading states
    let loadingProjects = false;
    let loadingDomains = false;
    
    // Section expansion state
    let projectsExpanded = false;
    let domainsExpanded = false;
    
    // Search functionality
    let projectSearch = '';
    let domainSearch = '';
    
    // Filtered options based on search
    $: filteredProjects = availableProjects.filter(project =>
        project.name.toLowerCase().includes(projectSearch.toLowerCase())
    );
    
    $: filteredDomains = availableDomains
        .filter(domain => {
            // Only show domains from selected projects (or all if none selected)
            const matchesProject = projects.length === 0 || projects.includes(domain.projectId);
            const matchesSearch = domain.name.toLowerCase().includes(domainSearch.toLowerCase());
            return matchesProject && matchesSearch;
        });
    
    onMount(async () => {
        await loadProjects();
        // Load domains after projects are loaded
        if (availableProjects.length > 0) {
            await loadDomains();
        }
    });
    
    async function loadProjects() {
        loadingProjects = true;
        try {
            const response = await fetch(getApiUrl(`/api/v1/projects/`), {
                credentials: 'include'
            });
            if (response.ok) {
                const data = await response.json();
                availableProjects = data.map((project: any) => ({
                    id: project.id,
                    name: project.name,
                    pageCount: project.total_pages || 0
                }));
                console.log('Loaded projects:', availableProjects);
            } else {
                console.error('Failed to load projects - HTTP error:', response.status);
            }
        } catch (error) {
            console.error('Failed to load projects:', error);
        } finally {
            loadingProjects = false;
        }
    }
    
    async function loadDomains() {
        loadingDomains = true;
        try {
            // Load domains for all projects by fetching from each project's domains endpoint
            const domainsSet = new Set<{ name: string; projectId: number; pageCount: number }>();
            
            // Get domains for each project
            for (const project of availableProjects) {
                try {
                    const response = await fetch(getApiUrl(`/api/v1/projects/${project.id}/domains`), {
                        credentials: 'include'
                    });
                    if (response.ok) {
                        const domains = await response.json();
                        domains.forEach((domain: any) => {
                            domainsSet.add({
                                name: domain.domain_name,
                                projectId: project.id,
                                pageCount: domain.total_pages || 0
                            });
                        });
                    }
                } catch (error) {
                    console.error(`Failed to load domains for project ${project.id}:`, error);
                }
            }
            
            availableDomains = Array.from(domainsSet);
            console.log('Loaded domains:', availableDomains);
        } catch (error) {
            console.error('Failed to load domains:', error);
        } finally {
            loadingDomains = false;
        }
    }
    
    function handleProjectChange(projectId: number, checked: boolean) {
        if (checked) {
            projects = [...projects, projectId];
        } else {
            projects = projects.filter(id => id !== projectId);
        }
        
        // Update filter store
        filters.update(f => ({ ...f, projects }));
        
        // Clear domain selection if it includes domains not from selected projects
        if (projects.length > 0) {
            const validDomains = domains.filter(domainName => {
                const domain = availableDomains.find(d => d.name === domainName);
                return domain && projects.includes(domain.projectId);
            });
            if (validDomains.length !== domains.length) {
                domains = validDomains;
                filters.update(f => ({ ...f, domains }));
            }
        }
    }
    
    function handleDomainChange(domainName: string, checked: boolean) {
        if (checked) {
            domains = [...domains, domainName];
        } else {
            domains = domains.filter(name => name !== domainName);
        }
        
        // Update filter store
        filters.update(f => ({ ...f, domains }));
    }
    
    function clearProjects() {
        projects = [];
        filters.update(f => ({ ...f, projects: [] }));
    }
    
    function clearDomains() {
        domains = [];
        filters.update(f => ({ ...f, domains: [] }));
    }
    
    function selectAllProjects() {
        projects = filteredProjects.map(p => p.id);
        filters.update(f => ({ ...f, projects }));
    }
    
    function selectAllDomains() {
        domains = filteredDomains.map(d => d.name);
        filters.update(f => ({ ...f, domains }));
    }
</script>

<div class="space-y-4">
    <!-- Projects Filter -->
    <Collapsible bind:open={projectsExpanded}>
        <CollapsibleTrigger class="flex items-center justify-between w-full py-3 px-2 text-left bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors">
            <div class="flex items-center space-x-2">
                <Building class="h-4 w-4 text-muted-foreground" />
                <span class="font-medium">Projects</span>
                {#if projects.length > 0}
                    <Badge variant="secondary" class="ml-2">
                        {projects.length}
                    </Badge>
                {/if}
            </div>
            {#if projectsExpanded}
                <ChevronDown class="h-4 w-4 text-muted-foreground" />
            {:else}
                <ChevronRight class="h-4 w-4 text-muted-foreground" />
            {/if}
        </CollapsibleTrigger>
        
        <CollapsibleContent class="pt-3">
            <div class="space-y-3">
                <!-- Search -->
                <div class="relative">
                    <Search class="absolute left-2.5 top-1/2 transform -translate-y-1/2 text-muted-foreground h-3.5 w-3.5" />
                    <Input
                        bind:value={projectSearch}
                        placeholder="Search projects..."
                        class="pl-8 h-8 text-sm"
                    />
                </div>
                
                <!-- Controls -->
                <div class="flex items-center justify-between text-xs">
                    <div class="flex space-x-2">
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            onclick={selectAllProjects}
                            disabled={loadingProjects || filteredProjects.length === 0}
                            class="h-6 px-2 text-xs"
                        >
                            Select All
                        </Button>
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            onclick={clearProjects}
                            disabled={projects.length === 0}
                            class="h-6 px-2 text-xs"
                        >
                            Clear
                        </Button>
                    </div>
                    {#if loadingProjects}
                        <div class="flex items-center space-x-1">
                            <Loader2 class="h-3 w-3 animate-spin" />
                            <span class="text-muted-foreground">Loading...</span>
                        </div>
                    {/if}
                </div>
                
                <!-- Project List -->
                <div class="max-h-48 overflow-y-auto space-y-2">
                    {#each filteredProjects as project (project.id)}
                        <div class="flex items-center space-x-2 p-2 hover:bg-muted/30 rounded">
                            <Checkbox
                                id="project-{project.id}"
                                checked={projects.includes(project.id)}
                                onCheckedChange={(checked) => handleProjectChange(project.id, !!checked)}
                            />
                            <label 
                                for="project-{project.id}" 
                                class="flex-1 text-sm cursor-pointer flex items-center justify-between"
                            >
                                <span class="truncate">{project.name}</span>
                                {#if project.pageCount !== undefined}
                                    <Badge variant="outline" class="ml-2 text-xs">
                                        {project.pageCount}
                                    </Badge>
                                {/if}
                            </label>
                        </div>
                    {/each}
                    
                    {#if !loadingProjects && filteredProjects.length === 0}
                        <div class="text-center text-muted-foreground text-sm py-4">
                            {projectSearch ? 'No projects match your search' : 'No projects available'}
                        </div>
                    {/if}
                </div>
                
                <!-- Selected Projects Display -->
                {#if projects.length > 0}
                    <div class="pt-2 border-t">
                        <div class="text-xs text-muted-foreground mb-1">Selected:</div>
                        <div class="flex flex-wrap gap-1">
                            {#each projects as projectId}
                                {@const project = availableProjects.find(p => p.id === projectId)}
                                {#if project}
                                    <Badge variant="secondary" class="text-xs">
                                        {project.name}
                                        <button
                                            type="button"
                                            onclick={() => handleProjectChange(projectId, false)}
                                            class="ml-1 h-3 w-3 p-0 hover:bg-red-100 rounded-full transition-colors flex items-center justify-center"
                                            aria-label="Remove {project.name} project filter"
                                        >
                                            <X class="h-2 w-2" />
                                        </button>
                                    </Badge>
                                {/if}
                            {/each}
                        </div>
                    </div>
                {/if}
            </div>
        </CollapsibleContent>
    </Collapsible>
    
    <!-- Domains Filter -->
    <Collapsible bind:open={domainsExpanded}>
        <CollapsibleTrigger class="flex items-center justify-between w-full py-3 px-2 text-left bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors">
            <div class="flex items-center space-x-2">
                <Globe class="h-4 w-4 text-muted-foreground" />
                <span class="font-medium">Domains</span>
                {#if domains.length > 0}
                    <Badge variant="secondary" class="ml-2">
                        {domains.length}
                    </Badge>
                {/if}
            </div>
            {#if domainsExpanded}
                <ChevronDown class="h-4 w-4 text-muted-foreground" />
            {:else}
                <ChevronRight class="h-4 w-4 text-muted-foreground" />
            {/if}
        </CollapsibleTrigger>
        
        <CollapsibleContent class="pt-3">
            <div class="space-y-3">
                <!-- Search -->
                <div class="relative">
                    <Search class="absolute left-2.5 top-1/2 transform -translate-y-1/2 text-muted-foreground h-3.5 w-3.5" />
                    <Input
                        bind:value={domainSearch}
                        placeholder="Search domains..."
                        class="pl-8 h-8 text-sm"
                    />
                </div>
                
                <!-- Controls -->
                <div class="flex items-center justify-between text-xs">
                    <div class="flex space-x-2">
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            onclick={selectAllDomains}
                            disabled={loadingDomains || filteredDomains.length === 0}
                            class="h-6 px-2 text-xs"
                        >
                            Select All
                        </Button>
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            onclick={clearDomains}
                            disabled={domains.length === 0}
                            class="h-6 px-2 text-xs"
                        >
                            Clear
                        </Button>
                    </div>
                    {#if loadingDomains}
                        <div class="flex items-center space-x-1">
                            <Loader2 class="h-3 w-3 animate-spin" />
                            <span class="text-muted-foreground">Loading...</span>
                        </div>
                    {/if}
                </div>
                
                <!-- Domain List -->
                <div class="max-h-48 overflow-y-auto space-y-2">
                    {#each filteredDomains as domain (`${domain.projectId}-${domain.name}`)}
                        <div class="flex items-center space-x-2 p-2 hover:bg-muted/30 rounded">
                            <Checkbox
                                id="domain-{domain.name}"
                                checked={domains.includes(domain.name)}
                                onCheckedChange={(checked) => handleDomainChange(domain.name, !!checked)}
                            />
                            <label 
                                for="domain-{domain.name}" 
                                class="flex-1 text-sm cursor-pointer flex items-center justify-between"
                            >
                                <span class="truncate font-mono">{domain.name}</span>
                                {#if domain.pageCount !== undefined}
                                    <Badge variant="outline" class="ml-2 text-xs">
                                        {domain.pageCount}
                                    </Badge>
                                {/if}
                            </label>
                        </div>
                    {/each}
                    
                    {#if !loadingDomains && filteredDomains.length === 0}
                        <div class="text-center text-muted-foreground text-sm py-4">
                            {domainSearch 
                                ? 'No domains match your search' 
                                : projects.length > 0 
                                    ? 'No domains in selected projects'
                                    : 'No domains available'
                            }
                        </div>
                    {/if}
                </div>
                
                <!-- Selected Domains Display -->
                {#if domains.length > 0}
                    <div class="pt-2 border-t">
                        <div class="text-xs text-muted-foreground mb-1">Selected:</div>
                        <div class="flex flex-wrap gap-1">
                            {#each domains as domainName}
                                <Badge variant="secondary" class="text-xs font-mono">
                                    {domainName}
                                    <button
                                        type="button"
                                        onclick={() => handleDomainChange(domainName, false)}
                                        class="ml-1 h-3 w-3 p-0 hover:bg-red-100 rounded-full transition-colors flex items-center justify-center"
                                        aria-label="Remove {domainName} domain filter"
                                    >
                                        <X class="h-2 w-2" />
                                    </button>
                                </Badge>
                            {/each}
                        </div>
                    </div>
                {/if}
                
                {#if projects.length > 0 && domains.length === 0}
                    <div class="text-xs text-muted-foreground bg-muted/30 p-2 rounded">
                        💡 Domains filtered to show only those from selected projects
                    </div>
                {/if}
            </div>
        </CollapsibleContent>
    </Collapsible>
</div>