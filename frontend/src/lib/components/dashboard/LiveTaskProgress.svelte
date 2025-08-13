<script lang="ts">
  import { Badge } from '$lib/components/ui/badge';
  import { Button } from '$lib/components/ui/button';
  import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Progress } from '$lib/components/ui/progress';
  import { Separator } from '$lib/components/ui/separator';
  import { activeTasks, completedTasks, activeTasksCount } from '$lib/stores/projectProgress';
  import { connectionState, isConnected, ConnectionState } from '$lib/stores/websocket';
  import { 
    Play, 
    Pause, 
    CheckCircle, 
    XCircle, 
    Clock, 
    Loader2,
    Wifi,
    WifiOff,
    RefreshCw
  } from 'lucide-svelte';
  import { onMount } from 'svelte';

  export let showCompleted = true;
  export let maxItems = 10;
  export let compact = false;

  let showConnectionStatus = true;
  
  function getStatusIcon(status: string) {
    switch (status) {
      case 'running': return Loader2;
      case 'completed': return CheckCircle;
      case 'failed': return XCircle;
      case 'pending': return Clock;
      default: return Play;
    }
  }

  function getStatusColor(status: string) {
    switch (status) {
      case 'running': return 'text-blue-500';
      case 'completed': return 'text-green-500';
      case 'failed': return 'text-red-500';
      case 'pending': return 'text-yellow-500';
      default: return 'text-gray-500';
    }
  }

  function getStatusBadgeVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
    switch (status) {
      case 'running': return 'default';
      case 'completed': return 'secondary';
      case 'failed': return 'destructive';
      case 'pending': return 'outline';
      default: return 'outline';
    }
  }

  function formatDuration(timestamp: string) {
    const diff = Date.now() - new Date(timestamp).getTime();
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) return `${hours}h ${minutes % 60}m`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    return `${seconds}s`;
  }

  function getConnectionStatusColor(state: ConnectionState) {
    switch (state) {
      case ConnectionState.CONNECTED: return 'text-green-500';
      case ConnectionState.CONNECTING:
      case ConnectionState.RECONNECTING: return 'text-yellow-500';
      case ConnectionState.ERROR:
      case ConnectionState.DISCONNECTED: return 'text-red-500';
      default: return 'text-gray-500';
    }
  }

  function getConnectionStatusText(state: ConnectionState) {
    switch (state) {
      case ConnectionState.CONNECTED: return 'Connected';
      case ConnectionState.CONNECTING: return 'Connecting...';
      case ConnectionState.RECONNECTING: return 'Reconnecting...';
      case ConnectionState.ERROR: return 'Connection Error';
      case ConnectionState.DISCONNECTED: return 'Disconnected';
      default: return 'Unknown';
    }
  }

  onMount(() => {
    // Auto-hide connection status after 5 seconds if connected
    const timer = setTimeout(() => {
      if ($isConnected) {
        showConnectionStatus = false;
      }
    }, 5000);
    
    return () => clearTimeout(timer);
  });

  // Show connection status when disconnected
  $: if (!$isConnected) {
    showConnectionStatus = true;
  }

  $: combinedTasks = [
    ...$activeTasks.map(task => ({ ...task, category: 'active' })),
    ...(showCompleted ? $completedTasks.slice(0, 5).map(task => ({ ...task, category: 'completed' })) : [])
  ].slice(0, maxItems);
</script>

