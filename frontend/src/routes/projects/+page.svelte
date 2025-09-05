<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { getApiUrl, apiFetch } from '$lib/utils';
  import { isAuthenticated, auth } from '$lib/stores/auth';
  import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import { Badge } from '$lib/components/ui/badge';
  import { Input } from '$lib/components/ui/input';
  import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
  import { Plus, FolderOpen, MoreHorizontal, Calendar, Activity, Trash2, Edit, Eye, AlertTriangle, Filter, Search } from 'lucide-svelte';
  import ArchiveSourceBadge from '$lib/components/project/ArchiveSourceBadge.svelte';
  
  let projects: any[] = [];
  let filteredProjects: any[] = [];
  let error = '';
  let deletingProjectId: number | null = null;
  let openDropdownId: number | null = null;
  
  // Filtering and search state
  let searchQuery = '';
  let archiveSourceFilter = 'all';
  let statusFilter = 'all';
  let showFilters = false;

  onMount(async () => {
    // Initialize auth and check if user is authenticated
    await auth.init();
    
    // Redirect to login if not authenticated
    if (!$isAuthenticated) {
      goto('/auth/login?redirect=/projects');
      return;
    }
    
    try {
      const url = getApiUrl('/api/v1/projects/');
      const res = await apiFetch(url);
      if (res.ok) {
        projects = await res.json();
        applyFilters();
      } else if (res.status === 401) {
        error = 'You are not authorized to view projects.';
      } else {
        error = 'Failed to load projects.';
      }
    } catch (e) {
      error = 'Network error while loading projects.';
    }
  });
  
  function getStatusColor(status: string) {
    switch (status) {
      case 'indexed': return 'default';
      case 'indexing': return 'secondary';
      case 'error': return 'destructive';
      case 'paused': return 'outline';
      default: return 'secondary';
    }
  }

  async function deleteProject(projectId: number, projectName: string) {
    if (!confirm(`Are you sure you want to delete the project "${projectName}"? This action cannot be undone.`)) {
      return;
    }

    deletingProjectId = projectId;
    
    try {
      const response = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}`), {
        method: 'DELETE'
      });

      if (response.ok) {
        // Remove the project from the local projects array
        projects = projects.filter(p => p.id !== projectId);
      } else if (response.status === 401) {
        error = 'You are not authorized to delete this project.';
      } else {
        const errorData = await response.json().catch(() => ({}));
        error = errorData.detail || 'Failed to delete project.';
      }
    } catch (e) {
      error = 'Network error while deleting project.';
    } finally {
      deletingProjectId = null;
    }
  }

  function toggleDropdown(projectId: number) {
    openDropdownId = openDropdownId === projectId ? null : projectId;
  }

  function closeDropdown() {
    openDropdownId = null;
  }

  // Close dropdown when clicking outside
  function handleClickOutside(event: MouseEvent) {
    const target = event.target as HTMLElement;
    if (!target.closest('.dropdown-menu')) {
      closeDropdown();
    }
  }
  
  // Filtering functions
  function applyFilters() {
    filteredProjects = projects.filter(project => {
      // Search filter
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        const matches = 
          (project.name || '').toLowerCase().includes(query) ||
          (project.description || '').toLowerCase().includes(query);
        if (!matches) return false;
      }
      
      // Archive source filter
      if (archiveSourceFilter !== 'all') {
        const projectArchiveSource = project.archive_source || 'wayback';
        if (projectArchiveSource !== archiveSourceFilter) return false;
      }
      
      // Status filter
      if (statusFilter !== 'all') {
        const projectStatus = project.status || 'no_index';
        if (projectStatus !== statusFilter) return false;
      }
      
      return true;
    });
  }
  
  // Reactive statements for filtering
  $: if (searchQuery || archiveSourceFilter || statusFilter) {
    applyFilters();
  }
  
  function clearFilters() {
    searchQuery = '';
    archiveSourceFilter = 'all';
    statusFilter = 'all';
    applyFilters();
  }
  
  function getArchiveSourceCounts() {
    const counts = { wayback: 0, commoncrawl: 0, hybrid: 0 };
    projects.forEach(project => {
      const source = project.archive_source || 'wayback';
      counts[source]++;
    });
    return counts;
  }
  
  $: archiveSourceCounts = getArchiveSourceCounts();
</script>

<svelte:head>
  <title>Projects - Chrono Scraper</title>
</svelte:head>

<svelte:window onclick={handleClickOutside} />

<DashboardLayout>
  <div class="space-y-8">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h2 class="text-2xl sm:text-3xl font-bold tracking-tight">Projects</h2>
        <p class="text-muted-foreground text-sm sm:text-base">
          Manage your web scraping and data collection projects.
          {#if projects.length > 0}
            <span class="hidden sm:inline">
              ({filteredProjects.length} of {projects.length} shown)
            </span>
          {/if}
        </p>
      </div>
      <div class="flex flex-col sm:flex-row gap-2">
        <Button
          variant="outline"
          size="sm"
          onclick={() => showFilters = !showFilters}
          class="w-full sm:w-auto"
        >
          <Filter class="mr-2 h-4 w-4" />
          {showFilters ? 'Hide' : 'Show'} Filters
          {#if searchQuery || archiveSourceFilter !== 'all' || statusFilter !== 'all'}
            <Badge variant="secondary" class="ml-2 px-1.5 py-0.5 text-xs">Active</Badge>
          {/if}
        </Button>
        <a href="/projects/create" class="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2 w-full sm:w-auto">
          <Plus class="mr-2 h-4 w-4" />
          New Project
        </a>
      </div>
    </div>
    
    <!-- Search and Filters -->
    {#if showFilters || searchQuery || archiveSourceFilter !== 'all' || statusFilter !== 'all'}
      <Card class="bg-muted/30">
        <CardContent class="pt-6">
          <div class="space-y-4">
            <!-- Search -->
            <div class="relative">
              <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
              <Input
                bind:value={searchQuery}
                placeholder="Search projects by name or description..."
                class="pl-10"
              />
            </div>
            
            <!-- Filter Controls -->
            <div class="flex flex-col sm:flex-row gap-4">
              <!-- Archive Source Filter -->
              <div class="flex-1">
                <label class="text-sm font-medium mb-2 block">Archive Source</label>
                <Select bind:value={archiveSourceFilter}>
                  <SelectTrigger>
                    <SelectValue placeholder="All sources" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Sources ({projects.length})</SelectItem>
                    <SelectItem value="wayback">
                      <div class="flex items-center gap-2">
                        🏛️ Wayback Machine
                        <Badge variant="secondary" class="ml-auto">{archiveSourceCounts.wayback}</Badge>
                      </div>
                    </SelectItem>
                    <SelectItem value="commoncrawl">
                      <div class="flex items-center gap-2">
                        🌐 Common Crawl
                        <Badge variant="secondary" class="ml-auto">{archiveSourceCounts.commoncrawl}</Badge>
                      </div>
                    </SelectItem>
                    <SelectItem value="hybrid">
                      <div class="flex items-center gap-2">
                        ⚡ Hybrid Mode
                        <Badge variant="secondary" class="ml-auto">{archiveSourceCounts.hybrid}</Badge>
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <!-- Status Filter -->
              <div class="flex-1">
                <label class="text-sm font-medium mb-2 block">Status</label>
                <Select bind:value={statusFilter}>
                  <SelectTrigger>
                    <SelectValue placeholder="All statuses" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Statuses</SelectItem>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="indexing">Indexing</SelectItem>
                    <SelectItem value="indexed">Indexed</SelectItem>
                    <SelectItem value="paused">Paused</SelectItem>
                    <SelectItem value="error">Error</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <!-- Clear Filters -->
              <div class="flex items-end">
                <Button
                  variant="outline"
                  size="sm"
                  onclick={clearFilters}
                  disabled={!searchQuery && archiveSourceFilter === 'all' && statusFilter === 'all'}
                >
                  Clear
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    {/if}
    
    {#if error}
      <Card class="border-destructive">
        <CardContent class="pt-4 sm:pt-6">
          <div class="flex items-start sm:items-center space-x-2 text-destructive">
            <AlertTriangle class="h-4 w-4 mt-0.5 sm:mt-0 flex-shrink-0" />
            <p class="text-sm sm:text-base break-words">{error}</p>
          </div>
        </CardContent>
      </Card>
    {/if}
    
    {#if filteredProjects.length === 0 && projects.length === 0 && !error}
      <Card>
        <CardContent class="pt-6">
          <div class="flex flex-col items-center justify-center space-y-3 py-12">
            <FolderOpen class="h-12 w-12 text-muted-foreground" />
            <div class="text-center">
              <h3 class="text-lg font-semibold">No projects yet</h3>
              <p class="text-muted-foreground mb-4">
                Create your first project to start scraping and analyzing web data.
              </p>
              <a href="/projects/create" class="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2">
                <Plus class="mr-2 h-4 w-4" />
                Create Project
              </a>
            </div>
          </div>
        </CardContent>
      </Card>
    {:else if filteredProjects.length === 0 && projects.length > 0}
      <Card class="border-amber-200 bg-amber-50 dark:bg-amber-950/20">
        <CardContent class="pt-6">
          <div class="flex flex-col items-center justify-center space-y-3 py-8">
            <Filter class="h-12 w-12 text-amber-600 dark:text-amber-400" />
            <div class="text-center">
              <h3 class="text-lg font-semibold text-amber-800 dark:text-amber-200">No matching projects</h3>
              <p class="text-amber-600 dark:text-amber-300 mb-4">
                No projects match your current filters. Try adjusting your search or filter criteria.
              </p>
              <Button variant="outline" onclick={clearFilters}>
                Clear All Filters
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    {:else}
      <div class="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
        {#each filteredProjects as project}
          <Card class="hover:shadow-md transition-shadow cursor-pointer">
            <CardHeader class="pb-2">
              <div class="flex items-start sm:items-center justify-between gap-2">
                <CardTitle class="text-base sm:text-lg leading-tight flex-1 min-w-0">{project.name || project.title || 'Untitled Project'}</CardTitle>
                <div class="relative dropdown-menu flex-shrink-0">
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    class="h-8 w-8 p-0 touch-target-44"
                    disabled={deletingProjectId === project.id}
                    onclick={() => toggleDropdown(project.id)}
                  >
                    <MoreHorizontal class="h-4 w-4" />
                  </Button>
                  
                  {#if openDropdownId === project.id}
                    <div class="absolute right-0 top-8 w-48 bg-background border border-border rounded-md shadow-lg z-50 sm:w-48">
                      <div class="py-1">
                        <a 
                          href="/projects/{project.id}" 
                          class="flex items-center px-3 py-3 sm:py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors touch-target-44"
                          onclick={() => closeDropdown()}
                        >
                          <Eye class="mr-2 h-4 w-4" />
                          View Details
                        </a>
                        <a 
                          href="/projects/{project.id}/manage" 
                          class="flex items-center px-3 py-3 sm:py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors touch-target-44"
                          onclick={() => closeDropdown()}
                        >
                          <Edit class="mr-2 h-4 w-4" />
                          Manage
                        </a>
                        <hr class="my-1 border-border" />
                        <button
                          class="flex items-center w-full px-3 py-3 sm:py-2 text-sm text-destructive hover:bg-accent hover:text-destructive transition-colors text-left disabled:opacity-50 disabled:cursor-not-allowed touch-target-44"
                          onclick={() => {
                            closeDropdown();
                            deleteProject(project.id, project.name || project.title || 'Untitled Project');
                          }}
                          disabled={deletingProjectId === project.id}
                        >
                          <Trash2 class="mr-2 h-4 w-4" />
                          {deletingProjectId === project.id ? 'Deleting...' : 'Delete Project'}
                        </button>
                      </div>
                    </div>
                  {/if}
                </div>
              </div>
              {#if project.description}
                <CardDescription class="line-clamp-2 text-sm">
                  {project.description}
                </CardDescription>
              {/if}
            </CardHeader>
            <CardContent class="space-y-4">
              <div class="flex flex-col gap-2">
                <div class="flex flex-wrap items-center gap-2">
                  <Badge variant={getStatusColor(project.status || 'no_index')} class="self-start">
                    {project.status || 'No Index'}
                  </Badge>
                  <ArchiveSourceBadge 
                    archiveSource={project.archive_source || 'wayback'}
                    fallbackEnabled={project.fallback_enabled || false}
                    size="sm"
                    showIcon={true}
                    showTooltip={true}
                  />
                </div>
                <div class="flex items-center text-xs sm:text-sm text-muted-foreground">
                  <Calendar class="mr-1 h-3 w-3" />
                  {new Date(project.created_at || Date.now()).toLocaleDateString()}
                </div>
              </div>
              
              <div class="flex items-center justify-between text-xs sm:text-sm">
                <div class="flex items-center text-muted-foreground">
                  <Activity class="mr-1 h-3 w-3" />
                  {project.total_pages || 0} pages
                </div>
                <div class="flex items-center text-muted-foreground">
                  <FolderOpen class="mr-1 h-3 w-3" />
                  {project.domain_count || 0} targets
                </div>
              </div>
              
              <div class="flex flex-col sm:flex-row space-y-2 sm:space-y-0 sm:space-x-2 pt-2">
                <a 
                  href="/projects/{project.id}" 
                  class="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 sm:h-9 px-3 flex-1 touch-target-44"
                  class:opacity-50={deletingProjectId === project.id}
                  class:pointer-events-none={deletingProjectId === project.id}
                >
                  View Details
                </a>
                <a 
                  href="/projects/{project.id}/manage" 
                  class="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 sm:h-9 px-3 flex-1 touch-target-44"
                  class:opacity-50={deletingProjectId === project.id}
                  class:pointer-events-none={deletingProjectId === project.id}
                >
                  {#if deletingProjectId === project.id}
                    Deleting...
                  {:else}
                    Manage
                  {/if}
                </a>
              </div>
            </CardContent>
          </Card>
        {/each}
      </div>
    {/if}
  </div>
</DashboardLayout>

