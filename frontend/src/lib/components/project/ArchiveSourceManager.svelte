<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import { Badge } from '$lib/components/ui/badge';
  import { Switch } from '$lib/components/ui/switch';
  import { Label } from '$lib/components/ui/label';
  import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
  import { Input } from '$lib/components/ui/input';
  import { 
    Archive, 
    Globe, 
    Zap, 
    Settings, 
    AlertTriangle, 
    CheckCircle, 
    Info,
    Clock,
    Activity,
    Shield,
    Save,
    RotateCcw
  } from 'lucide-svelte';
  import ArchiveSourceBadge from './ArchiveSourceBadge.svelte';
  import type { 
    ArchiveSource, 
    ArchiveConfig, 
    ArchiveSourceInfo,
    ArchiveSourceMetrics 
  } from '$lib/types/scraping';
  
  const dispatch = createEventDispatcher<{
    save: { archiveSource: ArchiveSource; fallbackEnabled: boolean; archiveConfig: ArchiveConfig };
    cancel: void;
    test: { source: ArchiveSource };
  }>();
  
  export let projectId: number;
  export let currentArchiveSource: ArchiveSource = 'wayback';
  export let currentFallbackEnabled: boolean = true;
  export let currentArchiveConfig: ArchiveConfig = {};
  export let metrics: Record<ArchiveSource, ArchiveSourceMetrics> | undefined = undefined;
  export let readonly: boolean = false;
  export let showAdvanced: boolean = false;
  
  // Local state
  let archiveSource: ArchiveSource = currentArchiveSource;
  let fallbackEnabled: boolean = currentFallbackEnabled;
  let archiveConfig: ArchiveConfig = { ...currentArchiveConfig };
  let showAdvancedSettings: boolean = showAdvanced;
  let hasUnsavedChanges: boolean = false;
  let testingSource: ArchiveSource | null = null;
  
  // Archive source options
  const archiveSourceOptions = [
    {
      value: 'wayback',
      label: 'Wayback Machine',
      description: 'Internet Archive\'s Wayback Machine - most comprehensive coverage',
      icon: Archive,
      color: 'text-blue-600 dark:text-blue-400',
      recommended: false
    },
    {
      value: 'commoncrawl',
      label: 'Common Crawl',
      description: 'Open repository of web crawl data - fast and reliable',
      icon: Globe,
      color: 'text-green-600 dark:text-green-400',
      recommended: false
    },
    {
      value: 'hybrid',
      label: 'Hybrid Mode',
      description: 'Intelligent combination of both sources with automatic fallback',
      icon: Zap,
      color: 'text-purple-600 dark:text-purple-400',
      recommended: true
    }
  ] as const;
  
  // Default configuration values
  const defaultConfig: Record<string, any> = {
    fallback_delay_seconds: 2,
    max_fallback_attempts: 3,
    failure_threshold: 5,
    recovery_timeout_seconds: 60,
    half_open_max_calls: 10,
    concurrent_requests: 4,
    request_timeout_seconds: 30,
    retry_exponential_base: 2
  };
  
  // Reactive statements
  $: {
    hasUnsavedChanges = 
      archiveSource !== currentArchiveSource ||
      fallbackEnabled !== currentFallbackEnabled ||
      JSON.stringify(archiveConfig) !== JSON.stringify(currentArchiveConfig);
  }
  
  $: selectedOption = archiveSourceOptions.find(opt => opt.value === archiveSource);
  
  function handleSave() {
    dispatch('save', {
      archiveSource,
      fallbackEnabled,
      archiveConfig
    });
  }
  
  function handleCancel() {
    // Reset to original values
    archiveSource = currentArchiveSource;
    fallbackEnabled = currentFallbackEnabled;
    archiveConfig = { ...currentArchiveConfig };
    dispatch('cancel');
  }
  
  function handleReset() {
    archiveConfig = { ...defaultConfig };
  }
  
  async function handleTestConnection(source: ArchiveSource) {
    testingSource = source;
    dispatch('test', { source });
    // Reset testing state after 3 seconds
    setTimeout(() => {
      testingSource = null;
    }, 3000);
  }
  
  function updateConfig(key: string, value: any) {
    archiveConfig = {
      ...archiveConfig,
      [key]: value
    };
  }
  
  // Get metrics for a specific source
  function getSourceMetrics(source: ArchiveSource): ArchiveSourceMetrics | undefined {
    return metrics?.[source];
  }
  
  // Circuit breaker status indicator
  function getCircuitBreakerColor(status: string): string {
    switch (status) {
      case 'closed': return 'text-green-500';
      case 'open': return 'text-red-500';
      case 'half_open': return 'text-yellow-500';
      default: return 'text-gray-500';
    }
  }