<!-- Connection Status -->
{#if showConnectionStatus}
  <Card class="mb-4 border-l-4 {$isConnected ? 'border-l-green-500' : 'border-l-red-500'}">
    <CardContent class="flex items-center justify-between p-4">
      <div class="flex items-center gap-2">
        {#if $isConnected}
          <Wifi class="h-4 w-4 text-green-500" />
        {:else}
          <WifiOff class="h-4 w-4 text-red-500" />
        {/if}
        <span class="text-sm font-medium {getConnectionStatusColor($connectionState)}">
          {getConnectionStatusText($connectionState)}
        </span>
        {#if $connectionState === ConnectionState.RECONNECTING}
          <Loader2 class="h-3 w-3 animate-spin text-yellow-500" />
        {/if}
      </div>
      
      {#if $isConnected}
        <Button
          variant="ghost"
          size="sm"
          on:click={() => showConnectionStatus = false}
          class="text-xs"
        >
          Hide
        </Button>
      {/if}
    </CardContent>
  </Card>
{/if}

<!-- Task Progress -->
<Card>
  <CardHeader class="pb-2">
    <CardTitle class="flex items-center justify-between text-lg">
      <span>Live Task Progress</span>
      <div class="flex items-center gap-2">
        {#if $activeTasksCount > 0}
          <Badge variant="default" class="bg-blue-500">
            {$activeTasksCount} active
          </Badge>
        {/if}
        {#if !$isConnected}
          <Badge variant="destructive">
            Offline
          </Badge>
        {/if}
      </div>
    </CardTitle>
  </CardHeader>

  <CardContent class="space-y-4">
    {#if combinedTasks.length === 0}
      <div class="flex flex-col items-center justify-center py-8 text-center">
        <Clock class="h-8 w-8 text-gray-400 mb-2" />
        <p class="text-sm text-gray-500">No active tasks</p>
        <p class="text-xs text-gray-400 mt-1">Tasks will appear here when they start running</p>
      </div>
    {:else}
      <div class="space-y-3">
        {#each combinedTasks as task (task.id)}
          <div class="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 space-y-2">
            <!-- Task Header -->
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                {#if task.status === 'running'}
                  <Loader2 class="h-4 w-4 animate-spin {getStatusColor(task.status)}" />
                {:else}
                  <svelte:component this={getStatusIcon(task.status)} class="h-4 w-4 {getStatusColor(task.status)}" />
                {/if}
                <span class="text-sm font-medium truncate">
                  {task.message || 'Processing...'}
                </span>
              </div>
              
              <div class="flex items-center gap-2">
                <Badge variant={getStatusBadgeVariant(task.status)} class="text-xs">
                  {task.status}
                </Badge>
                {#if task.category === 'active'}
                  <span class="text-xs text-gray-500">
                    {formatDuration(task.updated_at)}
                  </span>
                {/if}
              </div>
            </div>

            <!-- Progress Bar -->
            {#if task.status === 'running' || task.status === 'pending'}
              <div class="space-y-1">
                <Progress value={task.progress} class="h-2" />
                <div class="flex justify-between text-xs text-gray-500">
                  <span>{Math.round(task.progress)}%</span>
                  {#if task.details?.current && task.details?.total}
                    <span>{task.details.current} / {task.details.total}</span>
                  {/if}
                </div>
              </div>
            {/if}

            <!-- Task Details -->
            {#if task.details && !compact}
              <div class="text-xs text-gray-600 dark:text-gray-400">
                {#if task.details.domain_name}
                  <span class="font-medium">Domain:</span> {task.details.domain_name}
                {/if}
                {#if task.details.snapshots_found}
                  <span class="ml-4">
                    <span class="font-medium">Found:</span> {task.details.snapshots_found} pages
                  </span>
                {/if}
              </div>
            {/if}

            <!-- Error Message -->
            {#if task.status === 'failed' && task.error}
              <div class="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-2 rounded">
                <strong>Error:</strong> {task.error}
              </div>
            {/if}

            <!-- Project Link -->
            {#if task.project_id && !compact}
              <div class="flex justify-end">
                <Button 
                  variant="ghost" 
                  size="sm" 
                  class="text-xs h-6 px-2"
                  on:click={() => window.location.href = `/projects/${task.project_id}`}
                >
                  View Project
                </Button>
              </div>
            {/if}
          </div>

          {#if task.category === 'active' && showCompleted}
            <Separator class="my-2" />
          {/if}
        {/each}
      </div>
    {/if}

    <!-- Footer Actions -->
    {#if !compact && ($activeTasks.length > 0 || $completedTasks.length > 0)}
      <div class="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
        <div class="text-xs text-gray-500">
          {$activeTasks.length} active • {$completedTasks.length} completed
        </div>
        
        <div class="flex gap-2">
          {#if showCompleted && $completedTasks.length > 5}
            <Button variant="ghost" size="sm" class="text-xs">
              View All
            </Button>
          {/if}
          
          <Button 
            variant="ghost" 
            size="sm" 
            class="text-xs"
            on:click={() => showCompleted = !showCompleted}
          >
            {showCompleted ? 'Hide' : 'Show'} Completed
          </Button>
        </div>
      </div>
    {/if}
  </CardContent>
</Card>

<style>
  :global(.animate-spin) {
    animation: spin 1s linear infinite;
  }
  
  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
</style>