<script lang="ts">
  import { goto } from '$app/navigation';
  import { getApiUrl, apiFetch } from '$lib/utils';
  import { Button } from '$lib/components/ui/button';
  import { Card, CardContent } from '$lib/components/ui/card';
  import { Alert, AlertDescription } from '$lib/components/ui/alert';
  import { AlertCircle, ArrowLeft, ArrowRight } from 'lucide-svelte';
  
  // Step Components
  import ProgressIndicator from './ProgressIndicator.svelte';
  import ProjectBasics from './ProjectBasics.svelte';
  import TargetConfiguration from './TargetConfiguration.svelte';
  import ProcessingOptions from './ProcessingOptions.svelte';
  import ReviewConfirm from './ReviewConfirm.svelte';

  // Form state
  let currentStep = 1;
  const totalSteps = 4;
  
  // Step validation states
  let stepValidation = {
    1: false,
    2: false,
    3: true, // Processing options are always valid
    4: true  // Review is always valid
  };


  // Form data
  let formData = {
    // Project basics
    projectName: '',
    description: '',
    
    // Targets
    targets: [{ value: '', type: 'domain', from_date: '', to_date: '' }],
    
    // Archive source configuration
    archive_source: 'hybrid',
    fallback_enabled: true,
    archive_config: {},
    
    // Processing options
    auto_start_scraping: true,
    enable_attachment_download: false,
    extract_entities: false,
    
    // AI options
    langextractEnabled: false,
    langextractProvider: 'disabled',
    langextractModel: '',
    langextractCostEstimate: null
  };

  // UI state
  let loading = false;
  let error = '';

  // Navigation
  const nextStep = () => {
    if (currentStep < totalSteps && stepValidation[currentStep]) {
      currentStep++;
    }
  };

  const prevStep = () => {
    if (currentStep > 1) {
      currentStep--;
    }
  };

  // Make canProceed reactive
  $: canProceed = (step) => {
    return stepValidation[step];
  };

  // Step update handlers
  const handleStep1Update = (event) => {
    const { projectName, description, isValid } = event.detail;
    formData.projectName = projectName;
    formData.description = description;
    stepValidation[1] = isValid;
    // Force reactivity by reassigning the object
    stepValidation = { ...stepValidation };
  };

  const handleStep2Update = (event) => {
    const { targets, archive_source, fallback_enabled, archive_config, isValid } = event.detail;
    formData.targets = targets;
    formData.archive_source = archive_source;
    formData.fallback_enabled = fallback_enabled;
    formData.archive_config = archive_config;
    stepValidation[2] = isValid;
    // Force reactivity by reassigning the object
    stepValidation = { ...stepValidation };
  };

  const handleStep3Update = (event) => {
    const { 
      auto_start_scraping, 
      enable_attachment_download, 
      extract_entities,
      langextractEnabled,
      langextractProvider,
      langextractModel,
      langextractCostEstimate,
      isValid 
    } = event.detail;
    
    formData.auto_start_scraping = auto_start_scraping;
    formData.enable_attachment_download = enable_attachment_download;
    formData.extract_entities = extract_entities;
    formData.langextractEnabled = langextractEnabled;
    formData.langextractProvider = langextractProvider;
    formData.langextractModel = langextractModel;
    formData.langextractCostEstimate = langextractCostEstimate;
    stepValidation[3] = isValid;
    // Force reactivity by reassigning the object
    stepValidation = { ...stepValidation };
  };

  const handleStep4Update = (event) => {
    const { isValid } = event.detail;
    stepValidation[4] = isValid;
    // Force reactivity by reassigning the object
    stepValidation = { ...stepValidation };
  };

  // Form submission
  const handleSubmit = async () => {
    const validTargets = formData.targets.filter(t => t.value.trim());
    if (validTargets.length === 0) {
      error = 'At least one target is required';
      return;
    }

    loading = true;
    error = '';

    try {
      // Create project with manual name and description (no LLM generation)
      const projectResponse = await apiFetch(getApiUrl('/api/v1/projects'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: formData.projectName,
          description: formData.description.trim() || null, // Allow empty description
          process_documents: true, // Always enable search indexing
          enable_attachment_download: formData.enable_attachment_download,
          langextract_enabled: formData.langextractEnabled,
          langextract_provider: formData.langextractProvider,
          langextract_model: formData.langextractModel || null,
          langextract_estimated_cost_per_1k: formData.langextractCostEstimate?.cost_per_1k_pages || null,
          archive_source: formData.archive_source,
          fallback_enabled: formData.fallback_enabled,
          archive_config: formData.archive_config
        })
      });

      if (!projectResponse.ok) {
        const data = await projectResponse.json();
        error = data.detail || 'Failed to create project';
        return;
      }

      const project = await projectResponse.json();

      // Create domains for each target
      for (const target of validTargets) {
        try {
          const domainResponse = await apiFetch(getApiUrl(`/api/v1/projects/${project.id}/domains`), {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              domain_name: target.type === 'domain' ? target.value : new URL(target.value).hostname,
              match_type: target.type === 'domain' ? 'domain' : 'prefix',
              url_path: target.type === 'url' ? target.value : null,
              from_date: target.from_date || null,
              to_date: target.to_date || null,
              max_pages: null,
              active: true
            })
          });

          if (!domainResponse.ok) {
            console.error(`Failed to create domain/target: ${target.value}`);
          }
        } catch (err) {
          console.error(`Error creating domain/target ${target.value}:`, err);
        }
      }

      // Auto-start scraping if enabled
      if (formData.auto_start_scraping) {
        try {
          await apiFetch(getApiUrl(`/api/v1/projects/${project.id}/scrape`), {
            method: 'POST',
            headers: {}
          });
        } catch (e) {
          console.error('Failed to auto-start scraping', e);
        }
      }

      // Navigate to project page
      await goto(`/projects/${project.id}`);
    } catch (err) {
      error = 'Network error occurred';
      console.error('Project creation error:', err);
    } finally {
      loading = false;
    }
  };
