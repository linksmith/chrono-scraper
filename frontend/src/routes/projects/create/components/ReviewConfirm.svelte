<script lang="ts">
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Badge } from '$lib/components/ui/badge';
  import { Separator } from '$lib/components/ui/separator';
  import { CheckCircle, Globe, Link, Calendar, Settings, Brain, DollarSign, FileText, Archive, Layers, Database } from 'lucide-svelte';
  import { createEventDispatcher } from 'svelte';

  const dispatch = createEventDispatcher();

  export let projectName = '';
  export let description = '';
  export let targets = [];
  export let archive_source = 'hybrid';
  export let fallback_enabled = true;
  export let archive_config = {};
  export let auto_start_scraping = true;

  export let enable_attachment_download = false;
  export let extract_entities = false;
  export let langextractEnabled = false;
  export let langextractProvider = 'disabled';
  export let langextractModel = '';
  export let langextractCostEstimate = null;

  // Always valid since this is just review
  $: isValid = true;

  $: validTargets = targets.filter(t => t.value.trim());
  $: hasDateFilters = validTargets.some(t => t.from_date || t.to_date);
  $: enabledFeatures = [
    auto_start_scraping && 'Auto-start scraping',
    'Search indexing', // Always enabled
    enable_attachment_download && 'Download attachments',
    extract_entities && 'Entity extraction',
    langextractEnabled && 'Advanced AI processing'
  ].filter(Boolean);

  // Dispatch changes to parent
  $: dispatch('update', { isValid });

  const formatDate = (dateStr) => {
    if (!dateStr) return null;
    return new Date(dateStr).toLocaleDateString();
  };

  const getProviderName = (provider) => {
    const names = {
      'openrouter': 'OpenRouter',
      'openai': 'OpenAI',
      'anthropic': 'Anthropic',  
      'ollama': 'Ollama (Local)',
      'disabled': 'Disabled'
    };
    return names[provider] || provider;
  };

  const getArchiveSourceName = (source) => {
    const names = {
      'wayback': 'Wayback Machine',
      'commoncrawl': 'Common Crawl',
      'hybrid': 'Hybrid Mode'
    };
    return names[source] || source;
  };

  const getArchiveSourceIcon = (source) => {
    switch (source) {
      case 'wayback': return Globe;
      case 'commoncrawl': return Database;
      case 'hybrid': return Layers;
      default: return Archive;
    }
  };
</script>

