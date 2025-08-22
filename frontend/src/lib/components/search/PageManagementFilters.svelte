<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Star, Tag, CheckCircle, XCircle } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { Label } from '$lib/components/ui/label';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { filters } from '$lib/stores/filters';
	import { pageManagementStore, pageManagementActions } from '$lib/stores/page-management';
	import TagAutocomplete from '$lib/components/page-management/TagAutocomplete.svelte';

	const dispatch = createEventDispatcher<{
		filterChange: void;
	}>();

	// Reactive filter state
	$: currentFilters = $filters;

	// Filter options
	const reviewStatusOptions = [
		{ value: 'relevant', label: 'Relevant', icon: CheckCircle, color: 'text-green-600' },
		{ value: 'irrelevant', label: 'Irrelevant', icon: XCircle, color: 'text-red-600' }
	];


	// Event handlers
	function handleStarredToggle(checked: boolean) {
		filters.update(f => ({ ...f, starredOnly: checked }));
		dispatch('filterChange');
	}

	function handleReviewStatusToggle(value: string, checked: boolean) {
		filters.update(f => {
			const newStatus = checked 
				? [...f.reviewStatus, value]
				: f.reviewStatus.filter(s => s !== value);
			return { ...f, reviewStatus: newStatus };
		});
		dispatch('filterChange');
	}


	function handleTagsChange(tags: string[]) {
		filters.update(f => ({ ...f, tags }));
		dispatch('filterChange');
	}

	function clearAllPageFilters() {
		filters.update(f => ({
			...f,
			starredOnly: false,
			tags: [],
			reviewStatus: []
		}));
		dispatch('filterChange');
	}

	// Check if there are any active page management filters
	$: hasActivePageFilters = currentFilters.starredOnly || 
		currentFilters.tags.length > 0 || 
		currentFilters.reviewStatus.length > 0;
</script>

<div class="space-y-4">
	<!-- Section Header -->
	<div class="flex items-center justify-between">
		<h3 class="font-medium text-sm">Page Management</h3>
		{#if hasActivePageFilters}
			<Button variant="ghost" size="sm" onclick={clearAllPageFilters}>
				Clear All
			</Button>
		{/if}
	</div>

	<!-- Starred Filter -->
	<div class="space-y-2">
		<div class="flex items-center space-x-2 group">
			<Checkbox
				bind:checked={currentFilters.starredOnly}
				onCheckedChange={handleStarredToggle}
				id="starred-filter"
			/>
			<Label for="starred-filter" class="flex items-center space-x-1 cursor-pointer group-hover:text-foreground transition-colors">
				<Star class="h-4 w-4 transition-all duration-200 {currentFilters.starredOnly ? 'text-yellow-500 scale-110' : 'text-muted-foreground'}" />
				<span>Show only starred</span>
			</Label>
		</div>
	</div>

	<!-- Tags Filter -->
	<div class="space-y-2">
		<Label class="flex items-center space-x-1">
			<Tag class="h-4 w-4" />
			<span>Tags</span>
		</Label>
		
		<TagAutocomplete
			tags={currentFilters.tags}
			suggestions={$pageManagementStore.tagSuggestions}
			placeholder="Filter by tags..."
			on:update={(e) => handleTagsChange(e.detail)}
			on:loadSuggestions={(e) => pageManagementActions.loadTagSuggestions(e.detail?.query)}
		/>
		

	</div>

	<!-- Review Status Filter -->
	<div class="space-y-2">
		<Label class="flex items-center space-x-1">
			<CheckCircle class="h-4 w-4" />
			<span>Review Status</span>
		</Label>
		
		<div class="space-y-1">
			{#each reviewStatusOptions as option}
				<div class="flex items-center space-x-2 group">
					<Checkbox
						checked={currentFilters.reviewStatus.includes(option.value)}
						onCheckedChange={(checked) => handleReviewStatusToggle(option.value, checked)}
						id={`review-${option.value}`}
					/>
					<Label for={`review-${option.value}`} class="flex items-center space-x-1 cursor-pointer text-sm group-hover:text-foreground transition-colors">
						<svelte:component 
							this={option.icon} 
							class="h-3 w-3 transition-all duration-200 {currentFilters.reviewStatus.includes(option.value) ? option.color + ' scale-110' : 'text-muted-foreground'}" 
						/>
						<span>{option.label}</span>
					</Label>
				</div>
			{/each}
		</div>
	</div>

</div>

<style>
	/* Custom styling for compact filter sections */
	:global(.page-management-filters .filter-section) {
		border-bottom: 1px solid hsl(var(--border));
		padding-bottom: 0.75rem;
		margin-bottom: 0.75rem;
	}
	
	:global(.page-management-filters .filter-section:last-child) {
		border-bottom: none;
		margin-bottom: 0;
	}
</style>