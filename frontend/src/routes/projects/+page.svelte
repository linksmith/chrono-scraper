<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { isAuthenticated, auth } from '$lib/stores/auth';
  import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import { Badge } from '$lib/components/ui/badge';
  import { Plus, FolderOpen, MoreHorizontal, Calendar, Activity, Trash2, Edit, Eye } from 'lucide-svelte';
  
  let projects: any[] = [];
  let error = '';
  let deletingProjectId: number | null = null;
  let openDropdownId: number | null = null;

  onMount(async () => {
    // Initialize auth and check if user is authenticated
    await auth.init();
    
    // Redirect to login if not authenticated
    if (!$isAuthenticated) {
      goto('/auth/login?redirect=/projects');
      return;
    }
    
    try {
      const url = '/api/v1/projects/';
      const res = await fetch(url, { credentials: 'include' });
      if (res.ok) {
        projects = await res.json();
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
      const response = await fetch(`/api/v1/projects/${projectId}`, {
        method: 'DELETE',
        credentials: 'include'
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
</script>

<svelte:head>
  <title>Projects - Chrono Scraper</title>
</svelte:head>

<svelte:window onclick={handleClickOutside} />

<DashboardLayout>
  <div class="space-y-8">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-3xl font-bold tracking-tight">Projects</h2>
        <p class="text-muted-foreground">
          Manage your web scraping and data collection projects.
        </p>
      </div>
      <a href="/projects/create" class="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2">
        <Plus class="mr-2 h-4 w-4" />
        New Project
      </a>
    </div>
    
    {#if error}
      <Card class="border-destructive">
        <CardContent class="pt-6">
          <div class="flex items-center space-x-2 text-destructive">
            <p>{error}</p>
          </div>
        </CardContent>
      </Card>
    {/if}
    
    {#if projects.length === 0 && !error}
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
    {:else}
      <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {#each projects as project}
          <Card class="hover:shadow-md transition-shadow cursor-pointer">
            <CardHeader class="pb-2">
              <div class="flex items-center justify-between">
                <CardTitle class="text-lg">{project.name || project.title || 'Untitled Project'}</CardTitle>
                <div class="relative dropdown-menu">
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    class="h-8 w-8 p-0"
                    disabled={deletingProjectId === project.id}
                    onclick={() => toggleDropdown(project.id)}
                  >
                    <MoreHorizontal class="h-4 w-4" />
                  </Button>
                  
                  {#if openDropdownId === project.id}
                    <div class="absolute right-0 top-8 w-48 bg-background border border-border rounded-md shadow-lg z-50">
                      <div class="py-1">
                        <a 
                          href="/projects/{project.id}" 
                          class="flex items-center px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
                          onclick={() => closeDropdown()}
                        >
                          <Eye class="mr-2 h-4 w-4" />
                          View Details
                        </a>
                        <a 
                          href="/projects/{project.id}/manage" 
                          class="flex items-center px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
                          onclick={() => closeDropdown()}
                        >
                          <Edit class="mr-2 h-4 w-4" />
                          Manage
                        </a>
                        <hr class="my-1 border-border" />
                        <button
                          class="flex items-center w-full px-3 py-2 text-sm text-destructive hover:bg-accent hover:text-destructive transition-colors text-left disabled:opacity-50 disabled:cursor-not-allowed"
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
                <CardDescription class="line-clamp-2">
                  {project.description}
                </CardDescription>
              {/if}
            </CardHeader>
            <CardContent class="space-y-4">
              <div class="flex items-center justify-between">
                <Badge variant={getStatusColor(project.status || 'no_index')}>
                  {project.status || 'No Index'}
                </Badge>
                <div class="flex items-center text-sm text-muted-foreground">
                  <Calendar class="mr-1 h-3 w-3" />
                  {new Date(project.created_at || Date.now()).toLocaleDateString()}
                </div>
              </div>
              
              <div class="flex items-center justify-between text-sm">
                <div class="flex items-center text-muted-foreground">
                  <Activity class="mr-1 h-3 w-3" />
                  {project.total_pages || 0} pages
                </div>
                <div class="flex items-center text-muted-foreground">
                  <FolderOpen class="mr-1 h-3 w-3" />
                  {project.domain_count || 0} domains
                </div>
              </div>
              
              <div class="flex space-x-2 pt-2">
                <a 
                  href="/projects/{project.id}" 
                  class="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-9 px-3 flex-1"
                  class:opacity-50={deletingProjectId === project.id}
                  class:pointer-events-none={deletingProjectId === project.id}
                >
                  View Details
                </a>
                <a 
                  href="/projects/{project.id}/manage" 
                  class="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-9 px-3 flex-1"
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

