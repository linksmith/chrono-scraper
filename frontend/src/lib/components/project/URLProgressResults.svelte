<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Grid, List, Filter, RotateCcw, Ban, TrendingUp } from 'lucide-svelte';
	import URLProgressCard from './URLProgressCard.svelte';
	import { 
		pageManagementStore, 
		pageManagementActions,
		bulkSelectionMode,
		selectedPagesCount,
		hasSelectedPages
	} from '$lib/stores/page-management';

	export let scrapePages: any[] = [];
	export let loading: boolean = false;
	export let error: string = '';
	export let searchQuery: string = '';
	export let viewMode: 'list' | 'grid' = 'list';
	export let showBulkActions: boolean = false;

	const dispatch = createEventDispatcher<{
		viewModeChange: { mode: 'list' | 'grid' };
		bulkActionsToggle: boolean;
		pageAction: { type: string; pageId: number; data?: any };
		pageSelect: { pageId: number; selected: boolean; shiftKey?: boolean };
		bulkAction: { action: string; pageIds: number[] };
	}>();

	// Reactive state for bulk selection
	$: inBulkMode = $bulkSelectionMode;
	$: selectedCount = $selectedPagesCount;
	$: showBulkToolbar = $hasSelectedPages;

	// Selection state
	let selectedPageIds: Set<number> = new Set();
	let lastSelectedIndex = -1;

	// Handle page actions
	function handlePageAction(event: CustomEvent) {
		const { type, pageId } = event.detail;
		dispatch('pageAction', { type, pageId });
	}

	// Handle page selection with shift-click support
	function handlePageSelect(event: CustomEvent) {
		const { pageId, selected, shiftKey } = event.detail;
		
		if (shiftKey && lastSelectedIndex >= 0) {
			// Range selection
			const currentIndex = scrapePages.findIndex(p => p.id === pageId);
			const start = Math.min(lastSelectedIndex, currentIndex);
			const end = Math.max(lastSelectedIndex, currentIndex);
			
			const newSelection = new Set(selectedPageIds);
			for (let i = start; i <= end; i++) {
				if (selected) {
					newSelection.add(scrapePages[i].id);
				} else {
					newSelection.delete(scrapePages[i].id);
				}
			}
			selectedPageIds = newSelection;
		} else {
			// Single selection
			const newSelection = new Set(selectedPageIds);
			if (selected) {
				newSelection.add(pageId);
			} else {
				newSelection.delete(pageId);
			}
			selectedPageIds = newSelection;
			lastSelectedIndex = scrapePages.findIndex(p => p.id === pageId);
		}

		// Update page management store
		pageManagementStore.update(state => ({
			...state,
			selectedPageIds: Array.from(selectedPageIds)
		}));

		dispatch('pageSelect', { pageId, selected, shiftKey });
	}

	function handleViewModeChange(mode: 'list' | 'grid') {
		dispatch('viewModeChange', { mode });
	}

	function handleBulkActionsToggle() {
		const newValue = !showBulkActions;
		dispatch('bulkActionsToggle', newValue);
		
		// Also toggle bulk selection mode
		pageManagementActions.toggleBulkSelectionMode();
		
		// Clear selection when disabling
		if (!newValue) {
			selectedPageIds.clear();
			selectedPageIds = selectedPageIds;
			pageManagementActions.clearSelection();
		}
	}

	// Bulk action handlers
	function handleSelectAll() {
		const allPageIds = scrapePages.map(p => p.id);
		selectedPageIds = new Set(allPageIds);
		
		pageManagementStore.update(state => ({
			...state,
			selectedPageIds: allPageIds
		}));
	}

	function handleSelectNone() {
		selectedPageIds.clear();
		selectedPageIds = selectedPageIds;
		pageManagementActions.clearSelection();
	}

	function handleBulkAction(action: string) {
		const selectedIds = Array.from(selectedPageIds);
		if (selectedIds.length === 0) return;
		
		dispatch('bulkAction', { action, pageIds: selectedIds });
	}

	// Sync pages to store when scrapePages change
	$: if (scrapePages) {
		pageManagementStore.update(state => ({
			...state,
			pages: scrapePages.map(scrapePage => ({
				id: parseInt(scrapePage.id),
				title: scrapePage.title || scrapePage.original_url,
				url: scrapePage.original_url,
				review_status: 'unreviewed',
				tags: [],
				word_count: 0,
				content_snippet: scrapePage.extracted_text || '',
				scraped_at: scrapePage.completed_at || scrapePage.created_at,
				reviewed_at: null,
				author: null,
				language: null,
				meta_description: null,
				is_starred: false
			}))
		}));
	}
</script>

