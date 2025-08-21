<script lang="ts">
  import { Progress } from '$lib/components/ui/progress';
  import { Check } from 'lucide-svelte';

  export let currentStep: number;
  export let totalSteps: number = 4;

  const steps = [
    { number: 1, title: 'Project Details', description: 'Name and description' },
    { number: 2, title: 'Target Configuration', description: 'URLs and domains to scrape' },
    { number: 3, title: 'Processing Options', description: 'Content processing settings' },
    { number: 4, title: 'Review & Confirm', description: 'Verify your settings' }
  ];

  $: progressValue = (currentStep / totalSteps) * 100;
</script>

<div class="w-full space-y-6">
  <!-- Progress Bar -->
  <div class="space-y-2">
    <div class="flex justify-between text-sm font-medium text-muted-foreground">
      <span>Step {currentStep} of {totalSteps}</span>
      <span>{Math.round(progressValue)}% Complete</span>
    </div>
    <Progress value={progressValue} max={100} class="w-full h-2" />
  </div>

  <!-- Step Indicators -->
  <div class="hidden sm:block">
    <div class="flex items-center justify-between">
      {#each steps as step}
        <div class="flex flex-col items-center space-y-2 flex-1">
          <!-- Step Circle -->
          <div class="relative">
            {#if step.number < currentStep}
              <!-- Completed Step -->
              <div class="w-10 h-10 bg-emerald-500 rounded-full flex items-center justify-center">
                <Check class="w-5 h-5 text-white" />
              </div>
            {:else if step.number === currentStep}
              <!-- Current Step -->
              <div class="w-10 h-10 bg-emerald-500 rounded-full flex items-center justify-center border-4 border-emerald-100">
                <span class="text-sm font-semibold text-white">{step.number}</span>
              </div>
            {:else}
              <!-- Future Step -->
              <div class="w-10 h-10 bg-muted rounded-full flex items-center justify-center border-2 border-border">
                <span class="text-sm font-medium text-muted-foreground">{step.number}</span>
              </div>
            {/if}

            <!-- Connecting Line (not for last step) -->
            {#if step.number < totalSteps}
              <div class="absolute top-5 left-10 w-full h-0.5 
                          {step.number < currentStep ? 'bg-emerald-500' : 'bg-border'}">
              </div>
            {/if}
          </div>

          <!-- Step Title and Description -->
          <div class="text-center min-w-0 px-2">
            <p class="text-sm font-medium 
                     {step.number <= currentStep ? 'text-emerald-600' : 'text-muted-foreground'}">
              {step.title}
            </p>
            <p class="text-xs text-muted-foreground mt-1">
              {step.description}
            </p>
          </div>
        </div>
      {/each}
    </div>
  </div>

  <!-- Mobile Step Indicator -->
  <div class="sm:hidden">
    <div class="text-center space-y-1">
      <h3 class="text-lg font-semibold font-space-grotesk text-emerald-600">
        {steps[currentStep - 1].title}
      </h3>
      <p class="text-sm text-muted-foreground">
        {steps[currentStep - 1].description}
      </p>
    </div>
  </div>
</div>