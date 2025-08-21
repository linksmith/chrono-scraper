<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { isAuthenticated, auth } from '$lib/stores/auth';
  import { getApiUrl, apiFetch } from '$lib/utils';
  import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import { Badge } from '$lib/components/ui/badge';
  import { Input } from '$lib/components/ui/input';
  import { Label } from '$lib/components/ui/label';
  import { Textarea } from '$lib/components/ui/textarea';
  import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
  import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
  import { Separator } from '$lib/components/ui/separator';
  import { 
    Settings, 
    Edit3, 
    Plus, 
    Trash2, 
    Globe, 
    AlertTriangle,
    Save,
    ArrowLeft,
    MoreHorizontal
  } from 'lucide-svelte';

  let projectId: string = '';
  let project: any = null;
  let domains: any[] = [];
  let loading = false;
  let error = '';
  let success = '';
  let statusMessage = '';
  let activeTab = 'settings';
  
  // Form data
  let projectForm = {
    name: '',
    description: '',
    process_documents: true,
    enable_attachment_download: true,
    langextract_enabled: false,
    langextract_provider: 'disabled',
    langextract_model: ''
  };
  
  let newDomain = {
    domain: '',
    match_type: 'domain',
    max_pages: 1000,
    active: true
  };
  
  let showDeleteConfirm = false;

  $: projectId = ($page.params.id || '') as string;

  onMount(async () => {
    await auth.init();
    
    if (!$isAuthenticated) {
      goto(`/auth/login?redirect=/projects/${projectId}/manage`);
      return;
    }
    
    await loadProject();
    await loadDomains();
  });

  const loadProject = async () => {
    loading = true;
    try {
      const res = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}`));

      if (res.ok) {
        project = await res.json();
        // Populate form
        projectForm = {
          name: project.name || '',
          description: project.description || '',
          process_documents: project.process_documents ?? true,
          enable_attachment_download: project.enable_attachment_download ?? true,
          langextract_enabled: project.langextract_enabled ?? false,
          langextract_provider: project.langextract_provider || 'disabled',
          langextract_model: project.langextract_model || ''
        };
      } else if (res.status === 404) {
        error = 'Project not found.';
      } else if (res.status === 401) {
        error = 'You are not authorized to manage this project.';
      } else {
        error = 'Failed to load project.';
      }
    } catch (e) {
      console.error('Failed to load project:', e);
      error = 'Network error while loading project.';
    } finally {
      loading = false;
    }
  };

  const loadDomains = async () => {
    try {
      const res = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}/domains`));

      if (res.ok) {
        domains = await res.json();
      }
    } catch (e) {
      console.error('Failed to load domains:', e);
    }
  };

  const updateProject = async () => {
    loading = true;
    error = '';
    success = '';
    
    try {
      const res = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}`), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(projectForm)
      });

      if (res.ok) {
        project = await res.json();
        success = 'Project updated successfully!';
      } else {
        const errorData = await res.json().catch(() => ({}));
        error = errorData.detail || 'Failed to update project.';
      }
    } catch (e) {
      console.error('Failed to update project:', e);
      error = 'Network error while updating project.';
    } finally {
      loading = false;
    }
  };

  const addDomain = async () => {
    if (!newDomain.domain) {
      error = 'Target is required.';
      return;
    }

    loading = true;
    error = '';
    success = '';

    try {
      const res = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}/domains`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(newDomain)
      });

      if (res.ok) {
        await loadDomains();
        newDomain = {
          domain: '',
          match_type: 'domain',
          max_pages: 1000,
          active: true
        };
        success = 'Target added successfully!';
      } else {
        const errorData = await res.json().catch(() => ({}));
        error = errorData.detail || 'Failed to add target.';
      }
    } catch (e) {
      console.error('Failed to add target:', e);
      error = 'Network error while adding target.';
    } finally {
      loading = false;
    }
  };

  const deleteDomain = async (domainId: string) => {
    if (!confirm('Are you sure you want to delete this target? This will also delete all associated pages.')) {
      return;
    }

    loading = true;
    error = '';
    success = '';

    try {
      const res = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}/domains/${domainId}`), {
        method: 'DELETE'
      });

      if (res.ok) {
        await loadDomains();
        success = 'Target deleted successfully!';
      } else {
        const errorData = await res.json().catch(() => ({}));
        error = errorData.detail || 'Failed to delete target.';
      }
    } catch (e) {
      console.error('Failed to delete target:', e);
      error = 'Network error while deleting target.';
    } finally {
      loading = false;
    }
  };

  const deleteProject = async () => {
    loading = true;
    error = '';
    statusMessage = '';

    try {
      // Show progress message for active scraping
      const hasActiveScraping = domains?.some((domain: any) => 
        domain.status === 'scraping' || domain.status === 'queued'
      );
      
      if (hasActiveScraping) {
        statusMessage = 'Stopping active scraping tasks...';
      }

      // Create a controller for timeout handling
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout

      const res = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}`), {
        method: 'DELETE',
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (res.ok) {
        statusMessage = 'Project deleted successfully!';
        showDeleteConfirm = false;
        // Small delay to show success message
        setTimeout(() => {
          goto('/projects');
        }, 1000);
      } else {
        const errorData = await res.json().catch(() => ({}));
        if (res.status === 408 || res.status === 504) {
          error = 'Deletion is taking longer than expected. The project may still be processing. Please check the projects list.';
        } else {
          error = errorData.detail || `Failed to delete project (${res.status}).`;
        }
        showDeleteConfirm = false;
      }
    } catch (e: any) {
      console.error('Failed to delete project:', e);
      
      if (e.name === 'AbortError') {
        error = 'Deletion timed out. The project may still be processing. Please check the projects list in a moment.';
      } else if (e.message?.includes('NetworkError') || e.message?.includes('fetch')) {
        error = 'Network error during deletion. The project may still be processing. Please refresh and check the projects list.';
      } else {
        error = 'An unexpected error occurred while deleting the project.';
      }
      showDeleteConfirm = false;
    } finally {
      loading = false;
      statusMessage = '';
    }
  };

  const getDomainStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'active': return 'default';
      case 'paused': return 'secondary';
      case 'completed': return 'outline';
      case 'error': return 'destructive';
      default: return 'secondary';
    }
  };
