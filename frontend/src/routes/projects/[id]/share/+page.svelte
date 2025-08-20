<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { isAuthenticated, auth } from '$lib/stores/auth';
  import { getApiUrl, apiFetch } from '$lib/utils';
  import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import { Input } from '$lib/components/ui/input';
  import { Label } from '$lib/components/ui/label';
  import { Badge } from '$lib/components/ui/badge';
  import { Switch } from '$lib/components/ui/switch';
  import { 
    ArrowLeft,
    Share,
    Copy,
    Mail,
    Users,
    Globe,
    Link,
    Eye,
    Settings,
    AlertTriangle
  } from 'lucide-svelte';

  let projectId: string = '';
  let project: any = null;
  let loading = false;
  let error = '';
  let success = '';
  
  let shareSettings = {
    public: false,
    allow_anonymous: false,
    require_approval: true,
    share_url: ''
  };
  
  let inviteEmail = '';
  let invites: any[] = [];

  $: projectId = ($page.params.id || '') as string;

  onMount(async () => {
    await auth.init();
    
    if (!$isAuthenticated) {
      goto(`/auth/login?redirect=/projects/${projectId}/share`);
      return;
    }
    
    await loadProject();
    await loadShareSettings();
    await loadInvites();
  });

  const loadProject = async () => {
    loading = true;
    try {
      const res = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}`));

      if (res.ok) {
        project = await res.json();
      } else if (res.status === 404) {
        error = 'Project not found.';
      } else if (res.status === 401) {
        error = 'You are not authorized to share this project.';
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

  const loadShareSettings = async () => {
    // Placeholder - sharing functionality not yet implemented in backend
    shareSettings.share_url = shareSettings.public ? 
      `${window.location.origin}/public/projects/${projectId}` : '';
  };

  const loadInvites = async () => {
    // Placeholder - sharing functionality not yet implemented in backend
    invites = [];
  };

  const updateShareSettings = async () => {
    loading = true;
    error = '';
    success = 'Share settings updated successfully! (Note: Sharing functionality is coming soon)';
    
    // Update URL if public
    if (shareSettings.public) {
      shareSettings.share_url = `${window.location.origin}/public/projects/${projectId}`;
    } else {
      shareSettings.share_url = '';
    }
    
    loading = false;
  };

  const sendInvite = async () => {
    if (!inviteEmail) {
      error = 'Email address is required.';
      return;
    }

    loading = true;
    error = '';
    success = `Invitation would be sent to ${inviteEmail} (feature coming soon!)`;
    inviteEmail = '';
    loading = false;
  };

  const copyShareUrl = async () => {
    if (shareSettings.share_url) {
      try {
        await navigator.clipboard.writeText(shareSettings.share_url);
        success = 'Share URL copied to clipboard!';
      } catch (e) {
        error = 'Failed to copy URL to clipboard.';
      }
    }
  };

  const revokeInvite = async (inviteId: string) => {
    if (!confirm('Are you sure you want to revoke this invitation?')) {
      return;
    }

    loading = true;
    error = '';

    try {
      const res = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}/invites/${inviteId}`), {
        method: 'DELETE'
      });

      if (res.ok) {
        await loadInvites();
        success = 'Invitation revoked successfully!';
      } else {
        const errorData = await res.json().catch(() => ({}));
        error = errorData.detail || 'Failed to revoke invitation.';
      }
    } catch (e) {
      console.error('Failed to revoke invite:', e);
      error = 'Network error while revoking invitation.';
    } finally {
      loading = false;
    }
  };

  const getInviteStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'pending': return 'secondary';
      case 'accepted': return 'default';
      case 'expired': return 'outline';
      case 'revoked': return 'destructive';
      default: return 'secondary';
    }
  };
</script>

