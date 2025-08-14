<script lang="ts">
    import { goto } from '$app/navigation';
    import { getApiUrl } from '$lib/utils';
    // Auth is handled by hooks.server.ts - no client-side auth check needed
    import { onMount } from 'svelte';
    import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
    import { Button } from '$lib/components/ui/button';
    import { Input } from '$lib/components/ui/input';
    import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
    import { Separator } from '$lib/components/ui/separator';
    import { Badge } from '$lib/components/ui/badge';
    import { Skeleton } from '$lib/components/ui/skeleton';
    import { Plus, Trash2, AlertCircle } from 'lucide-svelte';
    
    let pageLoading = true;
    
    // Server-side auth handles redirects, just show loading state
    onMount(() => {
        // Simulate loading state
        setTimeout(() => {
            pageLoading = false;
        }, 1500);
    });
    
    let targets = [{ value: '', type: 'domain', from_date: '', to_date: '' }]; // Added date ranges
    let enable_attachment_download = true; // New attachment option
    let process_documents = true;
    let config = {
        max_pages: 1000,
        respect_robots_txt: false,
        delay_between_requests: 0,
        user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        extract_entities: true,
        save_screenshots: false,
        follow_redirects: false,
        max_depth: 10
    };
    
    // LangExtract configuration
    let langextractEnabled = false;
    let langextractProvider = 'disabled';
    let langextractModel = '';
    let langextractCostEstimate = null;
    let availableModels = [];
    let loadingModels = false;
    let loadingCostEstimate = false;
    
    let loading = false;
    let error = '';
    
    const addTarget = () => {
        targets = [...targets, { value: '', type: 'domain', from_date: '', to_date: '' }];
    };
    
    const removeTarget = (index: number) => {
        if (targets.length > 1) {
            targets = targets.filter((_, i) => i !== index);
        }
    };
    
    const updateTargetValue = (index: number, value: string) => {
        targets[index].value = processInput(value, targets[index].type);
        targets = [...targets];
    };
    
    const updateTargetType = (index: number, type: 'domain' | 'url') => {
        targets[index].type = type;
        targets[index].value = processInput(targets[index].value, type);
        targets = [...targets];
    };
    
    const processInput = (input: string, type: 'domain' | 'url') => {
        if (!input.trim()) return input;
        
        if (type === 'domain') {
            // Remove protocols, www, and paths - keep just domain
            return input
                .replace(/^https?:\/\//, '')
                .replace(/^www\./, '')
                .split('/')[0]
                .toLowerCase();
        } else {
            // Ensure URL has protocol, validate full URL
            if (!input.startsWith('http://') && !input.startsWith('https://')) {
                return `https://${input}`;
            }
            return input;
        }
    };
    
    const loadAvailableModels = async () => {
        if (availableModels.length > 0) return; // Already loaded
        
        loadingModels = true;
        try {
            const response = await fetch(getApiUrl('/api/v1/projects/langextract/models'), {
                headers: {
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                }
            });
            
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
            const response = await fetch(getApiUrl('/api/v1/projects/langextract/cost-estimate'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                },
                body: JSON.stringify({
                    model_id: langextractModel,
                    targets: validTargets.map(t => t.value),
                    estimated_pages: config.max_pages * validTargets.length
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
    
    const handleSubmit = async () => {
        const validTargets = targets.filter(t => t.value.trim());
        if (validTargets.length === 0) {
            error = 'At least one domain or URL is required';
            return;
        }
        
        loading = true;
        error = '';
        
        try {
            // Use the new simplified endpoint that generates name/description via LLM
            const domains = validTargets.map(t => 
                t.type === 'domain' ? t.value : new URL(t.value).hostname
            );
            
            const response = await fetch(getApiUrl('/api/v1/projects/create-with-domains'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                },
                body: JSON.stringify({
                    project_in: {
                        process_documents: process_documents,
                        enable_attachment_download: enable_attachment_download,
                        langextract_enabled: langextractEnabled,
                        langextract_provider: langextractProvider,
                        langextract_model: langextractModel || null,
                        langextract_estimated_cost_per_1k: langextractCostEstimate?.cost_per_1k_pages || null
                    },
                    domains: domains
                }),
            });
            
            if (response.ok) {
                const project = await response.json();
                
                // Create domains for each target after project creation
                for (const target of validTargets) {
                    try {
                        const domainResponse = await fetch(getApiUrl(`/api/v1/projects/${project.id}/domains`), {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                            },
                            body: JSON.stringify({
                                domain_name: target.type === 'domain' ? target.value : new URL(target.value).hostname,
                                match_type: target.type === 'domain' ? 'domain' : 'prefix',
                                url_path: target.type === 'url' ? new URL(target.value).pathname : null,
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
                
                await goto(`/projects/${project.id}`);
            } else {
                const data = await response.json();
                error = data.detail || 'Failed to create project';
            }
        } catch (err) {
            error = 'Network error occurred';
        } finally {
            loading = false;
        }
    };
</script>

<svelte:head>
    <title>Create Project - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
{#if pageLoading}
    <!-- Loading skeleton form -->
    <div class="max-w-4xl mx-auto space-y-8">
        <div>
            <Skeleton class="h-8 w-64 mb-2" />
            <Skeleton class="h-4 w-96" />
        </div>
        
        <div class="grid gap-6">
            <!-- Basic Information Card Skeleton -->
            <Card>
                <CardHeader>
                    <Skeleton class="h-6 w-48 mb-2" />
                    <Skeleton class="h-4 w-72" />
                </CardHeader>
                <CardContent class="space-y-6">
                    <div class="space-y-2">
                        <Skeleton class="h-4 w-24" />
                        <Skeleton class="h-10 w-full" />
                        <Skeleton class="h-3 w-64" />
                    </div>
                    <div class="space-y-2">
                        <Skeleton class="h-4 w-20" />
                        <Skeleton class="h-20 w-full" />
                        <Skeleton class="h-3 w-80" />
                    </div>
                    <div class="flex items-center space-x-2">
                        <Skeleton class="h-4 w-4" />
                        <Skeleton class="h-4 w-56" />
                    </div>
                </CardContent>
            </Card>
            
            <!-- Domains Card Skeleton -->
            <Card>
                <CardHeader>
                    <Skeleton class="h-6 w-40 mb-2" />
                    <Skeleton class="h-4 w-64" />
                </CardHeader>
                <CardContent class="space-y-4">
                    <div class="flex space-x-3">
                        <div class="flex-1 relative">
                            <div class="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                                <span class="text-muted-foreground text-sm">https://</span>
                            </div>
                            <Skeleton class="h-10 w-full" />
                        </div>
                        <Skeleton class="h-10 w-10" />
                    </div>
                    <Skeleton class="h-10 w-32" />
                </CardContent>
            </Card>
            
            <!-- Configuration Card Skeleton -->
            <Card>
                <CardHeader>
                    <Skeleton class="h-6 w-48 mb-2" />
                    <Skeleton class="h-4 w-56" />
                </CardHeader>
                <CardContent class="space-y-6">
                    <div class="grid grid-cols-2 gap-6">
                        <div class="space-y-2">
                            <Skeleton class="h-4 w-32" />
                            <Skeleton class="h-10 w-full" />
                            <Skeleton class="h-3 w-48" />
                        </div>
                        <div class="space-y-2">
                            <Skeleton class="h-4 w-36" />
                            <Skeleton class="h-10 w-full" />
                            <Skeleton class="h-3 w-52" />
                        </div>
                    </div>
                    <div class="space-y-3">
                        {#each Array(4) as _, i}
                            <div class="flex items-center space-x-2">
                                <Skeleton class="h-4 w-4" />
                                <Skeleton class="h-4 w-{[48, 56, 44, 32][i]}" />
                            </div>
                        {/each}
                    </div>
                </CardContent>
            </Card>
        </div>
        
        <div class="flex justify-end space-x-3">
            <Skeleton class="h-10 w-20" />
            <Skeleton class="h-10 w-32" />
        </div>
    </div>
{:else}
    <!-- Actual form with shadcn-svelte components -->
    <div class="max-w-4xl mx-auto space-y-8">
        <div>
            <h1 class="text-3xl font-bold tracking-tight">Create New Project</h1>
            <p class="text-muted-foreground">
                Set up a new web scraping project to track changes over time. The project name and description will be automatically generated based on your selected domains.
            </p>
        </div>
        
        <form on:submit|preventDefault={handleSubmit} class="space-y-6">
            {#if error}
                <Card class="border-destructive">
                    <CardContent class="p-4">
                        <div class="flex items-start space-x-3">
                            <AlertCircle class="h-5 w-5 text-destructive mt-0.5" />
                            <div>
                                <h3 class="text-sm font-medium text-destructive">Error</h3>
                                <p class="text-sm text-destructive mt-1">{error}</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            {/if}

            <!-- Project Configuration -->
            <Card>
                <CardHeader>
                    <CardTitle>Content Processing Options</CardTitle>
                    <CardDescription>
                        Configure how content should be processed and extracted.
                    </CardDescription>
                </CardHeader>
                <CardContent class="space-y-4">
                    <div class="flex items-center space-x-2">
                        <input
                            id="processDocuments"
                            type="checkbox"
                            bind:checked={process_documents}
                            class="h-4 w-4 text-primary focus:ring-primary border-input rounded"
                        />
                        <label for="processDocuments" class="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                            Enable search indexing for content
                        </label>
                    </div>
                    
                    <div class="flex items-center space-x-2">
                        <input
                            id="enableAttachmentDownload"
                            type="checkbox"
                            bind:checked={enable_attachment_download}
                            class="h-4 w-4 text-primary focus:ring-primary border-input rounded"
                        />
                        <label for="enableAttachmentDownload" class="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                            Download attachments (PDFs, DOCs, etc.)
                        </label>
                    </div>
                    <p class="text-sm text-muted-foreground ml-6">
                        When disabled, only HTML pages will be processed, skipping binary files and documents.
                    </p>
                </CardContent>
            </Card>

            <!-- Targets to Monitor -->
            <Card>
                <CardHeader>
                    <CardTitle>Targets to Monitor</CardTitle>
                    <CardDescription>
                        Add domains or specific URLs to track for changes from the Wayback Machine.
                    </CardDescription>
                </CardHeader>
                <CardContent class="space-y-4">
                    {#each targets as target, index}
                        <div class="space-y-3">
                            <!-- Target Type Toggle -->
                            <div class="flex items-center space-x-4">
                                <span class="text-sm font-medium">Target Type:</span>
                                <div class="flex items-center space-x-2">
                                    <input
                                        id="domain-{index}"
                                        type="radio"
                                        name="target-type-{index}"
                                        value="domain"
                                        checked={target.type === 'domain'}
                                        on:change={() => updateTargetType(index, 'domain')}
                                        class="h-4 w-4 text-primary focus:ring-primary border-input"
                                    />
                                    <label for="domain-{index}" class="text-sm">Entire Domain</label>
                                </div>
                                <div class="flex items-center space-x-2">
                                    <input
                                        id="url-{index}"
                                        type="radio"
                                        name="target-type-{index}"
                                        value="url"
                                        checked={target.type === 'url'}
                                        on:change={() => updateTargetType(index, 'url')}
                                        class="h-4 w-4 text-primary focus:ring-primary border-input"
                                    />
                                    <label for="url-{index}" class="text-sm">Specific URL/Path</label>
                                </div>
                            </div>
                            
                            <!-- Target Input -->
                            <div class="space-y-3">
                                <div class="flex items-start space-x-3">
                                <div class="flex-1">
                                    <label for="target-{index}" class="sr-only">Target {index + 1}</label>
                                    <div class="relative">
                                        {#if target.type === 'domain'}
                                            <div class="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                                                <span class="text-muted-foreground text-sm">https://</span>
                                            </div>
                                            <Input
                                                id="target-{index}"
                                                type="text"
                                                value={target.value}
                                                on:input={(e) => {
                                                    const target = e.target || e.currentTarget;
                                                    if (target) updateTargetValue(index, target.value);
                                                }}
                                                on:paste={(e) => {
                                                    setTimeout(() => {
                                                        const target = e.target || e.currentTarget;
                                                        if (target) updateTargetValue(index, target.value);
                                                    }, 0);
                                                }}
                                                placeholder="example.com"
                                                class="pl-16"
                                                data-testid="target-input-{index}"
                                            />
                                        {:else}
                                            <Input
                                                id="target-{index}"
                                                type="text"
                                                value={target.value}
                                                on:input={(e) => {
                                                    const target = e.target || e.currentTarget;
                                                    if (target) updateTargetValue(index, target.value);
                                                }}
                                                on:paste={(e) => {
                                                    setTimeout(() => {
                                                        const target = e.target || e.currentTarget;
                                                        if (target) updateTargetValue(index, target.value);
                                                    }, 0);
                                                }}
                                                placeholder="https://example.com/specific/path"
                                                data-testid="target-input-{index}"
                                            />
                                        {/if}
                                    </div>
                                    <p class="text-xs text-muted-foreground mt-1">
                                        {#if target.type === 'domain'}
                                            Will capture all pages under this domain (e.g., example.com/*)
                                        {:else}
                                            Will capture only this specific URL or path prefix
                                        {/if}
                                    </p>
                                </div>
                                
                                    {#if targets.length > 1}
                                        <button
                                            type="button"
                                            on:click={(e) => {
                                                e.preventDefault();
                                                removeTarget(index);
                                            }}
                                            class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 hover:bg-accent hover:text-accent-foreground h-10 w-10 text-destructive hover:text-destructive"
                                            title="Remove this target"
                                        >
                                            <Trash2 class="h-4 w-4" />
                                        </button>
                                    {/if}
                                </div>
                                
                                <!-- Date Range Fields -->
                                <div>
                                    <label class="text-xs font-medium text-muted-foreground mb-2 block">Date Range (Optional)</label>
                                    <div class="grid grid-cols-2 gap-2">
                                        <div>
                                            <label for="from-date-{index}" class="sr-only">From Date</label>
                                            <Input
                                                id="from-date-{index}"
                                                type="date"
                                                bind:value={target.from_date}
                                                placeholder="From date"
                                                class="text-sm"
                                            />
                                            <p class="text-xs text-muted-foreground mt-1">From</p>
                                        </div>
                                        <div>
                                            <label for="to-date-{index}" class="sr-only">To Date</label>
                                            <Input
                                                id="to-date-{index}"
                                                type="date"
                                                bind:value={target.to_date}
                                                placeholder="To date"
                                                class="text-sm"
                                            />
                                            <p class="text-xs text-muted-foreground mt-1">To</p>
                                        </div>
                                    </div>
                                    <p class="text-xs text-muted-foreground mt-1">
                                        Filter Wayback Machine snapshots to this date range. Leave empty to get all available snapshots.
                                    </p>
                                                                </div>
                            </div>
                        </div>
                    {/each}

                    <button
                        type="button"
                        on:click={addTarget}
                        class="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2 w-full"
                    >
                        <Plus class="h-4 w-4" />
                        Add Another Target
                    </button>
                </CardContent>
            </Card>


            <!-- LangExtract AI Configuration -->
            <Card>
                <CardHeader>
                    <CardTitle class="flex items-center">
                        AI-Powered Content Extraction
                        <Badge variant="secondary" class="ml-2">Optional</Badge>
                    </CardTitle>
                    <CardDescription>
                        Enable advanced AI extraction for structured data analysis.
                    </CardDescription>
                </CardHeader>
                <CardContent class="space-y-4">
                    <div class="flex items-center space-x-2">
                        <input
                            id="extractEntities"
                            type="checkbox"
                            bind:checked={config.extract_entities}
                            class="h-4 w-4 text-primary focus:ring-primary border-input rounded"
                        />
                        <label for="extractEntities" class="text-sm font-medium leading-none">
                            Extract entities from content
                        </label>
                    </div>
                    
                    <div class="flex items-center space-x-2">
                        <input
                            id="langextractEnabled"
                            type="checkbox"
                            bind:checked={langextractEnabled}
                            class="h-4 w-4 text-primary focus:ring-primary border-input rounded"
                        />
                        <label for="langextractEnabled" class="text-sm font-medium leading-none">
                            Enable LangExtract AI processing
                        </label>
                    </div>

                    {#if langextractEnabled}
                        <div class="space-y-4 pl-6 border-l-2 border-primary/20">
                            <div class="space-y-2">
                                <label for="langextractProvider" class="text-sm font-medium leading-none">
                                    AI Provider
                                </label>
                                <select
                                    id="langextractProvider"
                                    bind:value={langextractProvider}
                                    class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                    <option value="disabled">Disabled</option>
                                    <option value="openrouter">OpenRouter (Recommended)</option>
                                    <option value="openai">OpenAI (Direct)</option>
                                    <option value="anthropic">Anthropic (Direct)</option>
                                    <option value="ollama">Ollama (Local)</option>
                                </select>
                            </div>

                            {#if langextractProvider === 'openrouter'}
                                <div class="space-y-2">
                                    <label for="langextractModel" class="text-sm font-medium leading-none">
                                        AI Model
                                    </label>
                                    <select
                                        id="langextractModel"
                                        bind:value={langextractModel}
                                        class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                        disabled={loadingModels}
                                    >
                                        <option value="">Select a model...</option>
                                        {#each availableModels as model}
                                            <option value={model.id}>
                                                {model.name} - ${model.pricing.estimated_per_1k_pages}/1k pages ({model.provider})
                                            </option>
                                        {/each}
                                    </select>
                                    {#if loadingModels}
                                        <p class="text-sm text-muted-foreground">Loading available models...</p>
                                    {/if}
                                </div>

                                {#if langextractCostEstimate}
                                    <Card>
                                        <CardHeader class="pb-3">
                                            <CardTitle class="text-base">Cost Estimate</CardTitle>
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
                                                    <p class="font-semibold">${langextractCostEstimate.total_estimated_cost}</p>
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                {:else if loadingCostEstimate}
                                    <Card>
                                        <CardContent class="p-4">
                                            <p class="text-sm text-muted-foreground">Calculating cost estimate...</p>
                                        </CardContent>
                                    </Card>
                                {/if}
                            {/if}

                            {#if langextractProvider !== 'disabled' && langextractProvider !== 'openrouter'}
                                <Card class="border-yellow-200 bg-yellow-50">
                                    <CardContent class="p-4">
                                        <p class="text-sm text-yellow-800">
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

            <!-- Submit Actions -->
            <div class="flex justify-end space-x-3">
                <Button type="button" variant="outline" onclick={() => goto('/projects')}>
                    Cancel
                </Button>
                
                <Button type="submit" disabled={loading} data-testid="create-project-button">
                    {#if loading}
                        <div class="animate-spin -ml-1 mr-3 h-5 w-5 border-2 border-current border-t-transparent rounded-full"></div>
                        Creating...
                    {:else}
                        Create Project
                    {/if}
                </Button>
            </div>
        </form>
    </div>
{/if}
</DashboardLayout>

