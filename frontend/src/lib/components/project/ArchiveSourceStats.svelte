<script lang="ts">
  import { onMount } from 'svelte';
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Badge } from '$lib/components/ui/badge';
  import { Skeleton } from '$lib/components/ui/skeleton';
  import { Alert, AlertDescription } from '$lib/components/ui/alert';
  import { 
    Archive, 
    Globe, 
    Zap, 
    TrendingUp, 
    Clock, 
    Shield,
    Activity,
    AlertTriangle,
    CheckCircle,
    Info
  } from 'lucide-svelte';
  import ArchiveSourceBadge from './ArchiveSourceBadge.svelte';
  import { getApiUrl, apiFetch } from '$lib/utils';
  import type { 
    ArchiveSourceStats,
    ArchiveSourceMetrics
  } from '$lib/types/scraping';
  
  export let projectId: number;
  export let className: string = '';
  
  let loading = false;
  let error = '';
  let stats: ArchiveSourceStats | undefined = undefined;
  let refreshInterval: NodeJS.Timeout | null = null;
  
  onMount(async () => {
    await loadStats();
    
    // Auto-refresh every 30 seconds
    refreshInterval = setInterval(loadStats, 30000);
    
    // Cleanup on destroy
    return () => {
      if (refreshInterval) {
        clearInterval(refreshInterval);
      }
    };
  });
  
  async function loadStats() {
    if (loading) return; // Prevent concurrent requests
    
    loading = true;
    error = '';
    
    try {
      const response = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}/archive-source/stats`));
      
      if (response.ok) {
        stats = await response.json();
      } else {
        // Stats may not be available for all projects
        error = 'Archive source statistics not available';
      }
    } catch (e) {
      console.warn('Failed to load archive source statistics:', e);
      error = 'Failed to load statistics';
    } finally {
      loading = false;
    }
  }
  
  function getPerformanceColor(rate: number): string {
    if (rate >= 95) return 'text-green-600 dark:text-green-400';
    if (rate >= 85) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-600 dark:text-red-400';
  }
  
  function getCircuitBreakerColor(status: string): string {
    switch (status) {
      case 'closed': return 'bg-green-500';
      case 'open': return 'bg-red-500';
      case 'half_open': return 'bg-yellow-500';
      default: return 'bg-gray-500';
    }
  }
  
  function getCircuitBreakerLabel(status: string): string {
    switch (status) {
      case 'closed': return 'Healthy';
      case 'open': return 'Circuit Open';
      case 'half_open': return 'Testing';
      default: return 'Unknown';
    }
  }
  
  // Calculate total usage across all sources
  $: totalUsage = stats ? Object.values(stats.preferred_source_usage).reduce((sum, count) => sum + count, 0) : 0;
</script>

<div class={className}>
  {#if error && !stats}
    <Alert class="border-amber-200 bg-amber-50 dark:bg-amber-950/20">
      <Info class="h-4 w-4 text-amber-600" />
      <AlertDescription class="text-amber-800 dark:text-amber-200">
        {error}
      </AlertDescription>
    </Alert>
  {:else}
    <Card>
      <CardHeader>
        <CardTitle class="flex items-center gap-2">
          <TrendingUp class="h-4 w-4" />
          Archive Source Performance
          {#if loading}
            <Activity class="h-3 w-3 animate-spin text-muted-foreground" />
          {/if}
        </CardTitle>
        <CardDescription>
          Real-time performance metrics and usage statistics for archive sources
        </CardDescription>
      </CardHeader>
      <CardContent>
        {#if loading && !stats}
          <!-- Loading State -->
          <div class="space-y-4">
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {#each Array(3) as _}
                <Card>
                  <CardContent class="p-4">
                    <div class="space-y-2">
                      <Skeleton class="h-4 w-20" />
                      <Skeleton class="h-6 w-12" />
                      <Skeleton class="h-3 w-16" />
                    </div>
                  </CardContent>
                </Card>
              {/each}
            </div>
          </div>
        {:else if stats}
          <div class="space-y-6">
            <!-- Archive Source Metrics Grid -->
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <!-- Wayback Machine -->
              {#if stats.wayback_machine}
                <Card class="bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800">
                  <CardContent class="p-4">
                    <div class="flex items-center justify-between mb-3">
                      <div class="flex items-center gap-2">
                        <Archive class="h-4 w-4 text-blue-600 dark:text-blue-400" />
                        <span class="font-medium text-blue-800 dark:text-blue-200">Wayback Machine</span>
                      </div>
                      <div class="w-2 h-2 rounded-full {getCircuitBreakerColor(stats.wayback_machine.circuit_breaker_status)}"></div>
                    </div>
                    <div class="space-y-2 text-sm">
                      <div class="flex justify-between">
                        <span class="text-muted-foreground">Success Rate</span>
                        <span class="{getPerformanceColor(stats.wayback_machine.success_rate)} font-mono">
                          {stats.wayback_machine.success_rate.toFixed(1)}%
                        </span>
                      </div>
                      <div class="flex justify-between">
                        <span class="text-muted-foreground">Avg Response</span>
                        <span class="font-mono">{stats.wayback_machine.avg_response_time_ms}ms</span>
                      </div>
                      <div class="flex justify-between">
                        <span class="text-muted-foreground">Total Requests</span>
                        <span class="font-mono">{stats.wayback_machine.total_requests.toLocaleString()}</span>
                      </div>
                      <div class="flex justify-between">
                        <span class="text-muted-foreground">Status</span>
                        <span class="text-xs">{getCircuitBreakerLabel(stats.wayback_machine.circuit_breaker_status)}</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              {/if}
              
              <!-- Common Crawl -->
              {#if stats.commoncrawl}
                <Card class="bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800">
                  <CardContent class="p-4">
                    <div class="flex items-center justify-between mb-3">
                      <div class="flex items-center gap-2">
                        <Globe class="h-4 w-4 text-green-600 dark:text-green-400" />
                        <span class="font-medium text-green-800 dark:text-green-200">Common Crawl</span>
                      </div>
                      <div class="w-2 h-2 rounded-full {getCircuitBreakerColor(stats.commoncrawl.circuit_breaker_status)}"></div>
                    </div>
                    <div class="space-y-2 text-sm">
                      <div class="flex justify-between">
                        <span class="text-muted-foreground">Success Rate</span>
                        <span class="{getPerformanceColor(stats.commoncrawl.success_rate)} font-mono">
                          {stats.commoncrawl.success_rate.toFixed(1)}%
                        </span>
                      </div>
                      <div class="flex justify-between">
                        <span class="text-muted-foreground">Avg Response</span>
                        <span class="font-mono">{stats.commoncrawl.avg_response_time_ms}ms</span>
                      </div>
                      <div class="flex justify-between">
                        <span class="text-muted-foreground">Total Requests</span>
                        <span class="font-mono">{stats.commoncrawl.total_requests.toLocaleString()}</span>
                      </div>
                      <div class="flex justify-between">
                        <span class="text-muted-foreground">Status</span>
                        <span class="text-xs">{getCircuitBreakerLabel(stats.commoncrawl.circuit_breaker_status)}</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              {/if}
              
              <!-- Hybrid Fallbacks -->
              {#if stats.hybrid_fallbacks > 0}
                <Card class="bg-purple-50 dark:bg-purple-950/20 border-purple-200 dark:border-purple-800">
                  <CardContent class="p-4">
                    <div class="flex items-center gap-2 mb-3">
                      <Zap class="h-4 w-4 text-purple-600 dark:text-purple-400" />
                      <span class="font-medium text-purple-800 dark:text-purple-200">Hybrid Fallbacks</span>
                    </div>
                    <div class="text-center">
                      <div class="text-2xl font-bold text-purple-700 dark:text-purple-300 mb-1">
                        {stats.hybrid_fallbacks.toLocaleString()}
                      </div>
                      <p class="text-xs text-purple-600 dark:text-purple-400">
                        Automatic source switches
                      </p>
                    </div>
                  </CardContent>
                </Card>
              {/if}
            </div>
            
            <!-- Usage Distribution -->
            {#if totalUsage > 0}
              <div class="space-y-3">
                <h4 class="text-sm font-medium flex items-center gap-2">
                  <Activity class="h-3 w-3" />
                  Usage Distribution
                </h4>
                <div class="space-y-2">
                  {#each Object.entries(stats.preferred_source_usage) as [source, count]}
                    {#if count > 0}
                      {@const percentage = (count / totalUsage) * 100}
                      <div class="flex items-center gap-3">
                        <div class="w-16 text-xs text-muted-foreground capitalize">
                          {source}
                        </div>
                        <div class="flex-1 bg-muted rounded-full h-2">
                          <div 
                            class="h-2 rounded-full {source === 'wayback' ? 'bg-blue-500' : source === 'commoncrawl' ? 'bg-green-500' : 'bg-purple-500'}"
                            style="width: {percentage}%"
                          ></div>
                        </div>
                        <div class="text-xs font-mono text-muted-foreground w-12 text-right">
                          {percentage.toFixed(1)}%
                        </div>
                        <div class="text-xs font-mono text-muted-foreground w-16 text-right">
                          {count.toLocaleString()}
                        </div>
                      </div>
                    {/if}
                  {/each}
                </div>
              </div>
            {/if}
            
            <!-- Performance Recommendations -->
            {#if stats.wayback_machine || stats.commoncrawl}
              <div class="space-y-2">
                <h4 class="text-sm font-medium flex items-center gap-2">
                  <Shield class="h-3 w-3" />
                  System Health
                </h4>
                <div class="flex flex-wrap gap-2 text-xs">
                  {#if stats.wayback_machine && stats.wayback_machine.circuit_breaker_status === 'closed'}
                    <Badge variant="secondary" class="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                      <CheckCircle class="mr-1 h-2 w-2" />
                      Wayback Healthy
                    </Badge>
                  {:else if stats.wayback_machine && stats.wayback_machine.circuit_breaker_status !== 'closed'}
                    <Badge variant="destructive" class="bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                      <AlertTriangle class="mr-1 h-2 w-2" />
                      Wayback Issues
                    </Badge>
                  {/if}
                  
                  {#if stats.commoncrawl && stats.commoncrawl.circuit_breaker_status === 'closed'}
                    <Badge variant="secondary" class="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                      <CheckCircle class="mr-1 h-2 w-2" />
                      CommonCrawl Healthy
                    </Badge>
                  {:else if stats.commoncrawl && stats.commoncrawl.circuit_breaker_status !== 'closed'}
                    <Badge variant="destructive" class="bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                      <AlertTriangle class="mr-1 h-2 w-2" />
                      CommonCrawl Issues
                    </Badge>
                  {/if}
                  
                  {#if stats.hybrid_fallbacks > 10}
                    <Badge variant="outline" class="bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200">
                      <Info class="mr-1 h-2 w-2" />
                      High Fallback Activity
                    </Badge>
                  {/if}
                </div>
              </div>
            {/if}
          </div>
        {:else}
          <!-- No Data State -->
          <div class="text-center py-8">
            <Archive class="h-8 w-8 text-muted-foreground mx-auto mb-2" />
            <p class="text-sm text-muted-foreground">
              No archive source statistics available yet.
            </p>
            <p class="text-xs text-muted-foreground mt-1">
              Statistics will appear after scraping activity begins.
            </p>
          </div>
        {/if}
      </CardContent>
    </Card>
  {/if}
</div>