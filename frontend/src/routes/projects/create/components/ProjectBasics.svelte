<script lang="ts">
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Input } from '$lib/components/ui/input';
  import { Label } from '$lib/components/ui/label';
  import { Textarea } from '$lib/components/ui/textarea';
  import { createEventDispatcher } from 'svelte';

  const dispatch = createEventDispatcher();

  export let projectName = '';
  export let description = '';

  // Validation - only project name is required
  $: isValid = projectName.trim().length >= 3;


  // Character limits
  const nameMaxLength = 100;
  const descriptionMaxLength = 500;

  $: nameCharCount = projectName.length;
  $: descriptionCharCount = description.length;

  // Dispatch changes to parent
  $: dispatch('update', { projectName, description, isValid });
</script>

<div class="space-y-4 sm:space-y-6">
  <div class="text-center space-y-2 px-2 sm:px-0">
    <h2 class="text-xl sm:text-2xl font-bold font-space-grotesk text-emerald-600">
      Let's Start Your Project
    </h2>
    <p class="text-sm sm:text-base text-muted-foreground">
      Give your project a descriptive name and tell us what you're investigating
    </p>
  </div>

  <Card class="shadow-sm">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <div class="w-8 h-8 bg-emerald-100 rounded-full flex items-center justify-center">
          <span class="text-emerald-600 font-semibold">1</span>
        </div>
        Project Information
      </CardTitle>
      <CardDescription>
        This information helps organize and identify your investigation
      </CardDescription>
    </CardHeader>
    <CardContent class="space-y-4 sm:space-y-6 p-4 sm:p-6">
      <!-- Project Name -->
      <div class="space-y-2">
        <Label for="projectName" class="text-base font-medium">
          Project Name *
        </Label>
        <Input 
          id="projectName"
          bind:value={projectName}
          placeholder="e.g., Corporate Investigation 2024"
          maxlength={nameMaxLength}
          class="text-base"
        />
        <div class="flex justify-between text-xs text-muted-foreground">
          <span>Minimum 3 characters required</span>
          <span class="{nameCharCount > nameMaxLength * 0.9 ? 'text-amber-600' : ''}">
            {nameCharCount}/{nameMaxLength}
          </span>
        </div>
      </div>

      <!-- Description -->
      <div class="space-y-2">
        <Label for="description" class="text-base font-medium">
          Project Description
        </Label>
        <Textarea 
          id="description"
          bind:value={description}
          placeholder="Describe the purpose of this investigation, what you're looking for, and any context that might be helpful..."
          maxlength={descriptionMaxLength}
          class="min-h-[100px] text-base"
        />
        <div class="flex justify-between text-xs text-muted-foreground">
          <span>Optional - provide additional context if helpful</span>
          <span class="{descriptionCharCount > descriptionMaxLength * 0.9 ? 'text-amber-600' : ''}">
            {descriptionCharCount}/{descriptionMaxLength}
          </span>
        </div>
      </div>

    </CardContent>
  </Card>
</div>

<style>
  /* Custom focus styles for inputs */
  :global(.focus\:ring-emerald-500:focus) {
    --tw-ring-color: rgb(16 185 129);
  }
</style>