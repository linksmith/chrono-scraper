<script lang="ts">
    import { goto } from '$app/navigation';
    import { getApiUrl } from '$lib/utils';
    import { isAuthenticated } from '$lib/stores/auth';
    import { onMount } from 'svelte';
    
    // Redirect if not authenticated
    onMount(() => {
        if (!$isAuthenticated) {
            goto('/auth/login?redirect=/projects/create');
        }
    });
    
    let name = '';
    let description = '';
    let domains = [''];
    let isPublic = false;
    let config = {
        max_pages: 1000,
        respect_robots_txt: true,
        delay_between_requests: 1000,
        user_agent: 'chrono-scraper/2.0 (research tool)',
        extract_entities: true,
        save_screenshots: false,
        follow_redirects: true,
        max_depth: 5
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
    
    const addDomain = () => {
        domains = [...domains, ''];
    };
    
    const removeDomain = (index: number) => {
        if (domains.length > 1) {
            domains = domains.filter((_, i) => i !== index);
        }
    };
    
    const updateDomain = (index: number, value: string) => {
        domains[index] = value;
        domains = [...domains];
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
        
        const validDomains = domains.filter(d => d.trim());
        if (validDomains.length === 0) return;
        
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
                    domains: validDomains,
                    estimated_pages: config.max_pages * validDomains.length
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
    
    $: if (langextractModel && domains.length > 0) {
        calculateCostEstimate();
    }
    
    const handleSubmit = async () => {
        // Validate form
        if (!name.trim()) {
            error = 'Project name is required';
            return;
        }
        
        const validDomains = domains.filter(d => d.trim());
        if (validDomains.length === 0) {
            error = 'At least one domain is required';
            return;
        }
        
        loading = true;
        error = '';
        
        try {
            const response = await fetch(getApiUrl('/api/v1/projects/'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
                },
                body: JSON.stringify({
                    name: name.trim(),
                    description: description.trim() || null,
                    process_documents: true,
                    langextract_enabled: langextractEnabled,
                    langextract_provider: langextractProvider,
                    langextract_model: langextractModel || null,
                    langextract_estimated_cost_per_1k: langextractCostEstimate?.cost_per_1k_pages || null,
                    config: {
                        ...config,
                        domains: validDomains
                    }
                }),
            });
            
            if (response.ok) {
                const project = await response.json();
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

<div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
    <div class="mb-8">
        <nav class="flex" aria-label="Breadcrumb">
            <ol class="flex items-center space-x-4">
                <li>
                    <div>
                        <a href="/projects" class="text-gray-400 hover:text-gray-500">
                            Projects
                        </a>
                    </div>
                </li>
                <li>
                    <div class="flex items-center">
                        <svg class="flex-shrink-0 h-5 w-5 text-gray-300" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd" />
                        </svg>
                        <span class="ml-4 text-sm font-medium text-gray-500">Create Project</span>
                    </div>
                </li>
            </ol>
        </nav>
        
        <div class="mt-4">
            <h1 class="text-3xl font-bold text-gray-900">Create New Project</h1>
            <p class="mt-2 text-gray-600">Set up a new web scraping project to track changes over time.</p>
        </div>
    </div>

    <div class="bg-white shadow rounded-lg">
        <form class="space-y-8 p-6" on:submit|preventDefault={handleSubmit}>
            {#if error}
                <div class="rounded-md bg-red-50 p-4">
                    <div class="flex">
                        <div class="flex-shrink-0">
                            <svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                            </svg>
                        </div>
                        <div class="ml-3">
                            <h3 class="text-sm font-medium text-red-800">Error</h3>
                            <div class="mt-2 text-sm text-red-700">
                                <p>{error}</p>
                            </div>
                        </div>
                    </div>
                </div>
            {/if}

            <!-- Basic Information -->
            <div class="space-y-6">
                <div>
                    <h2 class="text-lg font-medium text-gray-900">Basic Information</h2>
                    <p class="mt-1 text-sm text-gray-600">Provide basic details about your project.</p>
                </div>

                <div class="grid grid-cols-1 gap-6">
                    <div>
                        <label for="name" class="block text-sm font-medium text-gray-700">
                            Project Name *
                        </label>
                        <input
                            id="name"
                            type="text"
                            bind:value={name}
                            required
                            class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                            placeholder="My Research Project"
                            data-testid="project-name-input"
                        />
                        <p class="mt-2 text-sm text-gray-500">A descriptive name for your project.</p>
                    </div>

                    <div>
                        <label for="description" class="block text-sm font-medium text-gray-700">
                            Description
                        </label>
                        <textarea
                            id="description"
                            bind:value={description}
                            rows="3"
                            class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                            placeholder="Describe what this project is for and what you're researching..."
                        ></textarea>
                        <p class="mt-2 text-sm text-gray-500">Optional description of your project goals and methodology.</p>
                    </div>

                    <div class="flex items-center">
                        <input
                            id="isPublic"
                            type="checkbox"
                            bind:checked={isPublic}
                            class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                        />
                        <label for="isPublic" class="ml-2 block text-sm text-gray-900">
                            Make this project publicly visible
                        </label>
                    </div>
                </div>
            </div>

            <!-- Domains to Monitor -->
            <div class="space-y-6">
                <div>
                    <h2 class="text-lg font-medium text-gray-900">Domains to Monitor</h2>
                    <p class="mt-1 text-sm text-gray-600">Add the websites you want to track for changes.</p>
                </div>

                <div class="space-y-4">
                    {#each domains as domain, index}
                        <div class="flex items-center space-x-3">
                            <div class="flex-1">
                                <label for="domain-{index}" class="sr-only">Domain {index + 1}</label>
                                <input
                                    id="domain-{index}"
                                    type="url"
                                    value={domain}
                                    on:input={(e) => updateDomain(index, e.target.value)}
                                    class="block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                    placeholder="https://example.com"
                                    data-testid="domain-input-{index}"
                                />
                            </div>
                            
                            {#if domains.length > 1}
                                <button
                                    type="button"
                                    on:click={() => removeDomain(index)}
                                    class="inline-flex items-center p-2 border border-transparent rounded-md text-red-600 hover:bg-red-50"
                                >
                                    <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                    </svg>
                                </button>
                            {/if}
                        </div>
                    {/each}

                    <button
                        type="button"
                        on:click={addDomain}
                        class="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                    >
                        <svg class="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                        </svg>
                        Add Another Domain
                    </button>
                </div>
            </div>

            <!-- Scraping Configuration -->
            <div class="space-y-6">
                <div>
                    <h2 class="text-lg font-medium text-gray-900">Scraping Configuration</h2>
                    <p class="mt-1 text-sm text-gray-600">Configure how the scraper should behave.</p>
                </div>

                <div class="grid grid-cols-1 gap-6 sm:grid-cols-2">
                    <div>
                        <label for="maxPages" class="block text-sm font-medium text-gray-700">
                            Max Pages to Scrape
                        </label>
                        <input
                            id="maxPages"
                            type="number"
                            bind:value={config.max_pages}
                            min="1"
                            max="100000"
                            class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                        />
                        <p class="mt-1 text-xs text-gray-500">Limit the number of pages to scrape per domain.</p>
                    </div>

                    <div>
                        <label for="maxDepth" class="block text-sm font-medium text-gray-700">
                            Maximum Crawl Depth
                        </label>
                        <input
                            id="maxDepth"
                            type="number"
                            bind:value={config.max_depth}
                            min="1"
                            max="10"
                            class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                        />
                        <p class="mt-1 text-xs text-gray-500">How many links deep to follow from the starting URL.</p>
                    </div>

                    <div>
                        <label for="delay" class="block text-sm font-medium text-gray-700">
                            Delay Between Requests (ms)
                        </label>
                        <input
                            id="delay"
                            type="number"
                            bind:value={config.delay_between_requests}
                            min="100"
                            max="10000"
                            step="100"
                            class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                        />
                        <p class="mt-1 text-xs text-gray-500">Delay to be respectful to target servers.</p>
                    </div>

                    <div>
                        <label for="userAgent" class="block text-sm font-medium text-gray-700">
                            User Agent
                        </label>
                        <input
                            id="userAgent"
                            type="text"
                            bind:value={config.user_agent}
                            class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                        />
                        <p class="mt-1 text-xs text-gray-500">User agent string to identify your scraper.</p>
                    </div>
                </div>

                <div class="space-y-4">
                    <div class="flex items-center">
                        <input
                            id="respectRobots"
                            type="checkbox"
                            bind:checked={config.respect_robots_txt}
                            class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                        />
                        <label for="respectRobots" class="ml-2 block text-sm text-gray-900">
                            Respect robots.txt files
                        </label>
                    </div>

                    <div class="flex items-center">
                        <input
                            id="extractEntities"
                            type="checkbox"
                            bind:checked={config.extract_entities}
                            class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                        />
                        <label for="extractEntities" class="ml-2 block text-sm text-gray-900">
                            Extract entities from content
                        </label>
                    </div>

                    <div class="flex items-center">
                        <input
                            id="saveScreenshots"
                            type="checkbox"
                            bind:checked={config.save_screenshots}
                            class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                        />
                        <label for="saveScreenshots" class="ml-2 block text-sm text-gray-900">
                            Save screenshots of pages
                        </label>
                    </div>

                    <div class="flex items-center">
                        <input
                            id="followRedirects"
                            type="checkbox"
                            bind:checked={config.follow_redirects}
                            class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                        />
                        <label for="followRedirects" class="ml-2 block text-sm text-gray-900">
                            Follow redirects
                        </label>
                    </div>
                </div>
            </div>

            <!-- LangExtract AI Configuration -->
            <div class="space-y-6">
                <div>
                    <h2 class="text-lg font-medium text-gray-900">AI-Powered Content Extraction</h2>
                    <p class="mt-1 text-sm text-gray-600">Enable advanced AI extraction for structured data analysis (optional).</p>
                </div>

                <div class="flex items-center">
                    <input
                        id="langextractEnabled"
                        type="checkbox"
                        bind:checked={langextractEnabled}
                        class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                    />
                    <label for="langextractEnabled" class="ml-2 block text-sm text-gray-900">
                        Enable LangExtract AI processing
                    </label>
                </div>

                {#if langextractEnabled}
                    <div class="space-y-4 pl-6 border-l-2 border-blue-200">
                        <!-- Provider Selection -->
                        <div>
                            <label for="langextractProvider" class="block text-sm font-medium text-gray-700">
                                AI Provider
                            </label>
                            <select
                                id="langextractProvider"
                                bind:value={langextractProvider}
                                class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                            >
                                <option value="disabled">Disabled</option>
                                <option value="openrouter">OpenRouter (Recommended)</option>
                                <option value="openai">OpenAI (Direct)</option>
                                <option value="anthropic">Anthropic (Direct)</option>
                                <option value="ollama">Ollama (Local)</option>
                            </select>
                        </div>

                        {#if langextractProvider === 'openrouter'}
                            <!-- Model Selection -->
                            <div>
                                <label for="langextractModel" class="block text-sm font-medium text-gray-700">
                                    AI Model
                                </label>
                                <select
                                    id="langextractModel"
                                    bind:value={langextractModel}
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
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
                                    <p class="mt-1 text-xs text-gray-500">Loading available models...</p>
                                {/if}
                            </div>

                            {#if langextractCostEstimate}
                                <!-- Cost Estimate -->
                                <div class="bg-blue-50 p-4 rounded-md">
                                    <h4 class="text-sm font-medium text-blue-900 mb-2">Cost Estimate</h4>
                                    <div class="text-sm text-blue-800 space-y-1">
                                        <p><strong>Model:</strong> {langextractCostEstimate.model.name}</p>
                                        <p><strong>Estimated Pages:</strong> {langextractCostEstimate.estimated_pages.toLocaleString()}</p>
                                        <p><strong>Cost per 1k pages:</strong> ${langextractCostEstimate.cost_per_1k_pages}</p>
                                        <p class="font-semibold"><strong>Total Estimated Cost:</strong> ${langextractCostEstimate.total_estimated_cost}</p>
                                    </div>
                                    <details class="mt-2">
                                        <summary class="text-xs text-blue-700 cursor-pointer">View breakdown</summary>
                                        <div class="mt-1 text-xs text-blue-600 space-y-1">
                                            <p>Input tokens: {langextractCostEstimate.breakdown.input_tokens.toLocaleString()}</p>
                                            <p>Output tokens: {langextractCostEstimate.breakdown.output_tokens.toLocaleString()}</p>
                                            <p>Input cost: ${langextractCostEstimate.breakdown.input_cost}</p>
                                            <p>Output cost: ${langextractCostEstimate.breakdown.output_cost}</p>
                                        </div>
                                    </details>
                                </div>
                            {:else if loadingCostEstimate}
                                <div class="bg-gray-50 p-4 rounded-md">
                                    <p class="text-sm text-gray-600">Calculating cost estimate...</p>
                                </div>
                            {/if}
                        {/if}

                        {#if langextractProvider !== 'disabled' && langextractProvider !== 'openrouter'}
                            <div class="bg-yellow-50 p-4 rounded-md">
                                <p class="text-sm text-yellow-800">
                                    <strong>Note:</strong> Direct provider integration requires API keys to be configured in your environment.
                                    OpenRouter is recommended for easier setup and access to multiple models.
                                </p>
                            </div>
                        {/if}
                    </div>
                {/if}
            </div>

            <!-- Submit -->
            <div class="flex justify-end space-x-3 pt-6 border-t border-gray-200">
                <button
                    type="button"
                    on:click={() => goto('/projects')}
                    class="inline-flex justify-center py-2 px-4 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                    Cancel
                </button>
                
                <button
                    type="submit"
                    disabled={loading}
                    class="inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
                    data-testid="create-project-button"
                >
                    {#if loading}
                        <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Creating...
                    {:else}
                        Create Project
                    {/if}
                </button>
            </div>
        </form>
    </div>
</div>

<style>
    input, textarea, select {
        border: 1px solid #d1d5db;
        border-radius: 0.375rem;
        padding: 0.5rem 0.75rem;
        font-size: 0.875rem;
        line-height: 1.25rem;
    }
    
    input:focus, textarea:focus, select:focus {
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
    }
</style>