<script lang="ts">
    import { Checkbox } from "$lib/components/ui/checkbox";
    import { Slider } from "$lib/components/ui/slider";
    import { Badge } from "$lib/components/ui/badge";
    import { Button } from "$lib/components/ui/button";
    import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "$lib/components/ui/collapsible";
    import { 
        FileText, 
        Languages, 
        Type, 
        Hash,
        ChevronDown,
        ChevronRight,
        X 
    } from "lucide-svelte";
    import { filters, type FilterState } from "$lib/stores/filters";
    import { onMount } from "svelte";
    
    export let contentTypes: string[] = [];
    export let languages: string[] = [];
    export let wordCount: [number | null, number | null] = [null, null];
    export let hasTitle: boolean | null = null;
    export let hasAuthor: boolean | null = null;
    
    // Available options from facets
    let availableContentTypes: { name: string; count: number }[] = [];
    let availableLanguages: { name: string; code: string; count: number }[] = [];
    
    // Section expansion state
    let contentTypesExpanded = false;
    let languagesExpanded = false;
    let wordCountExpanded = false;
    let metadataExpanded = false;
    
    // Word count settings
    const MIN_WORD_COUNT = 0;
    const MAX_WORD_COUNT = 10000;
    let wordCountSlider: number[] = [MIN_WORD_COUNT, MAX_WORD_COUNT];
    
    // Common content types
    const commonContentTypes = [
        { name: 'text/html', label: 'Web Pages', icon: '🌐' },
        { name: 'application/pdf', label: 'PDF Documents', icon: '📄' },
        { name: 'text/plain', label: 'Text Files', icon: '📝' },
        { name: 'application/json', label: 'JSON Data', icon: '🔧' },
        { name: 'text/xml', label: 'XML Documents', icon: '📋' },
        { name: 'text/csv', label: 'CSV Files', icon: '📊' }
    ];
    
    // Common languages
    const commonLanguages = [
        { code: 'en', name: 'English' },
        { code: 'es', name: 'Spanish' },
        { code: 'fr', name: 'French' },
        { code: 'de', name: 'German' },
        { code: 'zh', name: 'Chinese' },
        { code: 'ja', name: 'Japanese' },
        { code: 'ar', name: 'Arabic' },
        { code: 'ru', name: 'Russian' }
    ];
    
    onMount(async () => {
        await loadContentFacets();
        updateWordCountSlider();
    });
    
    async function loadContentFacets() {
        try {
            const response = await fetch('/api/v1/search/facets', {
                credentials: 'include'
            });
            
            if (response.ok) {
                const data = await response.json();
                
                if (data.content_types) {
                    availableContentTypes = Object.entries(data.content_types).map(([name, count]) => ({
                        name,
                        count: count as number
                    }));
                }
                
                if (data.languages) {
                    availableLanguages = Object.entries(data.languages).map(([code, count]) => {
                        const langInfo = commonLanguages.find(l => l.code === code);
                        return {
                            code,
                            name: langInfo?.name || code.toUpperCase(),
                            count: count as number
                        };
                    });
                }
            }
        } catch (error) {
            console.error('Failed to load content facets:', error);
        }
    }
    
    function updateWordCountSlider() {
        if (wordCount[0] !== null || wordCount[1] !== null) {
            wordCountSlider = [
                wordCount[0] ?? MIN_WORD_COUNT,
                wordCount[1] ?? MAX_WORD_COUNT
            ];
        }
    }
    
    function handleContentTypeChange(contentType: string, checked: boolean) {
        if (checked) {
            contentTypes = [...contentTypes, contentType];
        } else {
            contentTypes = contentTypes.filter(ct => ct !== contentType);
        }
        
        filters.update(f => ({
            ...f,
            contentTypes
        }));
    }
    
    function handleLanguageChange(languageCode: string, checked: boolean) {
        if (checked) {
            languages = [...languages, languageCode];
        } else {
            languages = languages.filter(l => l !== languageCode);
        }
        
        filters.update(f => ({
            ...f,
            languages
        }));
    }
    
    function handleWordCountChange(values: number[]) {
        const [min, max] = values;
        const newWordCount: [number | null, number | null] = [
            min > MIN_WORD_COUNT ? min : null,
            max < MAX_WORD_COUNT ? max : null
        ];
        
        wordCount = newWordCount;
        
        filters.update(f => ({
            ...f,
            wordCount: newWordCount
        }));
    }
    
    function handleMetadataChange(field: 'hasTitle' | 'hasAuthor', value: boolean | null) {
        if (field === 'hasTitle') {
            hasTitle = value;
        } else {
            hasAuthor = value;
        }
        
        filters.update(f => ({
            ...f,
            [field]: value
        }));
    }
    
    function clearContentTypes() {
        contentTypes = [];
        filters.update(f => ({ ...f, contentTypes: [] }));
    }
    
    function clearLanguages() {
        languages = [];
        filters.update(f => ({ ...f, languages: [] }));
    }
    
    function clearWordCount() {
        wordCount = [null, null];
        wordCountSlider = [MIN_WORD_COUNT, MAX_WORD_COUNT];
        filters.update(f => ({ ...f, wordCount: [null, null] }));
    }
    
    function clearMetadata() {
        hasTitle = null;
        hasAuthor = null;
        filters.update(f => ({ ...f, hasTitle: null, hasAuthor: null }));
    }
    
    function formatWordCount(): string {
        const [min, max] = wordCount;
        if (min !== null && max !== null) {
            return `${min.toLocaleString()} - ${max.toLocaleString()} words`;
        } else if (min !== null) {
            return `${min.toLocaleString()}+ words`;
        } else if (max !== null) {
            return `Up to ${max.toLocaleString()} words`;
        }
        return 'Any length';
    }
    
    $: hasContentFilters = contentTypes.length > 0 || languages.length > 0 || 
                          wordCount[0] !== null || wordCount[1] !== null ||
                          hasTitle !== null || hasAuthor !== null;
