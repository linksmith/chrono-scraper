<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { isAuthenticated, auth } from '$lib/stores/auth';
  import { getApiUrl } from '$lib/utils';
  import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import { Badge } from '$lib/components/ui/badge';
  import { Plus, FolderOpen, MoreHorizontal, Calendar, Activity } from 'lucide-svelte';
  
  let projects: any[] = [];
  let error = '';

  onMount(async () => {
    // Initialize auth and check if user is authenticated
    await auth.init();
    
    // Redirect to login if not authenticated
    if (!$isAuthenticated) {
      goto('/auth/login?redirect=/projects');
      return;
    }
    
    try {
      const res = await fetch(getApiUrl('/api/v1/projects'), { credentials: 'include' });
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
</script>

<svelte:head>
  <title>Projects - Chrono Scraper</title>
</svelte:head>

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
      <Button on:click={() => goto('/projects/create')}>
        <Plus class="mr-2 h-4 w-4" />
        New Project
      </Button>
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
              <Button on:click={() => goto('/projects/create')}>
                <Plus class="mr-2 h-4 w-4" />
                Create Project
              </Button>
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
                <Button variant="ghost" size="sm" class="h-8 w-8 p-0">
                  <MoreHorizontal class="h-4 w-4" />
                </Button>
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
                <Button variant="outline" size="sm" class="flex-1" on:click={() => goto(`/projects/${project.id}`)}>
                  View Details
                </Button>
                <Button size="sm" class="flex-1" on:click={() => goto(`/projects/${project.id}/manage`)}>
                  Manage
                </Button>
              </div>
            </CardContent>
          </Card>
        {/each}
      </div>
    {/if}
  </div>
</DashboardLayout>

