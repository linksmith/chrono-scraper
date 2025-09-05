<script lang="ts">
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Input } from '$lib/components/ui/input';
  import { Label } from '$lib/components/ui/label';
  import { Badge } from '$lib/components/ui/badge';
  import { Archive, Layers, Database, Globe } from 'lucide-svelte';
  import { createEventDispatcher } from 'svelte';
  
  import type { 
    ArchiveSource, 
    ArchiveConfig, 
    ArchiveConfiguration,
    FallbackStrategy 
  } from '$lib/types/archive';
  import { 
    DEFAULT_ARCHIVE_CONFIG, 
    ARCHIVE_SOURCE_OPTIONS,
    formatDelay,
    formatTime,
    validateArchiveConfig
  } from '$lib/types/archive';

  const dispatch = createEventDispatcher<{
    update: ArchiveConfiguration
  }>();

  export let archive_source: ArchiveSource = 'hybrid';
  export let fallback_enabled: boolean = true;
  export let archive_config: ArchiveConfig = { ...DEFAULT_ARCHIVE_CONFIG };
  
  export let showAdvanced: boolean = true; // Option to hide advanced settings
  export let compact: boolean = false;     // Compact mode for smaller displays

  // Validation
  $: configErrors = fallback_enabled ? validateArchiveConfig(archive_config) : [];
  $: isValid = configErrors.length === 0;

  // Dispatch changes to parent
  $: dispatch('update', { 
    archive_source, 
    fallback_enabled, 
    archive_config
  });

  const iconComponents = {
    globe: Globe,
    database: Database,
    layers: Layers,
    archive: Archive
  };
</script>