</script>

<div class="space-y-4">
    <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
            <FileText class="h-4 w-4 text-muted-foreground" />
            <span class="text-sm font-medium">Content</span>
            {#if hasContentFilters}
                <Badge variant="secondary" class="text-xs">
                    Active
                </Badge>
            {/if}
        </div>
    </div>
    
    <!-- Content Types -->
    <Collapsible bind:open={contentTypesExpanded}>
        <CollapsibleTrigger asChild>
            <button 
                type="button"
                class="w-full flex items-center justify-between h-8 px-0 hover:bg-accent hover:text-accent-foreground rounded-md transition-colors"
            >
                <div class="flex items-center space-x-2">
                    <Type class="h-3 w-3" />
                    <span class="text-xs">Content Types</span>
                    {#if contentTypes.length > 0}
                        <Badge variant="outline" class="text-xs h-4 px-1">
                            {contentTypes.length}
                        </Badge>
                    {/if}
                </div>
                {#if contentTypesExpanded}
                    <ChevronDown class="h-3 w-3" />
                {:else}
                    <ChevronRight class="h-3 w-3" />
                {/if}
            </button>
        </CollapsibleTrigger>
        <CollapsibleContent class="space-y-2 pt-2">
            {#if contentTypes.length > 0}
                <div class="flex items-center justify-between">
                    <span class="text-xs text-muted-foreground">Selected:</span>
                    <Button
                        variant="ghost"
                        size="sm"
                        onclick={clearContentTypes}
                        class="h-6 px-2 text-xs"
                    >
                        Clear
                    </Button>
                </div>
                <div class="flex flex-wrap gap-1">
                    {#each contentTypes as contentType}
                        <Badge variant="secondary" class="text-xs">
                            {commonContentTypes.find(ct => ct.name === contentType)?.label || contentType}
                            <button
                                type="button"
                                onclick={() => handleContentTypeChange(contentType, false)}
                                class="ml-1 h-3 w-3 p-0 hover:bg-red-100 rounded-sm transition-colors flex items-center justify-center"
                                aria-label="Remove {contentType} filter"
                            >
                                <X class="h-2 w-2" />
                            </button>
                        </Badge>
                    {/each}
                </div>
            {/if}
            
            <div class="space-y-2">
                {#each (availableContentTypes.length > 0 ? availableContentTypes : commonContentTypes) as contentType}
                    <div class="flex items-center space-x-2">
                        <Checkbox
                            id="content-{contentType.name}"
                            checked={contentTypes.includes(contentType.name)}
                            onCheckedChange={(checked) => handleContentTypeChange(contentType.name, checked)}
                        />
                        <label for="content-{contentType.name}" class="text-xs cursor-pointer flex-1">
                            {#if 'icon' in contentType}
                                <span class="mr-1">{contentType.icon}</span>
                            {/if}
                            {contentType.label || contentType.name}
                        </label>
                        {#if 'count' in contentType && contentType.count}
                            <Badge variant="outline" class="text-xs h-4 px-1">
                                {contentType.count}
                            </Badge>
                        {/if}
                    </div>
                {/each}
            </div>
        </CollapsibleContent>
    </Collapsible>
    
    <!-- Languages -->
    <Collapsible bind:open={languagesExpanded}>
        <CollapsibleTrigger asChild>
            <button 
                type="button"
                class="w-full flex items-center justify-between h-8 px-0 hover:bg-accent hover:text-accent-foreground rounded-md transition-colors"
            >
                <div class="flex items-center space-x-2">
                    <Languages class="h-3 w-3" />
                    <span class="text-xs">Languages</span>
                    {#if languages.length > 0}
                        <Badge variant="outline" class="text-xs h-4 px-1">
                            {languages.length}
                        </Badge>
                    {/if}
                </div>
                {#if languagesExpanded}
                    <ChevronDown class="h-3 w-3" />
                {:else}
                    <ChevronRight class="h-3 w-3" />
                {/if}
            </button>
        </CollapsibleTrigger>
        <CollapsibleContent class="space-y-2 pt-2">
            {#if languages.length > 0}
                <div class="flex items-center justify-between">
                    <span class="text-xs text-muted-foreground">Selected:</span>
                    <Button
                        variant="ghost"
                        size="sm"
                        onclick={clearLanguages}
                        class="h-6 px-2 text-xs"
                    >
                        Clear
                    </Button>
                </div>
                <div class="flex flex-wrap gap-1">
                    {#each languages as languageCode}
                        {@const langInfo = commonLanguages.find(l => l.code === languageCode)}
                        <Badge variant="secondary" class="text-xs">
                            {langInfo?.name || languageCode.toUpperCase()}
                            <button
                                type="button"
                                onclick={() => handleLanguageChange(languageCode, false)}
                                class="ml-1 h-3 w-3 p-0 hover:bg-red-100 rounded-sm transition-colors flex items-center justify-center"
                                aria-label="Remove {languageCode} language filter"
                            >
                                <X class="h-2 w-2" />
                            </button>
                        </Badge>
                    {/each}
                </div>
            {/if}
            
            <div class="space-y-2">
                {#each (availableLanguages.length > 0 ? availableLanguages : commonLanguages) as language}
                    <div class="flex items-center space-x-2">
                        <Checkbox
                            id="lang-{language.code}"
                            checked={languages.includes(language.code)}
                            onCheckedChange={(checked) => handleLanguageChange(language.code, checked)}
                        />
                        <label for="lang-{language.code}" class="text-xs cursor-pointer flex-1">
                            {language.name}
                        </label>
                        {#if 'count' in language && language.count}
                            <Badge variant="outline" class="text-xs h-4 px-1">
                                {language.count}
                            </Badge>
                        {/if}
                    </div>
                {/each}
            </div>
        </CollapsibleContent>
    </Collapsible>
    
    <!-- Word Count -->
    <Collapsible bind:open={wordCountExpanded}>
        <CollapsibleTrigger asChild>
            <button 
                type="button"
                class="w-full flex items-center justify-between h-8 px-0 hover:bg-accent hover:text-accent-foreground rounded-md transition-colors"
            >
                <div class="flex items-center space-x-2">
                    <Hash class="h-3 w-3" />
                    <span class="text-xs">Word Count</span>
                    {#if wordCount[0] !== null || wordCount[1] !== null}
                        <Badge variant="outline" class="text-xs h-4 px-1">
                            Set
                        </Badge>
                    {/if}
                </div>
                {#if wordCountExpanded}
                    <ChevronDown class="h-3 w-3" />
                {:else}
                    <ChevronRight class="h-3 w-3" />
                {/if}
            </button>
        </CollapsibleTrigger>
        <CollapsibleContent class="space-y-3 pt-2">
            {#if wordCount[0] !== null || wordCount[1] !== null}
                <div class="flex items-center justify-between">
                    <Badge variant="secondary" class="text-xs">
                        {formatWordCount()}
                    </Badge>
                    <Button
                        variant="ghost"
                        size="sm"
                        onclick={clearWordCount}
                        class="h-6 px-2 text-xs"
                    >
                        Clear
                    </Button>
                </div>
            {/if}
            
            <div class="space-y-2">
                <Slider
                    type="multiple"
                    bind:value={wordCountSlider}
                    max={MAX_WORD_COUNT}
                    step={100}
                    onValueChange={handleWordCountChange}
                    class="w-full"
                />
                <div class="flex justify-between text-xs text-muted-foreground">
                    <span>{MIN_WORD_COUNT.toLocaleString()}</span>
                    <span>{MAX_WORD_COUNT.toLocaleString()}</span>
                </div>
            </div>
        </CollapsibleContent>
    </Collapsible>
    
    <!-- Metadata -->
    <Collapsible bind:open={metadataExpanded}>
        <CollapsibleTrigger asChild>
            <button 
                type="button"
                class="w-full flex items-center justify-between h-8 px-0 hover:bg-accent hover:text-accent-foreground rounded-md transition-colors"
            >
                <div class="flex items-center space-x-2">
                    <FileText class="h-3 w-3" />
                    <span class="text-xs">Metadata</span>
                    {#if hasTitle !== null || hasAuthor !== null}
                        <Badge variant="outline" class="text-xs h-4 px-1">
                            Set
                        </Badge>
                    {/if}
                </div>
                {#if metadataExpanded}
                    <ChevronDown class="h-3 w-3" />
                {:else}
                    <ChevronRight class="h-3 w-3" />
                {/if}
            </button>
        </CollapsibleTrigger>
        <CollapsibleContent class="space-y-2 pt-2">
            {#if hasTitle !== null || hasAuthor !== null}
                <div class="flex justify-end">
                    <Button
                        variant="ghost"
                        size="sm"
                        onclick={clearMetadata}
                        class="h-6 px-2 text-xs"
                    >
                        Clear
                    </Button>
                </div>
            {/if}
            
            <div class="space-y-3">
                <div class="space-y-2">
                    <span class="text-xs text-muted-foreground">Has Title:</span>
                    <div class="flex space-x-2">
                        <Button
                            variant={hasTitle === true ? "default" : "outline"}
                            size="sm"
                            onclick={() => handleMetadataChange('hasTitle', true)}
                            class="text-xs h-6 px-2"
                        >
                            Yes
                        </Button>
                        <Button
                            variant={hasTitle === false ? "default" : "outline"}
                            size="sm"
                            onclick={() => handleMetadataChange('hasTitle', false)}
                            class="text-xs h-6 px-2"
                        >
                            No
                        </Button>
                        <Button
                            variant={hasTitle === null ? "default" : "outline"}
                            size="sm"
                            onclick={() => handleMetadataChange('hasTitle', null)}
                            class="text-xs h-6 px-2"
                        >
                            Any
                        </Button>
                    </div>
                </div>
                
                <div class="space-y-2">
                    <span class="text-xs text-muted-foreground">Has Author:</span>
                    <div class="flex space-x-2">
                        <Button
                            variant={hasAuthor === true ? "default" : "outline"}
                            size="sm"
                            onclick={() => handleMetadataChange('hasAuthor', true)}
                            class="text-xs h-6 px-2"
                        >
                            Yes
                        </Button>
                        <Button
                            variant={hasAuthor === false ? "default" : "outline"}
                            size="sm"
                            onclick={() => handleMetadataChange('hasAuthor', false)}
                            class="text-xs h-6 px-2"
                        >
                            No
                        </Button>
                        <Button
                            variant={hasAuthor === null ? "default" : "outline"}
                            size="sm"
                            onclick={() => handleMetadataChange('hasAuthor', null)}
                            class="text-xs h-6 px-2"
                        >
                            Any
                        </Button>
                    </div>
                </div>
            </div>
        </CollapsibleContent>
    </Collapsible>
</div>