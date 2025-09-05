<script lang="ts">
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Switch } from '$lib/components/ui/switch';
  import { Label } from '$lib/components/ui/label';
  import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
  import { Badge } from '$lib/components/ui/badge';
  import { Skeleton } from '$lib/components/ui/skeleton';
  import { Settings, Zap, Brain, Rocket, FileText, Download, Bot } from 'lucide-svelte';
  import { createEventDispatcher } from 'svelte';
  import { getApiUrl, apiFetch } from '$lib/utils';

  const dispatch = createEventDispatcher();

  // Basic Processing Options
  export let auto_start_scraping = true;
  export let enable_attachment_download = false;
  export let extract_entities = false;

  // AI Processing Options
  export let langextractEnabled = false;
  export let langextractProvider = 'disabled';
  export let langextractModel = '';

  // Cost estimation
  export let langextractCostEstimate = null;
  export let targets = [];

  let availableModels = [];
  let loadingModels = false;
  let loadingCostEstimate = false;

  // Always valid step
  $: isValid = true;

  // Dispatch changes to parent
  $: dispatch('update', { 
    auto_start_scraping, 
    enable_attachment_download, 
    extract_entities,
    langextractEnabled,
    langextractProvider,
    langextractModel,
    langextractCostEstimate,
    isValid 
  });

  const loadAvailableModels = async () => {
    if (availableModels.length > 0) return;
    
    loadingModels = true;
    try {
      const response = await apiFetch(getApiUrl('/api/v1/projects/langextract/models'));
      
      if (response.ok) {
        availableModels = await response.json();
      }
    } catch (err) {
      console.error('Failed to load models:', err);
    } finally {
      loadingModels = false;
    }
  };

  const calculateCostEstimate = async () => {
    if (!langextractModel || !langextractEnabled) {
      langextractCostEstimate = null;
      return;
    }
    
    const validTargets = targets.filter(t => t.value.trim());
    if (validTargets.length === 0) return;
    
    loadingCostEstimate = true;
    try {
      const response = await apiFetch(getApiUrl('/api/v1/projects/langextract/cost-estimate'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model_id: langextractModel,
          domains: validTargets.map(t => t.value),
          estimated_pages: 1000 * validTargets.length
        })
      });
      
      if (response.ok) {
        langextractCostEstimate = await response.json();
      }
    } catch (err) {
      console.error('Failed to calculate cost:', err);
    } finally {
      loadingCostEstimate = false;
    }
  };

  // Reactive statements
  $: if (langextractEnabled && langextractProvider === 'openrouter') {
    loadAvailableModels();
  }

  $: if (langextractModel && targets.length > 0) {
    calculateCostEstimate();
  }

  // Reset model when provider changes
  $: if (langextractProvider !== 'openrouter') {
    langextractModel = '';
    langextractCostEstimate = null;
  }
</script>