</script>

<svelte:head>
  <title>Manage {project?.name || 'Project'} - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
  <div class="space-y-6">
    {#if loading && !project}
      <!-- Loading skeleton -->
      <div class="space-y-6">
        <div class="animate-pulse">
          <div class="h-8 bg-gray-200 rounded w-1/3 mb-2"></div>
          <div class="h-4 bg-gray-200 rounded w-1/2"></div>
        </div>
      </div>
    {:else if error}
      <Card class="border-destructive">
        <CardContent class="pt-6">
          <div class="flex items-center space-x-2 text-destructive">
            <AlertTriangle class="h-5 w-5" />
            <p>{error}</p>
          </div>
        </CardContent>
      </Card>
    {:else if project}
      <!-- Header -->
      <div class="flex items-start justify-between">
        <div class="space-y-1">
          <div class="flex items-center gap-2">
            <Button variant="ghost" size="sm" onclick={() => goto(`/projects/${projectId}`)}>
              <ArrowLeft class="h-4 w-4" />
            </Button>
            <h2 class="text-3xl font-bold tracking-tight">Manage Project</h2>
          </div>
          <p class="text-muted-foreground">
            Configure settings and manage targets for "{project.name}"
          </p>
        </div>
      </div>

      {#if success}
        <Card class="border-green-200 bg-green-50">
          <CardContent class="pt-6">
            <div class="flex items-center space-x-2 text-green-800">
              <p>{success}</p>
            </div>
          </CardContent>
        </Card>
      {/if}

      <!-- Tabs -->
      <Tabs bind:value={activeTab} class="w-full">
        <TabsList class="grid w-full grid-cols-3">
          <TabsTrigger value="settings">Settings</TabsTrigger>
          <TabsTrigger value="domains">Targets</TabsTrigger>
          <TabsTrigger value="danger">Danger Zone</TabsTrigger>
        </TabsList>

        <!-- Settings Tab -->
        <TabsContent value="settings" class="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Project Settings</CardTitle>
              <CardDescription>
                Configure general project settings and processing options.
              </CardDescription>
            </CardHeader>
            <CardContent class="space-y-6">
              <div class="grid gap-4 md:grid-cols-2">
                <div class="space-y-2">
                  <Label for="name">Project Name</Label>
                  <Input
                    id="name"
                    bind:value={projectForm.name}
                    placeholder="Enter project name"
                    required
                  />
                </div>
                
                <div class="space-y-2">
                  <Label for="description">Description</Label>
                  <Input
                    id="description"
                    bind:value={projectForm.description}
                    placeholder="Enter project description"
                  />
                </div>
              </div>

              <Separator />

              <div class="space-y-4">
                <h3 class="text-lg font-medium">Processing Options</h3>
                
                <div class="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="process_documents"
                    bind:checked={projectForm.process_documents}
                    class="rounded border-gray-300"
                  />
                  <Label for="process_documents">Enable document processing and indexing</Label>
                </div>

                <div class="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="enable_attachment_download"
                    bind:checked={projectForm.enable_attachment_download}
                    class="rounded border-gray-300"
                  />
                  <Label for="enable_attachment_download">Download and process attachments (PDFs, docs, etc.)</Label>
                </div>
              </div>

              <Separator />

              <div class="space-y-4">
                <h3 class="text-lg font-medium">Language Extraction</h3>
                
                <div class="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="langextract_enabled"
                    bind:checked={projectForm.langextract_enabled}
                    class="rounded border-gray-300"
                  />
                  <Label for="langextract_enabled">Enable LLM-powered language extraction</Label>
                </div>

                {#if projectForm.langextract_enabled}
                  <div class="grid gap-4 md:grid-cols-2 ml-6">
                    <div class="space-y-2">
                      <Label for="langextract_provider">Provider</Label>
                      <Select bind:value={projectForm.langextract_provider}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select provider" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="disabled">Disabled</SelectItem>
                          <SelectItem value="openrouter">OpenRouter</SelectItem>
                          <SelectItem value="openai">OpenAI</SelectItem>
                          <SelectItem value="anthropic">Anthropic</SelectItem>
                          <SelectItem value="ollama">Ollama</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div class="space-y-2">
                      <Label for="langextract_model">Model</Label>
                      <Input
                        id="langextract_model"
                        bind:value={projectForm.langextract_model}
                        placeholder="e.g., gpt-4, claude-3-sonnet"
                      />
                    </div>
                  </div>
                {/if}
              </div>

              <div class="flex justify-end pt-4">
                <Button onclick={updateProject} disabled={loading}>
                  <Save class="mr-2 h-4 w-4" />
                  {loading ? 'Saving...' : 'Save Changes'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <!-- Targets Tab -->
        <TabsContent value="domains" class="space-y-6">
          <!-- Add New Target -->
          <Card>
            <CardHeader>
              <CardTitle>Add Target</CardTitle>
              <CardDescription>
                Add a new target (domain or URL) to scrape for this project.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div class="grid gap-4 md:grid-cols-4">
                <div class="space-y-2">
                  <Label for="domain">Target</Label>
                  <Input
                    id="domain"
                    bind:value={newDomain.domain}
                    placeholder="example.com or https://example.com/path"
                    required
                  />
                </div>

                <div class="space-y-2">
                  <Label for="match_type">Match Type</Label>
                  <Select bind:value={newDomain.match_type}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="domain">Domain (full domain)</SelectItem>
                      <SelectItem value="exact">Exact</SelectItem>
                      <SelectItem value="prefix">Prefix</SelectItem>
                      <SelectItem value="regex">Regex</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div class="space-y-2">
                  <Label for="max_pages">Max Pages</Label>
                  <Input
                    id="max_pages"
                    type="number"
                    bind:value={newDomain.max_pages}
                    min="1"
                    max="100000"
                  />
                </div>

                <div class="flex items-end">
                  <Button onclick={addDomain} disabled={loading || !newDomain.domain}>
                    <Plus class="mr-2 h-4 w-4" />
                    Add Target
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          <!-- Existing Targets -->
          <Card>
            <CardHeader>
              <CardTitle>Configured Targets</CardTitle>
              <CardDescription>
                Manage existing targets for this project.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {#if domains.length === 0}
                <div class="text-center py-8">
                  <Globe class="h-12 w-12 text-muted-foreground mx-auto mb-3" />
                  <p class="text-muted-foreground">No targets configured yet.</p>
                </div>
              {:else}
                <div class="space-y-4">
                  {#each domains as domain}
                    <div class="flex items-center justify-between p-4 border rounded-lg">
                      <div class="flex items-center space-x-4">
                        <div>
                          <h3 class="font-medium">{domain.domain_name || domain.domain}</h3>
                          <div class="flex items-center gap-4 text-sm text-muted-foreground">
                            <span>Type: {domain.match_type}</span>
                            <span>Max: {domain.max_pages || 'Unlimited'} pages</span>
                            <span>Pages: {domain.scraped_pages || 0}/{domain.total_pages || 0}</span>
                          </div>
                        </div>
                      </div>
                      <div class="flex items-center gap-2">
                        <Badge variant={getDomainStatusColor(domain.status)}>
                          {domain.status || 'Active'}
                        </Badge>
                        <Button 
                          variant="ghost" 
                          size="sm"
                          onclick={() => deleteDomain(domain.id)}
                          disabled={loading}
                        >
                          <Trash2 class="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  {/each}
                </div>
              {/if}
            </CardContent>
          </Card>
        </TabsContent>

        <!-- Danger Zone Tab -->
        <TabsContent value="danger" class="space-y-6">
          <Card class="border-destructive">
            <CardHeader>
              <CardTitle class="text-destructive">Danger Zone</CardTitle>
              <CardDescription>
                Irreversible and destructive actions. Use with caution.
              </CardDescription>
            </CardHeader>
            <CardContent class="space-y-6">
              <div class="flex items-center justify-between p-4 border border-destructive rounded-lg">
                <div>
                  <h3 class="font-medium text-destructive">Delete Project</h3>
                  <p class="text-sm text-muted-foreground">
                    Permanently delete this project and all associated data including targets, pages, and scraping sessions.
                  </p>
                </div>
                <Button 
                  variant="destructive" 
                  onclick={() => showDeleteConfirm = true}
                  disabled={loading}
                >
                  <Trash2 class="mr-2 h-4 w-4" />
                  Delete Project
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    {/if}
  </div>
</DashboardLayout>

<!-- Delete Confirmation Modal -->
{#if showDeleteConfirm}
  <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
    <Card class="max-w-md mx-4">
      <CardHeader>
        <CardTitle class="text-destructive">Delete Project</CardTitle>
        <CardDescription>
          Are you absolutely sure you want to delete "{project?.name}"? This action cannot be undone.
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="flex items-center space-x-2 text-sm text-muted-foreground bg-yellow-50 p-3 rounded border border-yellow-200">
          <AlertTriangle class="h-4 w-4 text-yellow-600" />
          <span>This will permanently delete all domains, pages, and scraping data.</span>
        </div>
        
        {#if statusMessage}
          <div class="flex items-center space-x-2 text-sm text-blue-700 bg-blue-50 p-3 rounded border border-blue-200">
            <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-700"></div>
            <span>{statusMessage}</span>
          </div>
        {/if}
        
        <div class="flex justify-end space-x-2">
          <Button variant="outline" onclick={() => showDeleteConfirm = false} disabled={loading}>
            Cancel
          </Button>
          <Button variant="destructive" onclick={deleteProject} disabled={loading}>
            {loading ? 'Deleting...' : 'Delete Project'}
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
{/if}