<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { cn } from '$lib/utils';
	import { 
		Search, 
		Filter, 
		X, 
		Calendar, 
		Globe, 
		FileText, 
		User, 
		Hash, 
		ChevronDown,
		ChevronUp
	} from 'lucide-svelte';

	const dispatch = createEventDispatcher();

	export let initialFilters: any = {};
	export let facets: any = null;
	export let loading = false;

	// Form state
	let searchQuery = initialFilters.query || '';
	let selectedProjects: number[] = initialFilters.projects || [];
	let selectedDomains: string[] = initialFilters.domains || [];
	let dateFrom = initialFilters.date_from || '';
	let dateTo = initialFilters.date_to || '';
	let selectedContentTypes: string[] = initialFilters.content_types || [];
	let selectedLanguages: string[] = initialFilters.languages || [];
	let wordCountMin = initialFilters.word_count_min || '';
	let wordCountMax = initialFilters.word_count_max || '';
	let hasTitle = initialFilters.has_title;
	let hasAuthor = initialFilters.has_author;
	let selectedStatusCodes: number[] = initialFilters.status_codes || [];
	let keywords = initialFilters.keywords?.join(', ') || '';
	let excludeKeywords = initialFilters.exclude_keywords?.join(', ') || '';
	let sortBy = initialFilters.sort_by || 'scraped_at';
	let sortOrder = initialFilters.sort_order || 'desc';

	// UI state
	let showAdvancedFilters = false;
	let activeFiltersCount = 0;

	// Calculate active filters count
	$: {
		activeFiltersCount = 0;
		if (searchQuery) activeFiltersCount++;
		if (selectedProjects.length) activeFiltersCount++;
		if (selectedDomains.length) activeFiltersCount++;
		if (dateFrom || dateTo) activeFiltersCount++;
		if (selectedContentTypes.length) activeFiltersCount++;
		if (selectedLanguages.length) activeFiltersCount++;
		if (wordCountMin || wordCountMax) activeFiltersCount++;
		if (hasTitle !== undefined) activeFiltersCount++;
		if (hasAuthor !== undefined) activeFiltersCount++;
		if (selectedStatusCodes.length) activeFiltersCount++;
		if (keywords) activeFiltersCount++;
		if (excludeKeywords) activeFiltersCount++;
	}

	function handleSearch() {
		const filters = {
			query: searchQuery || undefined,
			projects: selectedProjects.length ? selectedProjects : undefined,
			domains: selectedDomains.length ? selectedDomains : undefined,
			date_from: dateFrom || undefined,
			date_to: dateTo || undefined,
			content_types: selectedContentTypes.length ? selectedContentTypes : undefined,
			languages: selectedLanguages.length ? selectedLanguages : undefined,
			word_count_min: wordCountMin ? parseInt(wordCountMin) : undefined,
			word_count_max: wordCountMax ? parseInt(wordCountMax) : undefined,
			has_title: hasTitle,
			has_author: hasAuthor,
			status_codes: selectedStatusCodes.length ? selectedStatusCodes : undefined,
			keywords: keywords ? keywords.split(',').map(k => k.trim()).filter(k => k) : undefined,
			exclude_keywords: excludeKeywords ? excludeKeywords.split(',').map(k => k.trim()).filter(k => k) : undefined,
			sort_by: sortBy,
			sort_order: sortOrder
		};

		dispatch('search', filters);
	}

	function clearFilters() {
		searchQuery = '';
		selectedProjects = [];
		selectedDomains = [];
		dateFrom = '';
		dateTo = '';
		selectedContentTypes = [];
		selectedLanguages = [];
		wordCountMin = '';
		wordCountMax = '';
		hasTitle = undefined;
		hasAuthor = undefined;
		selectedStatusCodes = [];
		keywords = '';
		excludeKeywords = '';
		sortBy = 'scraped_at';
		sortOrder = 'desc';
		
		dispatch('search', {});
	}

	function toggleArrayItem<T>(array: T[], item: T): T[] {
		const index = array.indexOf(item);
		if (index > -1) {
			return array.filter((_, i) => i !== index);
		} else {
			return [...array, item];
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			handleSearch();
		}
	}
</script>