<!-- Results Header -->
{#if scrapePages.length > 0}
	<div class="space-y-4">
		<div class="flex items-center justify-between">
			<div class="flex items-center space-x-4">
				<p class="text-sm text-muted-foreground">
					Found {scrapePages.length} URL{scrapePages.length !== 1 ? 's' : ''}
					{#if searchQuery.trim()}
						matching "<strong>{searchQuery}</strong>"
					{/if}
				</p>
				
				{#if inBulkMode && selectedCount > 0}
					<Badge variant="secondary" class="text-xs">
						{selectedCount} selected
					</Badge>
				{/if}
			</div>
			
			<div class="flex items-center space-x-2">
				<!-- Bulk Actions Controls -->
				{#if inBulkMode}
					<div class="flex items-center space-x-2">
						<Button
							variant="outline"
							size="sm"
							onclick={handleSelectAll}
							class="h-7 px-2 text-xs"
						>
							Select All
						</Button>
						<Button
							variant="outline"
							size="sm"
							onclick={handleSelectNone}
							class="h-7 px-2 text-xs"
						>
							None
						</Button>
					</div>
				{/if}

				<!-- View Mode Toggle -->
				<div class="flex bg-muted rounded-md p-1">
					<Button
						variant={viewMode === 'list' ? 'default' : 'ghost'}
						size="sm"
						class="h-6 px-2"
						onclick={() => handleViewModeChange('list')}
					>
						<List class="h-4 w-4" />
					</Button>
					<Button
						variant={viewMode === 'grid' ? 'default' : 'ghost'}
						size="sm"
						class="h-6 px-2"
						onclick={() => handleViewModeChange('grid')}
					>
						<Grid class="h-4 w-4" />
					</Button>
				</div>

				<Button 
					variant="outline" 
					size="sm"
					onclick={handleBulkActionsToggle}
					class="h-7 px-2 text-xs"
				>
					<Filter class="h-4 w-4 mr-2" />
					{showBulkActions ? 'Hide' : 'Show'} Bulk Actions
				</Button>
			</div>
		</div>

		<!-- Bulk Action Toolbar -->
		{#if showBulkToolbar && inBulkMode}
			<Card class="bg-blue-50 border-blue-200">
				<CardContent class="py-3">
					<div class="flex items-center justify-between">
						<div class="flex items-center space-x-4">
							<span class="text-sm font-medium">{selectedCount} URLs selected</span>
							<div class="flex space-x-2">
								<Button
									variant="outline"
									size="sm"
									onclick={() => handleBulkAction('retry')}
									class="h-7 px-3 text-xs"
									disabled={selectedCount === 0}
								>
									<RotateCcw class="h-3 w-3 mr-1" />
									{selectedCount === 1 ? 'Retry' : 'Retry All'}
								</Button>
								<Button
									variant="outline"
									size="sm"
									onclick={() => handleBulkAction('skip')}
									class="h-7 px-3 text-xs"
									disabled={selectedCount === 0}
								>
									<Ban class="h-3 w-3 mr-1" />
									Skip Selected
								</Button>
								<Button
									variant="outline"
									size="sm"
									onclick={() => handleBulkAction('priority')}
									class="h-7 px-3 text-xs"
									disabled={selectedCount === 0}
								>
									<TrendingUp class="h-3 w-3 mr-1" />
									Bump to Priority
								</Button>
							</div>
						</div>
						<Button
							variant="ghost"
							size="sm"
							onclick={handleSelectNone}
							class="h-7 px-2 text-xs"
						>
							Clear Selection
						</Button>
					</div>
				</CardContent>
			</Card>
		{/if}

		<!-- Results Grid/List -->
		<div class="relative">
			<!-- Loading overlay -->
			{#if loading}
				<div class="absolute inset-0 bg-background/80 backdrop-blur-sm z-10 flex items-center justify-center rounded-lg transition-all duration-200">
					<div class="flex items-center space-x-3">
						<div class="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full"></div>
						<span class="text-sm text-muted-foreground">Updating results...</span>
					</div>
				</div>
			{/if}
			
			<div class="{viewMode === 'grid' ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3' : 'space-y-2'} transition-opacity duration-200 {loading ? 'opacity-50' : 'opacity-100'}">
				{#each scrapePages as scrapePage, index}
					<URLProgressCard
						{scrapePage}
						isSelected={selectedPageIds.has(scrapePage.id)}
						compact={true}
						on:action={handlePageAction}
						on:select={handlePageSelect}
						on:expand={(e) => console.log('Expand:', e.detail)}
					/>
				{/each}
			</div>
		</div>
	</div>
{:else if searchQuery.trim() && !loading}
	<Card>
		<CardContent class="pt-6">
			<div class="flex flex-col items-center justify-center space-y-3 py-12">
				<div class="text-center">
					<h3 class="text-lg font-semibold">No URLs found</h3>
					<p class="text-muted-foreground">
						Try different search terms or adjust your filters.
					</p>
				</div>
			</div>
		</CardContent>
	</Card>
{:else if !loading}
	<Card>
		<CardContent class="pt-6">
			<div class="flex flex-col items-center justify-center space-y-3 py-12">
				<div class="text-center">
					<h3 class="text-lg font-semibold">No URLs discovered yet</h3>
					<p class="text-muted-foreground">
						URLs will appear here once CDX discovery begins.
					</p>
				</div>
			</div>
		</CardContent>
	</Card>
{/if}

<!-- Error Message -->
{#if error}
	<Card class="border-destructive">
		<CardContent class="pt-6">
			<div class="flex items-center space-x-2 text-destructive">
				<p>{error}</p>
			</div>
		</CardContent>
	</Card>
{/if}