{#if compact}
  <!-- Compact Mode -->
  <div class="space-y-3">
    <Label class="text-sm font-medium">Archive Source</Label>
    <div class="space-y-2">
      {#each ARCHIVE_SOURCE_OPTIONS as option}
        <label class="flex items-center space-x-2 cursor-pointer p-2 rounded border border-border hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors {option.recommended ? 'border-emerald-200 bg-emerald-50 dark:bg-emerald-950/50' : ''}">
          <input
            type="radio"
            name="archive-source-compact"
            value={option.value}
            bind:group={archive_source}
            class="h-4 w-4 text-emerald-500 border-gray-300 focus:ring-emerald-500"
          />
          <svelte:component this={iconComponents[option.icon]} class="h-4 w-4 text-{option.color}-600" />
          <div class="flex-1">
            <span class="text-sm font-medium">{option.title}</span>
            {#if option.recommended}
              <Badge variant="secondary" class="ml-2 bg-emerald-100 text-emerald-700 text-xs">Best Choice</Badge>
            {/if}
          </div>
        </label>
      {/each}
    </div>
    
    {#if archive_source === 'hybrid'}
      <div class="ml-6 p-3 bg-blue-50 dark:bg-blue-950/50 border border-blue-200 dark:border-blue-800 rounded">
        <label class="flex items-center space-x-2 cursor-pointer">
          <input
            type="checkbox"
            bind:checked={fallback_enabled}
            class="h-4 w-4 text-emerald-500 border-gray-300 focus:ring-emerald-500"
          />
          <span class="text-xs text-blue-700 dark:text-blue-300">Enable automatic fallback</span>
        </label>
      </div>
    {/if}
  </div>
{:else}
  <!-- Full Mode -->
  <Card class="shadow-sm">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <div class="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
          <Archive class="h-4 w-4 text-blue-600" />
        </div>
        Archive Source
      </CardTitle>
      <CardDescription>
        Choose which web archive to scrape content from. Hybrid mode provides the best reliability with automatic fallback.
      </CardDescription>
    </CardHeader>
    <CardContent class="space-y-4">
      <div class="space-y-3">
        {#each ARCHIVE_SOURCE_OPTIONS as option}
          <label class="flex items-start space-x-3 cursor-pointer p-3 rounded-lg border border-border hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors {option.recommended ? 'border-2 border-emerald-200 bg-emerald-50 dark:bg-emerald-950/50 dark:border-emerald-800' : ''}">
            <input
              type="radio"
              name="archive-source"
              value={option.value}
              bind:group={archive_source}
              class="mt-1 h-4 w-4 text-emerald-500 border-gray-300 focus:ring-emerald-500"
            />
            <div class="flex-1">
              <div class="flex items-center gap-2 mb-1">
                <svelte:component this={iconComponents[option.icon]} class="h-4 w-4 text-{option.color}-600" />
                <span class="font-medium text-sm">{option.title}</span>
                {#if option.recommended}
                  <Badge variant="secondary" class="bg-emerald-100 text-emerald-700 text-xs">
                    Best Choice
                  </Badge>
                {/if}
              </div>
              <p class="text-xs text-muted-foreground">
                {option.description}
              </p>
            </div>
          </label>
        {/each}
      </div>

      {#if archive_source === 'hybrid'}
        <div class="bg-blue-50 dark:bg-blue-950/50 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <div class="flex items-center gap-2 mb-3">
            <Layers class="h-4 w-4 text-blue-600" />
            <h4 class="font-medium text-blue-800 dark:text-blue-200 text-sm">Hybrid Mode Settings</h4>
          </div>
          
          <div class="space-y-4">
            <!-- Basic Fallback Toggle -->
            <label class="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                bind:checked={fallback_enabled}
                class="h-4 w-4 text-emerald-500 border-gray-300 focus:ring-emerald-500"
              />
              <span class="text-sm text-blue-700 dark:text-blue-300">Enable automatic fallback</span>
            </label>
            
            {#if fallback_enabled && showAdvanced}
              <!-- Advanced Configuration Panel -->
              <div class="ml-6 space-y-4 p-3 bg-white dark:bg-gray-900 border border-blue-100 dark:border-blue-800 rounded-lg">
                <h5 class="text-xs font-medium text-blue-600 dark:text-blue-400 uppercase tracking-wide">Advanced Configuration</h5>
                
                <!-- Fallback Strategy -->
                <div class="space-y-2">
                  <Label class="text-xs font-medium text-blue-700 dark:text-blue-300">Fallback Strategy</Label>
                  <div class="flex gap-3">
                    <label class="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="radio"
                        name="fallback-strategy"
                        value="sequential"
                        bind:group={archive_config.fallback_strategy}
                        class="h-3 w-3 text-emerald-500 border-gray-300 focus:ring-emerald-500"
                      />
                      <span class="text-xs text-blue-600 dark:text-blue-400">Sequential</span>
                    </label>
                    <label class="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="radio"
                        name="fallback-strategy"
                        value="parallel"
                        bind:group={archive_config.fallback_strategy}
                        class="h-3 w-3 text-emerald-500 border-gray-300 focus:ring-emerald-500"
                      />
                      <span class="text-xs text-blue-600 dark:text-blue-400">Parallel</span>
                    </label>
                  </div>
                  <p class="text-xs text-blue-500 dark:text-blue-400">
                    Sequential tries one archive at a time. Parallel tries both simultaneously for faster results.
                  </p>
                </div>

                <!-- Error Threshold -->
                <div class="space-y-2">
                  <Label for="error-threshold" class="text-xs font-medium text-blue-700 dark:text-blue-300">Error Threshold</Label>
                  <div class="flex items-center gap-2">
                    <Input
                      id="error-threshold"
                      type="number"
                      min="1"
                      max="10"
                      bind:value={archive_config.circuit_breaker_threshold}
                      class="w-20 h-8 text-xs"
                    />
                    <span class="text-xs text-blue-600 dark:text-blue-400">consecutive failures</span>
                  </div>
                  <p class="text-xs text-blue-500 dark:text-blue-400">
                    Number of failures before switching to the fallback archive.
                  </p>
                </div>

                <!-- Fallback Delay -->
                <div class="space-y-2">
                  <Label for="fallback-delay" class="text-xs font-medium text-blue-700 dark:text-blue-300">Fallback Delay</Label>
                  <div class="flex items-center gap-2">
                    <Input
                      id="fallback-delay"
                      type="number"
                      min="0"
                      max="30"
                      step="0.5"
                      bind:value={archive_config.fallback_delay}
                      class="w-20 h-8 text-xs"
                    />
                    <span class="text-xs text-blue-600 dark:text-blue-400">seconds</span>
                  </div>
                  <p class="text-xs text-blue-500 dark:text-blue-400">
                    Delay before attempting fallback (0 for immediate).
                  </p>
                </div>

                <!-- Recovery Time -->
                <div class="space-y-2">
                  <Label for="recovery-time" class="text-xs font-medium text-blue-700 dark:text-blue-300">Recovery Time</Label>
                  <div class="flex items-center gap-2">
                    <Input
                      id="recovery-time"
                      type="number"
                      min="30"
                      max="3600"
                      step="30"
                      bind:value={archive_config.recovery_time}
                      class="w-20 h-8 text-xs"
                    />
                    <span class="text-xs text-blue-600 dark:text-blue-400">seconds</span>
                  </div>
                  <p class="text-xs text-blue-500 dark:text-blue-400">
                    How long to wait before retrying a previously failed archive.
                  </p>
                </div>
              </div>
            {/if}
            
            {#if configErrors.length > 0}
              <div class="mt-3 p-2 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 rounded">
                <div class="text-xs text-red-600 dark:text-red-400 space-y-1">
                  {#each configErrors as error}
                    <div>⚠️ {error}</div>
                  {/each}
                </div>
              </div>
            {/if}
            
            <p class="text-xs text-blue-600 dark:text-blue-400">
              When enabled, the system will automatically try the secondary archive if the primary fails. This provides better success rates but may increase processing time.
            </p>
          </div>
        </div>
      {/if}

      <!-- Archive Source Summary -->
      <div class="bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
        <h4 class="font-medium text-gray-800 dark:text-gray-200 mb-2 text-sm">📚 Archive Configuration</h4>
        <div class="text-sm text-gray-700 dark:text-gray-300 space-y-1">
          <div class="flex justify-between items-center">
            <span>Selected Source:</span>
            <Badge variant="outline" class="text-xs">
              {#if archive_source === 'wayback'}
                Wayback Machine
              {:else if archive_source === 'commoncrawl'}
                Common Crawl
              {:else}
                Hybrid Mode
              {/if}
            </Badge>
          </div>
          {#if archive_source === 'hybrid'}
            <div class="flex justify-between items-center">
              <span>Fallback Enabled:</span>
              <Badge variant={fallback_enabled ? 'default' : 'secondary'} class="text-xs">
                {fallback_enabled ? 'Yes' : 'No'}
              </Badge>
            </div>
            {#if fallback_enabled && showAdvanced}
              <div class="text-xs text-gray-600 dark:text-gray-400 space-y-0.5 mt-2">
                <div>Strategy: {archive_config.fallback_strategy}</div>
                <div>Error threshold: {archive_config.circuit_breaker_threshold} failures</div>
                <div>Fallback delay: {formatDelay(archive_config.fallback_delay)}</div>
                <div>Recovery time: {formatTime(archive_config.recovery_time)}</div>
              </div>
            {/if}
          {/if}
        </div>
      </div>
    </CardContent>
  </Card>
{/if}