<div class="space-y-4">
	<!-- Main Search Bar -->
	<div class="flex gap-2">
		<div class="relative flex-1">
			<Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
			<input
				type="text"
				bind:value={searchQuery}
				on:keydown={handleKeydown}
				placeholder="Search content, titles, descriptions... Try: title:&quot;example&quot; domain:site.com wordcount:100..500"
				class="w-full pl-10 pr-4 py-2 border border-input bg-background rounded-md text-sm focus:ring-2 focus:ring-ring focus:border-transparent"
			/>
		</div>
		<Button on:click={handleSearch} disabled={loading}>
			<Search class="w-4 h-4" />
		</Button>
		<Button 
			variant="outline" 
			on:click={() => showAdvancedFilters = !showAdvancedFilters}
		>
			<Filter class="w-4 h-4" />
			{#if activeFiltersCount > 0}
				<Badge variant="secondary" class="ml-2 h-5 text-xs">
					{activeFiltersCount}
				</Badge>
			{/if}
			{#if showAdvancedFilters}
				<ChevronUp class="w-4 h-4 ml-1" />
			{:else}
				<ChevronDown class="w-4 h-4 ml-1" />
			{/if}
		</Button>
	</div>

	<!-- Active Filters Display -->
	{#if activeFiltersCount > 0}
		<div class="flex flex-wrap gap-2">
			{#if searchQuery}
				<Badge variant="outline" class="gap-1">
					<Search class="w-3 h-3" />
					"{searchQuery}"
					<Button 
						variant="ghost" 
						size="sm" 
						class="h-auto w-auto p-0 hover:bg-transparent"
						on:click={() => searchQuery = ''}
					>
						<X class="w-3 h-3" />
					</Button>
				</Badge>
			{/if}
			
			{#if selectedProjects.length > 0 && facets?.projects}
				{#each selectedProjects as projectId}
					{@const project = facets.projects.find(p => p.value === projectId)}
					<Badge variant="outline" class="gap-1">
						Project: {project?.label || projectId}
						<Button 
							variant="ghost" 
							size="sm" 
							class="h-auto w-auto p-0 hover:bg-transparent"
							on:click={() => selectedProjects = selectedProjects.filter(id => id !== projectId)}
						>
							<X class="w-3 h-3" />
						</Button>
					</Badge>
				{/each}
			{/if}

			{#if selectedDomains.length > 0}
				{#each selectedDomains as domain}
					<Badge variant="outline" class="gap-1">
						<Globe class="w-3 h-3" />
						{domain}
						<Button 
							variant="ghost" 
							size="sm" 
							class="h-auto w-auto p-0 hover:bg-transparent"
							on:click={() => selectedDomains = selectedDomains.filter(d => d !== domain)}
						>
							<X class="w-3 h-3" />
						</Button>
					</Badge>
				{/each}
			{/if}

			{#if dateFrom || dateTo}
				<Badge variant="outline" class="gap-1">
					<Calendar class="w-3 h-3" />
					{dateFrom || '...'} → {dateTo || '...'}
					<Button 
						variant="ghost" 
						size="sm" 
						class="h-auto w-auto p-0 hover:bg-transparent"
						on:click={() => { dateFrom = ''; dateTo = ''; }}
					>
						<X class="w-3 h-3" />
					</Button>
				</Badge>
			{/if}

			<Button 
				variant="ghost" 
				size="sm" 
				class="text-muted-foreground hover:text-foreground"
				on:click={clearFilters}
			>
				Clear all
			</Button>
		</div>
	{/if}

	<!-- Advanced Filters Panel -->
	{#if showAdvancedFilters}
		<Card>
			<CardHeader class="pb-3">
				<CardTitle class="text-base">Advanced Filters</CardTitle>
			</CardHeader>
			<CardContent class="space-y-6">
				<!-- Projects and Domains -->
				<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
					{#if facets?.projects?.length > 0}
						<div>
							<label class="text-sm font-medium mb-2 block">Projects</label>
							<div class="space-y-2 max-h-40 overflow-y-auto border rounded p-2">
								{#each facets.projects as project}
									<label class="flex items-center gap-2 text-sm cursor-pointer">
										<input
											type="checkbox"
											bind:group={selectedProjects}
											value={project.value}
											class="rounded border-gray-300"
										/>
										{project.label}
										<Badge variant="secondary" class="text-xs">{project.count}</Badge>
									</label>
								{/each}
							</div>
						</div>
					{/if}

					{#if facets?.domains?.length > 0}
						<div>
							<label class="text-sm font-medium mb-2 block">Domains</label>
							<div class="space-y-2 max-h-40 overflow-y-auto border rounded p-2">
								{#each facets.domains as domain}
									<label class="flex items-center gap-2 text-sm cursor-pointer">
										<input
											type="checkbox"
											bind:group={selectedDomains}
											value={domain.value}
											class="rounded border-gray-300"
										/>
										<Globe class="w-3 h-3 text-muted-foreground" />
										{domain.value}
										<Badge variant="secondary" class="text-xs">{domain.count}</Badge>
									</label>
								{/each}
							</div>
						</div>
					{/if}
				</div>

				<!-- Date Range -->
				<div>
					<label class="text-sm font-medium mb-2 block">
						<Calendar class="w-4 h-4 inline mr-1" />
						Date Range
					</label>
					<div class="flex gap-2 items-center">
						<input
							type="date"
							bind:value={dateFrom}
							class="px-3 py-2 border border-input bg-background rounded-md text-sm"
						/>
						<span class="text-muted-foreground">to</span>
						<input
							type="date"
							bind:value={dateTo}
							class="px-3 py-2 border border-input bg-background rounded-md text-sm"
						/>
					</div>
				</div>

				<!-- Content Types and Languages -->
				<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
					{#if facets?.content_types?.length > 0}
						<div>
							<label class="text-sm font-medium mb-2 block">Content Types</label>
							<div class="space-y-2 max-h-32 overflow-y-auto">
								{#each facets.content_types as contentType}
									<label class="flex items-center gap-2 text-sm cursor-pointer">
										<input
											type="checkbox"
											bind:group={selectedContentTypes}
											value={contentType.value}
											class="rounded border-gray-300"
										/>
										<FileText class="w-3 h-3 text-muted-foreground" />
										{contentType.value}
										<Badge variant="secondary" class="text-xs">{contentType.count}</Badge>
									</label>
								{/each}
							</div>
						</div>
					{/if}

					{#if facets?.languages?.length > 0}
						<div>
							<label class="text-sm font-medium mb-2 block">Languages</label>
							<div class="space-y-2 max-h-32 overflow-y-auto">
								{#each facets.languages as language}
									<label class="flex items-center gap-2 text-sm cursor-pointer">
										<input
											type="checkbox"
											bind:group={selectedLanguages}
											value={language.value}
											class="rounded border-gray-300"
										/>
										<Globe class="w-3 h-3 text-muted-foreground" />
										{language.value?.toUpperCase()}
										<Badge variant="secondary" class="text-xs">{language.count}</Badge>
									</label>
								{/each}
							</div>
						</div>
					{/if}
				</div>

				<!-- Word Count Range -->
				<div>
					<label class="text-sm font-medium mb-2 block">
						<Hash class="w-4 h-4 inline mr-1" />
						Word Count Range
					</label>
					<div class="flex gap-2 items-center">
						<input
							type="number"
							bind:value={wordCountMin}
							placeholder="Min"
							min="0"
							class="w-24 px-3 py-2 border border-input bg-background rounded-md text-sm"
						/>
						<span class="text-muted-foreground">to</span>
						<input
							type="number"
							bind:value={wordCountMax}
							placeholder="Max"
							min="0"
							class="w-24 px-3 py-2 border border-input bg-background rounded-md text-sm"
						/>
						{#if facets?.word_count}
							<span class="text-xs text-muted-foreground">
								(Range: {facets.word_count.min} - {facets.word_count.max})
							</span>
						{/if}
					</div>
				</div>

				<!-- Metadata Filters -->
				<div>
					<label class="text-sm font-medium mb-2 block">
						<User class="w-4 h-4 inline mr-1" />
						Metadata Presence
					</label>
					<div class="space-y-2">
						<label class="flex items-center gap-2 text-sm cursor-pointer">
							<input
								type="checkbox"
								bind:checked={hasTitle}
								class="rounded border-gray-300"
							/>
							Has Title
						</label>
						<label class="flex items-center gap-2 text-sm cursor-pointer">
							<input
								type="checkbox"
								bind:checked={hasAuthor}
								class="rounded border-gray-300"
							/>
							Has Author
						</label>
					</div>
				</div>

				<!-- Keywords -->
				<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
					<div>
						<label class="text-sm font-medium mb-2 block">Required Keywords</label>
						<input
							type="text"
							bind:value={keywords}
							placeholder="keyword1, keyword2, ..."
							class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
						/>
					</div>
					<div>
						<label class="text-sm font-medium mb-2 block">Exclude Keywords</label>
						<input
							type="text"
							bind:value={excludeKeywords}
							placeholder="exclude1, exclude2, ..."
							class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
						/>
					</div>
				</div>

				<!-- Sort Options -->
				<div>
					<label class="text-sm font-medium mb-2 block">Sort By</label>
					<div class="flex gap-2">
						<select
							bind:value={sortBy}
							class="px-3 py-2 border border-input bg-background rounded-md text-sm"
						>
							<option value="scraped_at">Scraped Date</option>
							<option value="capture_date">Capture Date</option>
							<option value="word_count">Word Count</option>
							<option value="extracted_title">Title</option>
							<option value="original_url">URL</option>
						</select>
						<select
							bind:value={sortOrder}
							class="px-3 py-2 border border-input bg-background rounded-md text-sm"
						>
							<option value="desc">Descending</option>
							<option value="asc">Ascending</option>
						</select>
					</div>
				</div>

				<!-- Action Buttons -->
				<div class="flex gap-2 pt-4 border-t">
					<Button on:click={handleSearch} disabled={loading}>
						<Search class="w-4 h-4 mr-2" />
						Search
					</Button>
					<Button variant="outline" on:click={clearFilters}>
						<X class="w-4 h-4 mr-2" />
						Clear Filters
					</Button>
				</div>
			</CardContent>
		</Card>
	{/if}
</div>