<svelte:head>
  <title>Share {project?.name || 'Project'} - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
  <div class="space-y-6">
    {#if loading && !project}
      <!-- Loading skeleton -->
      <div class="animate-pulse">
        <div class="h-8 bg-gray-200 rounded w-1/3 mb-2"></div>
        <div class="h-4 bg-gray-200 rounded w-1/2"></div>
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
            <Button variant="ghost" size="sm" on:click={() => goto(`/projects/${projectId}`)}>
              <ArrowLeft class="h-4 w-4" />
            </Button>
            <h2 class="text-3xl font-bold tracking-tight">Share Project</h2>
          </div>
          <p class="text-muted-foreground">
            Configure sharing settings for "{project.name}"
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

      <!-- Public Sharing -->
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Globe class="h-5 w-5" />
            Public Sharing
          </CardTitle>
          <CardDescription>
            Make this project publicly accessible with a shareable link.
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-6">
          <div class="flex items-center justify-between">
            <div class="space-y-1">
              <Label>Enable public access</Label>
              <p class="text-sm text-muted-foreground">
                Anyone with the link can view this project
              </p>
            </div>
            <Switch bind:checked={shareSettings.public} on:change={updateShareSettings} />
          </div>

          {#if shareSettings.public}
            <div class="space-y-4 p-4 bg-muted/50 rounded-lg">
              <div class="flex items-center justify-between">
                <div class="space-y-1">
                  <Label>Allow anonymous viewing</Label>
                  <p class="text-sm text-muted-foreground">
                    Visitors don't need to sign in
                  </p>
                </div>
                <Switch bind:checked={shareSettings.allow_anonymous} on:change={updateShareSettings} />
              </div>

              <div class="flex items-center justify-between">
                <div class="space-y-1">
                  <Label>Require approval</Label>
                  <p class="text-sm text-muted-foreground">
                    You must approve access requests
                  </p>
                </div>
                <Switch bind:checked={shareSettings.require_approval} on:change={updateShareSettings} />
              </div>

              {#if shareSettings.share_url}
                <div class="space-y-2">
                  <Label>Share URL</Label>
                  <div class="flex gap-2">
                    <Input 
                      value={shareSettings.share_url} 
                      readonly 
                      class="flex-1"
                    />
                    <Button size="sm" on:click={copyShareUrl}>
                      <Copy class="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              {/if}
            </div>
          {/if}
        </CardContent>
      </Card>

      <!-- Invite Users -->
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Users class="h-5 w-5" />
            Invite Users
          </CardTitle>
          <CardDescription>
            Send invitations to specific users to collaborate on this project.
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-6">
          <div class="flex gap-2">
            <Input
              bind:value={inviteEmail}
              placeholder="Enter email address"
              type="email"
              class="flex-1"
            />
            <Button on:click={sendInvite} disabled={loading || !inviteEmail}>
              <Mail class="mr-2 h-4 w-4" />
              Send Invite
            </Button>
          </div>

          {#if invites.length > 0}
            <div class="space-y-3">
              <h4 class="font-medium">Pending Invitations</h4>
              {#each invites as invite}
                <div class="flex items-center justify-between p-3 border rounded-lg">
                  <div>
                    <p class="font-medium">{invite.email}</p>
                    <p class="text-sm text-muted-foreground">
                      Invited {new Date(invite.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div class="flex items-center gap-2">
                    <Badge variant={getInviteStatusColor(invite.status)}>
                      {invite.status}
                    </Badge>
                    {#if invite.status === 'pending'}
                      <Button 
                        variant="ghost" 
                        size="sm"
                        on:click={() => revokeInvite(invite.id)}
                      >
                        Revoke
                      </Button>
                    {/if}
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </CardContent>
      </Card>

      <!-- Access Management -->
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Settings class="h-5 w-5" />
            Access Control
          </CardTitle>
          <CardDescription>
            Configure what shared users can see and do.
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="grid gap-4 md:grid-cols-2">
            <div class="flex items-center space-x-2">
              <input type="checkbox" id="view_pages" class="rounded border-gray-300" checked disabled />
              <Label for="view_pages">View pages and content</Label>
            </div>
            
            <div class="flex items-center space-x-2">
              <input type="checkbox" id="view_stats" class="rounded border-gray-300" checked disabled />
              <Label for="view_stats">View project statistics</Label>
            </div>
            
            <div class="flex items-center space-x-2">
              <input type="checkbox" id="search" class="rounded border-gray-300" checked disabled />
              <Label for="search">Search and filter content</Label>
            </div>
            
            <div class="flex items-center space-x-2">
              <input type="checkbox" id="export" class="rounded border-gray-300" disabled />
              <Label for="export">Export data (Premium)</Label>
            </div>
          </div>
          
          <p class="text-sm text-muted-foreground">
            Shared users can view project content but cannot modify settings or start new scraping sessions.
          </p>
        </CardContent>
      </Card>
    {/if}
  </div>
</DashboardLayout>