<div class="space-y-4 sm:space-y-6">
  <div class="text-center space-y-2 px-2 sm:px-0">
    <h2 class="text-xl sm:text-2xl font-bold font-space-grotesk text-emerald-600">
      Review & Confirm
    </h2>
    <p class="text-sm sm:text-base text-muted-foreground">
      Review your project configuration before creating
    </p>
  </div>

  <!-- Project Summary -->
  <Card class="shadow-sm">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <div class="w-8 h-8 bg-emerald-100 rounded-full flex items-center justify-center">
          <CheckCircle class="w-4 h-4 text-emerald-600" />
        </div>
        Project Summary
      </CardTitle>
    </CardHeader>
    <CardContent class="space-y-3 sm:space-y-4 p-4 sm:p-6">
      <div>
        <h3 class="font-semibold text-lg font-space-grotesk">{projectName}</h3>
        <p class="text-muted-foreground mt-1">{description}</p>
      </div>
    </CardContent>
  </Card>

  <!-- Targets Summary -->
  <Card class="shadow-sm">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <Globe class="w-5 h-5 text-emerald-600" />
        Scraping Targets
        <Badge variant="secondary">{validTargets.length} target{validTargets.length !== 1 ? 's' : ''}</Badge>
      </CardTitle>
    </CardHeader>
    <CardContent class="space-y-3 sm:space-y-4 p-4 sm:p-6">
      {#each validTargets as target, index}
        <div class="flex items-start justify-between p-3 bg-muted/50 rounded-lg">
          <div class="flex items-start gap-3">
            <div class="mt-1">
              {#if target.type === 'domain'}
                <Globe class="w-4 h-4 text-emerald-500" />
              {:else}
                <Link class="w-4 h-4 text-blue-500" />
              {/if}
            </div>
            <div>
              <p class="font-medium">{target.value}</p>
              <div class="flex items-center gap-2 mt-1">
                <Badge variant="outline" class="text-xs">
                  {target.type === 'domain' ? 'Entire Domain' : 'Specific URL'}
                </Badge>
                {#if target.from_date || target.to_date}
                  <Badge variant="outline" class="text-xs">
                    <Calendar class="w-3 h-3 mr-1" />
                    {#if target.from_date && target.to_date}
                      {formatDate(target.from_date)} - {formatDate(target.to_date)}
                    {:else if target.from_date}
                      From {formatDate(target.from_date)}
                    {:else}
                      Until {formatDate(target.to_date)}
                    {/if}
                  </Badge>
                {/if}
              </div>
            </div>
          </div>
        </div>
      {/each}
    </CardContent>
  </Card>

  <!-- Archive Source Configuration -->
  <Card class="shadow-sm">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <svelte:component this={getArchiveSourceIcon(archive_source)} class="w-5 h-5 text-blue-600" />
        Archive Source
        <Badge variant="secondary">{getArchiveSourceName(archive_source)}</Badge>
      </CardTitle>
    </CardHeader>
    <CardContent class="space-y-3 sm:space-y-4 p-4 sm:p-6">
      <div class="flex items-start gap-3 p-3 bg-blue-50 dark:bg-blue-950/50 rounded-lg border border-blue-200 dark:border-blue-800">
        <svelte:component this={getArchiveSourceIcon(archive_source)} class="w-5 h-5 text-blue-600 mt-0.5" />
        <div class="flex-1">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-medium text-blue-800 dark:text-blue-200">{getArchiveSourceName(archive_source)}</span>
            {#if archive_source === 'hybrid'}
              <Badge variant="secondary" class="bg-emerald-100 text-emerald-700 text-xs">
                Recommended
              </Badge>
            {/if}
          </div>
          <p class="text-sm text-blue-700 dark:text-blue-300">
            {#if archive_source === 'wayback'}
              Most comprehensive coverage with decades of historical data from Internet Archive.
            {:else if archive_source === 'commoncrawl'}
              Monthly web snapshots with faster queries and good coverage of recent content.
            {:else}
              Automatic fallback between archives for maximum reliability and comprehensive coverage.
            {/if}
          </p>
          {#if archive_source === 'hybrid'}
            <div class="mt-2 space-y-1">
              <div class="flex items-center gap-2">
                <CheckCircle class="w-4 h-4 text-emerald-500" />
                <span class="text-sm text-blue-700 dark:text-blue-300">
                  Fallback enabled: {fallback_enabled ? 'Yes' : 'No'}
                </span>
              </div>
              {#if fallback_enabled && archive_config}
                <div class="ml-6 text-xs text-blue-600 dark:text-blue-400 space-y-0.5">
                  {#if archive_config.fallback_strategy}
                    <div>Strategy: {archive_config.fallback_strategy}</div>
                  {/if}
                  {#if archive_config.circuit_breaker_threshold}
                    <div>Error threshold: {archive_config.circuit_breaker_threshold} failures</div>
                  {/if}
                  {#if archive_config.fallback_delay !== undefined}
                    <div>Fallback delay: {archive_config.fallback_delay}s</div>
                  {/if}
                  {#if archive_config.recovery_time}
                    <div>Recovery time: {archive_config.recovery_time}s</div>
                  {/if}
                </div>
              {/if}
            </div>
          {/if}
        </div>
      </div>
    </CardContent>
  </Card>

  <!-- Processing Configuration -->
  <Card class="shadow-sm">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <Settings class="w-5 h-5 text-emerald-600" />
        Processing Configuration
      </CardTitle>
    </CardHeader>
    <CardContent class="space-y-3 sm:space-y-4 p-4 sm:p-6">
      <div class="grid gap-3">
        {#each enabledFeatures as feature}
          <div class="flex items-center gap-2">
            <CheckCircle class="w-4 h-4 text-emerald-500" />
            <span class="text-sm">{feature}</span>
          </div>
        {/each}
      </div>

      {#if langextractEnabled}
        <Separator />
        <div class="space-y-3">
          <h4 class="font-medium flex items-center gap-2">
            <Brain class="w-4 h-4 text-purple-500" />
            AI Configuration
          </h4>
          <div class="grid gap-2 text-sm pl-6">
            <div class="flex justify-between">
              <span class="text-muted-foreground">Provider:</span>
              <span class="font-medium">{getProviderName(langextractProvider)}</span>
            </div>
            {#if langextractModel}
              <div class="flex justify-between">
                <span class="text-muted-foreground">Model:</span>
                <span class="font-medium text-xs">{langextractModel}</span>
              </div>
            {/if}
          </div>
        </div>
      {/if}
    </CardContent>
  </Card>

  <!-- Cost Estimate (if applicable) -->
  {#if langextractCostEstimate}
    <Card class="shadow-sm bg-emerald-50 dark:bg-gray-800 border-emerald-200 dark:border-gray-700">
      <CardHeader>
        <CardTitle class="flex items-center gap-2">
          <DollarSign class="w-5 h-5 text-emerald-600" />
          Estimated AI Processing Cost
        </CardTitle>
        <CardDescription>
          Based on your targets and selected AI model
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div class="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p class="text-muted-foreground">Estimated Pages</p>
            <p class="font-semibold text-lg">{langextractCostEstimate.estimated_pages.toLocaleString()}</p>
          </div>
          <div>
            <p class="text-muted-foreground">Total Cost</p>
            <p class="font-semibold text-lg text-emerald-700 dark:text-emerald-400">${langextractCostEstimate.total_estimated_cost}</p>
          </div>
          <div>
            <p class="text-muted-foreground">Cost per 1k pages</p>
            <p class="font-medium">${langextractCostEstimate.cost_per_1k_pages}</p>
          </div>
          <div>
            <p class="text-muted-foreground">Model</p>
            <p class="font-medium">{langextractCostEstimate.model.name}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  {/if}

  <!-- Ready to Create -->
  <Card class="shadow-sm bg-gradient-to-r from-emerald-50 to-green-50 dark:from-gray-800 dark:to-gray-900 border-emerald-200 dark:border-gray-700">
    <CardContent class="p-4 sm:p-6">
      <div class="flex items-center gap-4">
        <div class="w-12 h-12 bg-emerald-500 rounded-full flex items-center justify-center">
          <CheckCircle class="w-6 h-6 text-white" />
        </div>
        <div class="flex-1">
          <h3 class="font-semibold text-emerald-800 dark:text-emerald-400">Ready to Create Project</h3>
          <p class="text-emerald-700 dark:text-gray-300 text-sm mt-1">
            Your project is configured and ready to be created.
            {#if auto_start_scraping}
              Scraping will begin automatically.
            {:else}
              You can start scraping manually from the project dashboard.
            {/if}
          </p>
        </div>
      </div>
    </CardContent>
  </Card>
</div>