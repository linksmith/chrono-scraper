<script lang="ts">
    import { onMount } from 'svelte';
    import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
    import { Skeleton } from '$lib/components/ui/skeleton';
    import MultiStepProjectForm from './components/MultiStepProjectForm.svelte';
    
    let pageLoading = true;
    
    // Server-side auth handles redirects, just show loading state
    onMount(() => {
        // Simulate loading state
        setTimeout(() => {
            pageLoading = false;
        }, 1000);
    });
</script>

<svelte:head>
    <title>Create Project - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
{#if pageLoading}
    <!-- Loading skeleton -->
    <div class="max-w-4xl mx-auto space-y-8">
        <div class="flex items-center justify-center min-h-[400px]">
            <div class="space-y-4 text-center">
                <div class="animate-spin h-8 w-8 border-2 border-emerald-500 border-t-transparent rounded-full mx-auto"></div>
                <p class="text-muted-foreground">Loading project creation form...</p>
            </div>
        </div>
    </div>
{:else}
    <!-- Modern Multi-Step Form -->
    <div class="space-y-8">
        <div class="text-center space-y-2">
            <h1 class="text-4xl font-bold font-space-grotesk text-emerald-600">Create New Project</h1>
            <p class="text-lg text-muted-foreground max-w-2xl mx-auto">
                Set up a web scraping project step-by-step
            </p>
        </div>
        
        <MultiStepProjectForm />
    </div>
{/if}
</DashboardLayout>