<div class="space-y-4 sm:space-y-6">
  <div class="text-center space-y-2 px-2 sm:px-0">
    <h2 class="text-xl sm:text-2xl font-bold font-space-grotesk text-emerald-600">
      Processing Options
    </h2>
    <p class="text-sm sm:text-base text-muted-foreground">
      Configure how your content should be processed and what features to enable
    </p>
  </div>

  <!-- Basic Processing Options -->
  <Card class="shadow-sm">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <div class="w-8 h-8 bg-emerald-100 rounded-full flex items-center justify-center">
          <Settings class="w-4 h-4 text-emerald-600" />
        </div>
        Basic Processing
        <Badge variant="secondary" class="ml-2">Essential</Badge>
      </CardTitle>
      <CardDescription>
        Core functionality for content scraping and processing
      </CardDescription>
    </CardHeader>
    <CardContent class="space-y-4 sm:space-y-6 p-4 sm:p-6">
      <!-- Auto Start -->
      <div class="flex items-center justify-between p-4 border border-border rounded-lg">
        <div class="flex items-start gap-3">
          <Rocket class="h-5 w-5 text-emerald-500 mt-0.5" />
          <div>
            <Label class="text-base font-medium">Start scraping immediately</Label>
            <p class="text-sm text-muted-foreground mt-1">
              Begin scraping as soon as the project is created
            </p>
          </div>
        </div>
        <Switch bind:checked={auto_start_scraping} />
      </div>



      <!-- Attachment Download -->
      <div class="flex items-center justify-between p-4 border border-border rounded-lg">
        <div class="flex items-start gap-3">
          <Download class="h-5 w-5 text-emerald-500 mt-0.5" />
          <div>
            <Label class="text-base font-medium">Download attachments</Label>
            <p class="text-sm text-muted-foreground mt-1">
              Save PDFs, documents, and other file types
            </p>
          </div>
        </div>
        <Switch bind:checked={enable_attachment_download} />
      </div>
    </CardContent>
  </Card>

  <!-- AI-Powered Features -->
  <Card class="shadow-sm">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <div class="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center">
          <Brain class="w-4 h-4 text-purple-600" />
        </div>
        AI-Powered Features
        <Badge variant="secondary" class="ml-2 bg-purple-100 text-purple-700">Advanced</Badge>
      </CardTitle>
      <CardDescription>
        Enhanced processing using artificial intelligence
      </CardDescription>
    </CardHeader>
    <CardContent class="space-y-4 sm:space-y-6 p-4 sm:p-6">
      <!-- Entity Extraction -->
      <div class="flex items-center justify-between p-4 border border-border rounded-lg">
        <div class="flex items-start gap-3">
          <FileText class="h-5 w-5 text-purple-500 mt-0.5" />
          <div>
            <Label class="text-base font-medium">Extract entities from content</Label>
            <p class="text-sm text-muted-foreground mt-1">
              Automatically identify people, organizations, and locations
            </p>
          </div>
        </div>
        <Switch bind:checked={extract_entities} />
      </div>

      <!-- LangExtract AI -->
      <div class="flex items-center justify-between p-4 border border-border rounded-lg">
        <div class="flex items-start gap-3">
          <Bot class="h-5 w-5 text-purple-500 mt-0.5" />
          <div>
            <Label class="text-base font-medium">Advanced AI processing</Label>
            <p class="text-sm text-muted-foreground mt-1">
              Deep content analysis and structured data extraction
            </p>
          </div>
        </div>
        <Switch bind:checked={langextractEnabled} />
      </div>

      <!-- AI Configuration (when enabled) -->
      {#if langextractEnabled}
        <div class="border-l-4 border-purple-200 pl-6 space-y-4">
          <!-- AI Provider Selection -->
          <div class="space-y-2">
            <Label for="aiProvider" class="text-sm font-medium">AI Provider</Label>
            <Select bind:value={langextractProvider}>
              <SelectTrigger id="aiProvider">
                <SelectValue placeholder="Choose an AI provider..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="disabled">Disabled</SelectItem>
                <SelectItem value="openrouter">
                  <div class="flex items-center gap-2">
                    <Zap class="h-4 w-4 text-emerald-500" />
                    OpenRouter (Recommended)
                  </div>
                </SelectItem>
                <SelectItem value="openai">OpenAI (Direct)</SelectItem>
                <SelectItem value="anthropic">Anthropic (Direct)</SelectItem>
                <SelectItem value="ollama">Ollama (Local)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <!-- Model Selection (OpenRouter) -->
          {#if langextractProvider === 'openrouter'}
            <div class="space-y-2">
              <Label for="aiModel" class="text-sm font-medium">AI Model</Label>
              <Select bind:value={langextractModel} disabled={loadingModels}>
                <SelectTrigger id="aiModel">
                  <SelectValue placeholder={loadingModels ? "Loading models..." : "Select a model..."} />
                </SelectTrigger>
                <SelectContent>
                  {#each availableModels as model}
                    <SelectItem value={model.id}>
                      <div class="flex flex-col">
                        <span class="font-medium">{model.name}</span>
                        <span class="text-xs text-muted-foreground">
                          ${model.pricing.estimated_per_1k_pages}/1k pages • {model.provider}
                        </span>
                      </div>
                    </SelectItem>
                  {/each}
                </SelectContent>
              </Select>
              {#if loadingModels}
                <p class="text-sm text-muted-foreground">Loading available models...</p>
              {/if}
            </div>

            <!-- Cost Estimate -->
            {#if langextractCostEstimate}
              <Card class="bg-emerald-50 dark:bg-gray-800 border-emerald-200 dark:border-gray-700">
                <CardHeader class="pb-3">
                  <CardTitle class="text-base flex items-center gap-2">
                    <div class="w-6 h-6 bg-emerald-500 rounded-full flex items-center justify-center">
                      <span class="text-white text-xs">$</span>
                    </div>
                    Cost Estimate
                  </CardTitle>
                </CardHeader>
                <CardContent class="space-y-2 text-sm">
                  <div class="grid grid-cols-2 gap-4">
                    <div>
                      <p class="text-muted-foreground">Model</p>
                      <p class="font-medium">{langextractCostEstimate.model.name}</p>
                    </div>
                    <div>
                      <p class="text-muted-foreground">Estimated Pages</p>
                      <p class="font-medium">{langextractCostEstimate.estimated_pages.toLocaleString()}</p>
                    </div>
                    <div>
                      <p class="text-muted-foreground">Cost per 1k pages</p>
                      <p class="font-medium">${langextractCostEstimate.cost_per_1k_pages}</p>
                    </div>
                    <div>
                      <p class="text-muted-foreground">Total Estimated Cost</p>
                      <p class="font-semibold text-emerald-700 dark:text-emerald-400">${langextractCostEstimate.total_estimated_cost}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            {:else if loadingCostEstimate}
              <Card>
                <CardContent class="p-4">
                  <div class="flex items-center space-x-2">
                    <Skeleton class="h-4 w-4 rounded-full" />
                    <Skeleton class="h-4 w-32" />
                  </div>
                </CardContent>
              </Card>
            {/if}
          {/if}

          <!-- Direct Provider Note -->
          {#if langextractProvider !== 'disabled' && langextractProvider !== 'openrouter'}
            <Card class="border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20">
              <CardContent class="p-4">
                <p class="text-sm text-amber-800 dark:text-amber-300">
                  <strong>Note:</strong> Direct provider integration requires API keys to be configured in your environment.
                  OpenRouter is recommended for easier setup and access to multiple models.
                </p>
              </CardContent>
            </Card>
          {/if}
        </div>
      {/if}
    </CardContent>
  </Card>
</div>