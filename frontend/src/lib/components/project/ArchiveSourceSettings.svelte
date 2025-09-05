<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import { Alert, AlertDescription } from '$lib/components/ui/alert';
  import { Skeleton } from '$lib/components/ui/skeleton';
  import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '$lib/components/ui/sheet';
  import { 
    Archive, 
    Settings, 
    AlertTriangle, 
    CheckCircle, 
    Info,
    Activity,
    TrendingUp,
    Clock,
    Shield
  } from 'lucide-svelte';
  import ArchiveSourceBadge from './ArchiveSourceBadge.svelte';
  import ArchiveSourceManager from './ArchiveSourceManager.svelte';
  import { getApiUrl, apiFetch } from '$lib/utils';
  import type { 
    ArchiveSource, 
    ArchiveConfig, 
    ArchiveSourceMetrics,
    ArchiveSourceStats
  } from '$lib/types/scraping';
  
  const dispatch = createEventDispatcher<{
    configurationChanged: { 
      archiveSource: ArchiveSource; 
      fallbackEnabled: boolean; 
      archiveConfig: ArchiveConfig 
    };
  }>();
  
  export let projectId: number;
  export let archiveSource: ArchiveSource = 'wayback';
  export let fallbackEnabled: boolean = true;
  export let archiveConfig: ArchiveConfig = {};
  export let canEdit: boolean = true;
  
  // Local state
  let loading = false;
  let error = '';
  let success = '';
  let showManager = false;
  let metrics: Record<ArchiveSource, ArchiveSourceMetrics> | undefined = undefined;
  let stats: ArchiveSourceStats | undefined = undefined;
  let testResults: Record<string, 'testing' | 'success' | 'failure'> = {};
  
  onMount(() => {
    loadArchiveSourceMetrics();
  });
  
  async function loadArchiveSourceMetrics() {
    loading = true;
    error = '';
    
    try {
      const response = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}/archive-source/metrics`));
      
      if (response.ok) {
        const data = await response.json();
        metrics = data.metrics;
        stats = data.stats;
      } else {
        // Metrics not available - this is okay, just show without metrics
        console.log('Archive source metrics not available');
      }
    } catch (e) {
      console.warn('Failed to load archive source metrics:', e);
      // Non-critical error - continue without metrics
    } finally {
      loading = false;
    }
  }
  
  async function handleSaveConfiguration(event: CustomEvent) {
    const { archiveSource: newSource, fallbackEnabled: newFallback, archiveConfig: newConfig } = event.detail;
    
    loading = true;
    error = '';
    success = '';
    
    try {
      const response = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}/archive-source`), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          archive_source: newSource,
          fallback_enabled: newFallback,
          archive_config: newConfig
        })
      });
      
      if (response.ok) {
        archiveSource = newSource;
        fallbackEnabled = newFallback;
        archiveConfig = newConfig;
        
        success = 'Archive source configuration saved successfully';
        showManager = false;
        
        // Reload metrics to reflect changes
        await loadArchiveSourceMetrics();
        
        dispatch('configurationChanged', {
          archiveSource: newSource,
          fallbackEnabled: newFallback,
          archiveConfig: newConfig
        });
        
        // Clear success message after 3 seconds
        setTimeout(() => {
          success = '';
        }, 3000);
      } else {
        const errorData = await response.json();
        error = errorData.detail || 'Failed to save archive source configuration';
      }
    } catch (e) {
      error = 'Network error while saving configuration';
    } finally {
      loading = false;
    }
  }
  
  async function handleTestConnection(event: CustomEvent) {
    const { source } = event.detail;
    testResults = { ...testResults, [source]: 'testing' };
    
    try {
      const response = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}/archive-source/test`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ source })
      });
      
      if (response.ok) {
        testResults = { ...testResults, [source]: 'success' };
      } else {
        testResults = { ...testResults, [source]: 'failure' };
      }
    } catch (e) {
      testResults = { ...testResults, [source]: 'failure' };
    }
    
    // Clear test result after 5 seconds
    setTimeout(() => {
      const { [source]: _, ...rest } = testResults;
      testResults = rest;
    }, 5000);
  }
  
  function getPerformanceColor(rate: number): string {
    if (rate >= 95) return 'text-green-600 dark:text-green-400';
    if (rate >= 85) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-600 dark:text-red-400';
  }
  
  function getCircuitBreakerStatus(status: string): { color: string; label: string } {
    switch (status) {
      case 'closed':
        return { color: 'text-green-500', label: 'Healthy' };
      case 'open':
        return { color: 'text-red-500', label: 'Circuit Open' };
      case 'half_open':
        return { color: 'text-yellow-500', label: 'Testing' };
      default:
        return { color: 'text-gray-500', label: 'Unknown' };
    }
  }
</script>

<!-- Archive Source Settings Panel -->
<Card class="relative">
  <CardHeader>
    <div class="flex items-center justify-between">
      <div>
        <CardTitle class="flex items-center gap-2">
          <Archive class="h-4 w-4" />
          Archive Source Configuration
        </CardTitle>
        <CardDescription>
          Control how your project accesses archived web content
        </CardDescription>
      </div>
      
      {#if canEdit}
        <Sheet bind:open={showManager}>
          <SheetTrigger asChild>
            <Button variant="outline" size="sm">
              <Settings class="mr-1 h-3 w-3" />
              Configure
            </Button>
          </SheetTrigger>
          <SheetContent class="w-[600px] sm:w-[800px] max-w-[90vw] overflow-y-auto">
            <SheetHeader>
              <SheetTitle>Archive Source Settings</SheetTitle>
              <SheetDescription>
                Configure how your project accesses archived web content for optimal performance and reliability.
              </SheetDescription>
            </SheetHeader>
            <div class="mt-6">
              <ArchiveSourceManager
                {projectId}
                currentArchiveSource={archiveSource}
                currentFallbackEnabled={fallbackEnabled}
                currentArchiveConfig={archiveConfig}
                {metrics}
                on:save={handleSaveConfiguration}
                on:cancel={() => showManager = false}
                on:test={handleTestConnection}
              />
            </div>
          </SheetContent>
        </Sheet>
      {/if}
    </div>
  </CardHeader>
  
  <CardContent class="space-y-4">
    <!-- Status Messages -->
    {#if success}
      <Alert class="border-green-200 bg-green-50 dark:bg-green-950/20">
        <CheckCircle class="h-4 w-4 text-green-600" />
        <AlertDescription class="text-green-800 dark:text-green-200">
          {success}
        </AlertDescription>
      </Alert>
    {/if}
    
    {#if error}
      <Alert class="border-destructive">
        <AlertTriangle class="h-4 w-4" />
        <AlertDescription>
          {error}
        </AlertDescription>
      </Alert>
    {/if}
    
    {#if loading}
      <!-- Loading State -->
      <div class="space-y-3">
        <Skeleton class="h-8 w-48" />
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Skeleton class="h-20 w-full" />
          <Skeleton class="h-20 w-full" />
        </div>
      </div>
    {:else}
      <!-- Current Configuration -->
      <div class="space-y-4">
        <div class="flex flex-col sm:flex-row sm:items-center gap-3">
          <span class="font-medium text-sm">Current Source:</span>
          <ArchiveSourceBadge 
            {archiveSource}
            {fallbackEnabled}
            metrics={metrics?.[archiveSource]}
            size="md"
            showTooltip={true}
          />
        </div>
        
        {#if metrics}
          <!-- Performance Metrics -->
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {#each Object.entries(metrics) as [source, sourceMetrics]}
              {@const cbStatus = getCircuitBreakerStatus(sourceMetrics.circuit_breaker_status)}
              <Card class="bg-muted/20">
                <CardContent class="p-4">
                  <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center gap-2">
                      {#if source === 'wayback'}
                        <Archive class="h-3 w-3 text-blue-500" />
                        <span class="text-sm font-medium">Wayback</span>
                      {:else if source === 'commoncrawl'}
                        <Globe class="h-3 w-3 text-green-500" />
                        <span class="text-sm font-medium">CommonCrawl</span>
                      {:else if source === 'hybrid'}
                        <Zap class="h-3 w-3 text-purple-500" />
                        <span class="text-sm font-medium">Hybrid</span>
                      {/if}
                    </div>
                    <div class="flex items-center gap-1">
                      <div class="w-2 h-2 rounded-full {cbStatus.color.replace('text-', 'bg-')}"></div>
                    </div>
                  </div>
                  
                  <div class="space-y-2 text-xs">
                    <div class="flex justify-between">
                      <span class="text-muted-foreground">Success Rate</span>
                      <span class="{getPerformanceColor(sourceMetrics.success_rate)} font-mono">
                        {sourceMetrics.success_rate.toFixed(1)}%
                      </span>
                    </div>
                    <div class="flex justify-between">
                      <span class="text-muted-foreground">Avg Response</span>
                      <span class="font-mono">{sourceMetrics.avg_response_time_ms}ms</span>
                    </div>
                    <div class="flex justify-between">
                      <span class="text-muted-foreground">Requests</span>
                      <span class="font-mono">{sourceMetrics.total_requests.toLocaleString()}</span>
                    </div>
                    <div class="flex justify-between">
                      <span class="text-muted-foreground">Status</span>
                      <span class="{cbStatus.color} text-xs">{cbStatus.label}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            {/each}
          </div>
        {/if}
        
        <!-- Configuration Summary -->
        <div class="bg-muted/30 p-4 rounded-lg">
          <div class="flex items-start gap-2">
            <Info class="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
            <div class="space-y-2 text-sm">
              <p class="font-medium">Configuration Summary</p>
              <div class="space-y-1 text-muted-foreground">
                <p>• Archive Source: <span class="font-medium text-foreground">{archiveSource}</span></p>
                {#if archiveSource === 'hybrid'}
                  <p>• Fallback: <span class="font-medium text-foreground">{fallbackEnabled ? 'Enabled' : 'Disabled'}</span></p>
                  {#if fallbackEnabled && archiveConfig.fallback_delay_seconds}
                    <p>• Fallback Delay: <span class="font-medium text-foreground">{archiveConfig.fallback_delay_seconds}s</span></p>
                  {/if}
                {/if}
                {#if archiveConfig.concurrent_requests}
                  <p>• Concurrent Requests: <span class="font-medium text-foreground">{archiveConfig.concurrent_requests}</span></p>
                {/if}
                {#if archiveConfig.request_timeout_seconds}
                  <p>• Request Timeout: <span class="font-medium text-foreground">{archiveConfig.request_timeout_seconds}s</span></p>
                {/if}
              </div>
            </div>
          </div>
        </div>
        
        {#if stats && (stats.hybrid_fallbacks > 0 || Object.values(stats.preferred_source_usage).some(count => count > 0))}
          <!-- Usage Statistics -->
          <div class="space-y-3">
            <div class="flex items-center gap-2">
              <TrendingUp class="h-4 w-4 text-blue-500" />
              <span class="font-medium text-sm">Usage Statistics</span>
            </div>
            
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              {#if stats.hybrid_fallbacks > 0}
                <div class="flex justify-between items-center p-3 bg-purple-50 dark:bg-purple-950/20 rounded border border-purple-200 dark:border-purple-800">
                  <span class="text-purple-700 dark:text-purple-300">Hybrid Fallbacks</span>
                  <span class="font-mono font-medium text-purple-800 dark:text-purple-200">{stats.hybrid_fallbacks}</span>
                </div>
              {/if}
              
              {#each Object.entries(stats.preferred_source_usage) as [source, count]}
                {#if count > 0}
                  <div class="flex justify-between items-center p-3 bg-muted/50 rounded border border-border">
                    <span class="capitalize">{source} Usage</span>
                    <span class="font-mono font-medium">{count.toLocaleString()}</span>
                  </div>
                {/if}
              {/each}
            </div>
          </div>
        {/if}
      </div>
    {/if}
  </CardContent>
  
  <!-- Loading Overlay -->
  {#if loading}
    <div class="absolute inset-0 bg-background/50 backdrop-blur-sm flex items-center justify-center rounded-lg">
      <div class="flex items-center gap-2">
        <Activity class="h-4 w-4 animate-spin" />
        <span class="text-sm">Loading...</span>
      </div>
    </div>
  {/if}
</Card>