</script>

<div class="max-w-4xl mx-auto space-y-8">
  <!-- Progress Indicator -->
  <ProgressIndicator {currentStep} {totalSteps} />

  <!-- Error Display -->
  {#if error}
    <Alert class="border-destructive">
      <AlertCircle class="h-4 w-4" />
      <AlertDescription>
        {error}
      </AlertDescription>
    </Alert>
  {/if}

  <!-- Step Content -->
  <div class="min-h-[600px]">
    {#if currentStep === 1}
      <ProjectBasics
        projectName={formData.projectName}
        description={formData.description}
        on:update={handleStep1Update}
      />
    {:else if currentStep === 2}
      <TargetConfiguration
        targets={formData.targets}
        archive_source={formData.archive_source}
        fallback_enabled={formData.fallback_enabled}
        archive_config={formData.archive_config}
        on:update={handleStep2Update}
      />
    {:else if currentStep === 3}
      <ProcessingOptions
        auto_start_scraping={formData.auto_start_scraping}
        enable_attachment_download={formData.enable_attachment_download}
        extract_entities={formData.extract_entities}
        langextractEnabled={formData.langextractEnabled}
        langextractProvider={formData.langextractProvider}
        langextractModel={formData.langextractModel}
        langextractCostEstimate={formData.langextractCostEstimate}
        targets={formData.targets}
        on:update={handleStep3Update}
      />
    {:else if currentStep === 4}
      <ReviewConfirm
        projectName={formData.projectName}
        description={formData.description}
        targets={formData.targets}
        archive_source={formData.archive_source}
        fallback_enabled={formData.fallback_enabled}
        archive_config={formData.archive_config}
        auto_start_scraping={formData.auto_start_scraping}
        enable_attachment_download={formData.enable_attachment_download}
        extract_entities={formData.extract_entities}
        langextractEnabled={formData.langextractEnabled}
        langextractProvider={formData.langextractProvider}
        langextractModel={formData.langextractModel}
        langextractCostEstimate={formData.langextractCostEstimate}
        on:update={handleStep4Update}
      />
    {/if}
  </div>

  <!-- Navigation -->
  <Card>
    <CardContent class="p-6">
      <div class="flex items-center justify-between">
        <!-- Previous Button -->
        <div>
          {#if currentStep > 1}
            <Button variant="outline" onclick={prevStep} class="gap-2">
              <ArrowLeft class="h-4 w-4" />
              Previous
            </Button>
          {:else}
            <Button variant="outline" onclick={() => goto('/projects')} class="gap-2">
              <ArrowLeft class="h-4 w-4" />
              Cancel
            </Button>
          {/if}
        </div>

        <!-- Step Info -->
        <div class="text-center">
          <p class="text-sm text-muted-foreground">
            Step {currentStep} of {totalSteps}
          </p>
        </div>

        <!-- Next/Submit Button -->
        <div>
          {#if currentStep < totalSteps}
            <Button 
              onclick={nextStep} 
              disabled={!canProceed(currentStep)}
              class="gap-2"
            >
              Next
              <ArrowRight class="h-4 w-4" />
            </Button>
          {:else}
            <Button 
              onclick={handleSubmit} 
              disabled={loading || !canProceed(currentStep)}
              class="gap-2 bg-emerald-600 hover:bg-emerald-700"
            >
              {#if loading}
                <div class="animate-spin h-4 w-4 border-2 border-current border-t-transparent rounded-full"></div>
                Creating...
              {:else}
                Create Project
              {/if}
            </Button>
          {/if}
        </div>
      </div>
    </CardContent>
  </Card>
</div>