</script>

<div class="space-y-6">
  <!-- Header -->
  <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
    <div>
      <h3 class="text-lg font-semibold">Archive Source Configuration</h3>
      <p class="text-sm text-muted-foreground">
        Choose how your project accesses archived web content
      </p>
    </div>
    {#if hasUnsavedChanges}
      <Badge variant="secondary" class="self-start sm:self-center">
        <Activity class="mr-1 h-3 w-3" />
        Unsaved Changes
      </Badge>
    {/if}
  </div>

  <!-- Current Configuration Display -->
  <Card class="border-l-4 border-l-blue-500 bg-blue-50/50 dark:bg-blue-950/20">
    <CardHeader class="pb-3">
      <CardTitle class="text-base flex items-center gap-2">
        <Settings class="h-4 w-4" />
        Current Configuration
      </CardTitle>
    </CardHeader>
    <CardContent class="space-y-3">
      <div class="flex flex-col sm:flex-row sm:items-center gap-2">
        <span class="text-sm font-medium">Archive Source:</span>
        <ArchiveSourceBadge 
          {archiveSource}
          {fallbackEnabled}
          metrics={getSourceMetrics(archiveSource)}
          size="md"
        />
      </div>
      
      {#if metrics}
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          {#each archiveSourceOptions as option}
            {@const sourceMetrics = getSourceMetrics(option.value)}
            {#if sourceMetrics}
              <div class="flex items-center justify-between p-2 rounded border border-border">
                <div class="flex items-center gap-2">
                  <svelte:component this={option.icon} class="h-3 w-3 {option.color}" />
                  <span class="font-medium">{option.label}</span>
                </div>
                <div class="text-right">
                  <div class="font-mono text-xs">{sourceMetrics.success_rate.toFixed(1)}%</div>
                  <div class="text-xs text-muted-foreground">
                    <div class="w-1.5 h-1.5 rounded-full inline-block mr-1 {getCircuitBreakerColor(sourceMetrics.circuit_breaker_status)}"></div>
                    {sourceMetrics.avg_response_time_ms}ms
                  </div>
                </div>
              </div>
            {/if}
          {/each}
        </div>
      {/if}
    </CardContent>
  </Card>

  <!-- Archive Source Selection -->
  <Card>
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <Archive class="h-4 w-4" />
        Archive Source Selection
      </CardTitle>
      <CardDescription>
        Choose your primary archive source for web content retrieval
      </CardDescription>
    </CardHeader>
    <CardContent class="space-y-4">
      {#each archiveSourceOptions as option}
        <div 
          class="flex items-start gap-3 p-4 border border-border rounded-lg cursor-pointer transition-all duration-200 hover:border-primary/50 hover:bg-accent/50 {archiveSource === option.value ? 'border-primary bg-primary/5 dark:bg-primary/10' : ''}"
          onclick={() => !readonly && (archiveSource = option.value)}
          role="radio"
          aria-checked={archiveSource === option.value}
          tabindex={readonly ? -1 : 0}
        >
          <div class="flex items-center pt-0.5">
            <input
              type="radio"
              bind:group={archiveSource}
              value={option.value}
              disabled={readonly}
              class="sr-only"
            />
            <div class={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
              archiveSource === option.value 
                ? 'border-primary bg-primary' 
                : 'border-muted-foreground'
            }`}>
              {#if archiveSource === option.value}
                <div class="w-2 h-2 rounded-full bg-primary-foreground"></div>
              {/if}
            </div>
          </div>
          
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <svelte:component this={option.icon} class="h-4 w-4 {option.color} flex-shrink-0" />
              <Label class="text-base font-medium cursor-pointer">{option.label}</Label>
              {#if option.recommended}
                <Badge variant="secondary" class="text-xs">Recommended</Badge>
              {/if}
            </div>
            <p class="text-sm text-muted-foreground">{option.description}</p>
            
            {#if getSourceMetrics(option.value)}
              {@const sourceMetrics = getSourceMetrics(option.value)}
              <div class="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                <span>Success: {sourceMetrics.success_rate.toFixed(1)}%</span>
                <span>Response: {sourceMetrics.avg_response_time_ms}ms</span>
                <span class="flex items-center gap-1">
                  <div class="w-2 h-2 rounded-full {getCircuitBreakerColor(sourceMetrics.circuit_breaker_status)}"></div>
                  {sourceMetrics.circuit_breaker_status}
                </span>
              </div>
            {/if}
          </div>
          
          {#if !readonly}
            <Button
              variant="outline"
              size="sm"
              onclick={(e) => {
                e.stopPropagation();
                handleTestConnection(option.value);
              }}
              disabled={testingSource === option.value}
            >
              {#if testingSource === option.value}
                <Activity class="mr-1 h-3 w-3 animate-spin" />
                Testing...
              {:else}
                <CheckCircle class="mr-1 h-3 w-3" />
                Test
              {/if}
            </Button>
          {/if}
        </div>
      {/each}
    </CardContent>
  </Card>

  <!-- Fallback Configuration -->
  {#if archiveSource === 'hybrid'}
    <Card class="border-purple-200 dark:border-purple-700 bg-purple-50 dark:bg-purple-950/20">
      <CardHeader>
        <CardTitle class="flex items-center gap-2 text-purple-800 dark:text-purple-200">
          <Zap class="h-4 w-4" />
          Hybrid Mode Configuration
        </CardTitle>
        <CardDescription class="text-purple-600 dark:text-purple-300">
          Configure intelligent fallback behavior between archive sources
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <Label class="text-base font-medium">Enable Automatic Fallback</Label>
            <p class="text-sm text-muted-foreground mt-1">
              Automatically try alternative sources when primary fails
            </p>
          </div>
          <Switch bind:checked={fallbackEnabled} disabled={readonly} />
        </div>
        
        {#if fallbackEnabled}
          <div class="border-l-4 border-purple-300 pl-4 space-y-3">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label for="fallback-delay" class="text-sm font-medium">Fallback Delay (seconds)</Label>
                <Input
                  id="fallback-delay"
                  type="number"
                  min="1"
                  max="30"
                  bind:value={archiveConfig.fallback_delay_seconds}
                  disabled={readonly}
                  class="mt-1"
                  placeholder={String(defaultConfig.fallback_delay_seconds)}
                />
              </div>
              
              <div>
                <Label for="max-attempts" class="text-sm font-medium">Max Fallback Attempts</Label>
                <Input
                  id="max-attempts"
                  type="number"
                  min="1"
                  max="10"
                  bind:value={archiveConfig.max_fallback_attempts}
                  disabled={readonly}
                  class="mt-1"
                  placeholder={String(defaultConfig.max_fallback_attempts)}
                />
              </div>
            </div>
          </div>
        {/if}
      </CardContent>
    </Card>
  {/if}

  <!-- Advanced Settings -->
  {#if !readonly}
    <Card>
      <CardHeader>
        <div class="flex items-center justify-between">
          <div>
            <CardTitle class="flex items-center gap-2">
              <Settings class="h-4 w-4" />
              Advanced Settings
            </CardTitle>
            <CardDescription>
              Fine-tune performance and reliability parameters
            </CardDescription>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onclick={() => showAdvancedSettings = !showAdvancedSettings}
          >
            {showAdvancedSettings ? 'Hide' : 'Show'} Advanced
          </Button>
        </div>
      </CardHeader>
      
      {#if showAdvancedSettings}
        <CardContent class="space-y-6">
          <!-- Circuit Breaker Configuration -->
          <div class="space-y-4">
            <div class="flex items-center gap-2">
              <Shield class="h-4 w-4 text-orange-500" />
              <Label class="text-base font-medium">Circuit Breaker</Label>
            </div>
            
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 pl-6 border-l-2 border-orange-200 dark:border-orange-800">
              <div>
                <Label for="failure-threshold" class="text-sm font-medium">Failure Threshold</Label>
                <Input
                  id="failure-threshold"
                  type="number"
                  min="1"
                  max="20"
                  bind:value={archiveConfig.failure_threshold}
                  class="mt-1"
                  placeholder={String(defaultConfig.failure_threshold)}
                />
                <p class="text-xs text-muted-foreground mt-1">Failures before opening circuit</p>
              </div>
              
              <div>
                <Label for="recovery-timeout" class="text-sm font-medium">Recovery Timeout (s)</Label>
                <Input
                  id="recovery-timeout"
                  type="number"
                  min="10"
                  max="300"
                  bind:value={archiveConfig.recovery_timeout_seconds}
                  class="mt-1"
                  placeholder={String(defaultConfig.recovery_timeout_seconds)}
                />
                <p class="text-xs text-muted-foreground mt-1">Time before attempting recovery</p>
              </div>
              
              <div>
                <Label for="half-open-calls" class="text-sm font-medium">Half-Open Max Calls</Label>
                <Input
                  id="half-open-calls"
                  type="number"
                  min="1"
                  max="50"
                  bind:value={archiveConfig.half_open_max_calls}
                  class="mt-1"
                  placeholder={String(defaultConfig.half_open_max_calls)}
                />
                <p class="text-xs text-muted-foreground mt-1">Test calls during recovery</p>
              </div>
            </div>
          </div>

          <!-- Performance Configuration -->
          <div class="space-y-4">
            <div class="flex items-center gap-2">
              <Clock class="h-4 w-4 text-blue-500" />
              <Label class="text-base font-medium">Performance Tuning</Label>
            </div>
            
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 pl-6 border-l-2 border-blue-200 dark:border-blue-800">
              <div>
                <Label for="concurrent-requests" class="text-sm font-medium">Concurrent Requests</Label>
                <Input
                  id="concurrent-requests"
                  type="number"
                  min="1"
                  max="20"
                  bind:value={archiveConfig.concurrent_requests}
                  class="mt-1"
                  placeholder={String(defaultConfig.concurrent_requests)}
                />
                <p class="text-xs text-muted-foreground mt-1">Parallel request limit</p>
              </div>
              
              <div>
                <Label for="request-timeout" class="text-sm font-medium">Request Timeout (s)</Label>
                <Input
                  id="request-timeout"
                  type="number"
                  min="5"
                  max="120"
                  bind:value={archiveConfig.request_timeout_seconds}
                  class="mt-1"
                  placeholder={String(defaultConfig.request_timeout_seconds)}
                />
                <p class="text-xs text-muted-foreground mt-1">Individual request timeout</p>
              </div>
              
              <div>
                <Label for="retry-base" class="text-sm font-medium">Retry Exponential Base</Label>
                <Input
                  id="retry-base"
                  type="number"
                  min="1.5"
                  max="5"
                  step="0.1"
                  bind:value={archiveConfig.retry_exponential_base}
                  class="mt-1"
                  placeholder={String(defaultConfig.retry_exponential_base)}
                />
                <p class="text-xs text-muted-foreground mt-1">Backoff multiplier</p>
              </div>
            </div>
          </div>

          <!-- Reset to Defaults -->
          <div class="flex justify-end">
            <Button variant="outline" size="sm" onclick={handleReset}>
              <RotateCcw class="mr-1 h-3 w-3" />
              Reset to Defaults
            </Button>
          </div>
        </CardContent>
      {/if}
    </Card>
  {/if}

  <!-- Action Buttons -->
  {#if !readonly}
    <div class="flex flex-col sm:flex-row gap-2 sm:justify-end">
      <Button variant="outline" onclick={handleCancel} disabled={!hasUnsavedChanges}>
        Cancel
      </Button>
      <Button onclick={handleSave} disabled={!hasUnsavedChanges}>
        <Save class="mr-1 h-3 w-3" />
        Save Configuration
      </Button>
    </div>
  {/if}
</div>