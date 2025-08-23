<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Grid, List, Filter, ChevronDown, ChevronRight, ExternalLink } from 'lucide-svelte';
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
		groupAction: { action: string; urlGroup: string; pageIds: number[] };
		groupSelect: { urlGroup: string; selected: boolean };
	}>();

	// Reactive state for bulk selection
	$: inBulkMode = $bulkSelectionMode;
	$: selectedCount = $selectedPagesCount;
	$: showBulkToolbar = $hasSelectedPages;

	// Group pages by URL and sort by capture date
	interface URLGroup {
		url: string;
		domain: string;
		captures: any[];
		expanded: boolean;
		selected: boolean;
		hasFailures: boolean;
		hasPending: boolean;
		hasCompleted: boolean;
	}

	let urlGroups: URLGroup[] = [];
	let selectedPageIds: Set<number> = new Set();
	let selectedGroupUrls: Set<string> = new Set();
	let expandedGroups: Set<string> = new Set();

	// Group scrape pages by URL
	$: {
		if (scrapePages) {
			const groupMap = new Map<string, URLGroup>();
			
			for (const page of scrapePages) {
				const url = page.original_url;
				
				if (!groupMap.has(url)) {
					const domain = new URL(url).hostname;
					groupMap.set(url, {
						url,
						domain,
						captures: [],
						expanded: expandedGroups.has(url),
						selected: selectedGroupUrls.has(url),
						hasFailures: false,
						hasPending: false,
						hasCompleted: false
					});
				}
				
				const group = groupMap.get(url)!;
				group.captures.push(page);
				
				// Update group status flags
				if (page.status === 'failed') group.hasFailures = true;
				if (page.status === 'pending' || page.status === 'in_progress') group.hasPending = true;
				if (page.status === 'completed') group.hasCompleted = true;
			}
			
			// Sort captures within each group by capture date (newest first)
			for (const group of groupMap.values()) {
				group.captures.sort((a, b) => {
					const dateA = new Date(a.captured_at || a.created_at);
					const dateB = new Date(b.captured_at || b.created_at);
					return dateB.getTime() - dateA.getTime();
				});
			}
			
			// Convert to array and sort by domain then URL
			urlGroups = Array.from(groupMap.values()).sort((a, b) => {
				if (a.domain === b.domain) {
					return a.url.localeCompare(b.url);
				}
				return a.domain.localeCompare(b.domain);
			});
		}
	}

	function toggleGroupExpansion(url: string) {
		if (expandedGroups.has(url)) {
			expandedGroups.delete(url);
		} else {
			expandedGroups.add(url);
		}
		expandedGroups = expandedGroups;
		
		// Update the group's expanded state
		const group = urlGroups.find(g => g.url === url);
		if (group) {
			group.expanded = expandedGroups.has(url);
		}
	}

	function handleGroupSelect(url: string, selected: boolean) {
		if (selected) {
			selectedGroupUrls.add(url);
		} else {
			selectedGroupUrls.delete(url);
		}
		selectedGroupUrls = selectedGroupUrls;

		// Update group selection state
		const group = urlGroups.find(g => g.url === url);
		if (group) {
			group.selected = selected;
			
			// Select/deselect all captures in the group
			for (const capture of group.captures) {
				if (selected) {
					selectedPageIds.add(capture.id);
				} else {
					selectedPageIds.delete(capture.id);
				}
			}
			selectedPageIds = selectedPageIds;
		}

		dispatch('groupSelect', { urlGroup: url, selected });
	}

	function handleGroupAction(action: string, urlGroup: URLGroup) {
		const pageIds = urlGroup.captures.map(c => c.id);
		dispatch('groupAction', { action, urlGroup: urlGroup.url, pageIds });
	}

	// Handle individual page actions
	function handlePageAction(event: CustomEvent) {
		dispatch('pageAction', event.detail);
	}

	// Handle individual page selection
	function handlePageSelect(event: CustomEvent) {
		const { pageId, selected, shiftKey } = event.detail;
		
		if (selected) {
			selectedPageIds.add(pageId);
		} else {
			selectedPageIds.delete(pageId);
		}
		selectedPageIds = selectedPageIds;

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
			selectedGroupUrls.clear();
			selectedPageIds = selectedPageIds;
			selectedGroupUrls = selectedGroupUrls;
			pageManagementActions.clearSelection();
		}
	}

	// Bulk action handlers
	function handleSelectAll() {
		const allPageIds = scrapePages.map(p => p.id);
		const allGroupUrls = urlGroups.map(g => g.url);
		
		selectedPageIds = new Set(allPageIds);
		selectedGroupUrls = new Set(allGroupUrls);
		
		// Update group selection states
		for (const group of urlGroups) {
			group.selected = true;
		}
		
		pageManagementStore.update(state => ({
			...state,
			selectedPageIds: allPageIds
		}));
	}

	function handleSelectNone() {
		selectedPageIds.clear();
		selectedGroupUrls.clear();
		selectedPageIds = selectedPageIds;
		selectedGroupUrls = selectedGroupUrls;
		
		// Update group selection states
		for (const group of urlGroups) {
			group.selected = false;
		}
		
		pageManagementActions.clearSelection();
	}

	function handleBulkAction(action: string) {
		const selectedIds = Array.from(selectedPageIds);
		if (selectedIds.length === 0) return;
		
		dispatch('bulkAction', { action, pageIds: selectedIds });
	}

	// Get status color for URL groups
	function getGroupStatusColor(group: URLGroup) {
		if (group.hasFailures) return 'bg-red-500';
		if (group.hasPending) return 'bg-yellow-500';
		if (group.hasCompleted) return 'bg-green-500';
		return 'bg-gray-500';
	}

	// Get status text for URL groups
	function getGroupStatusText(group: URLGroup) {
		const total = group.captures.length;
		const completed = group.captures.filter(c => c.status === 'completed').length;
		const failed = group.captures.filter(c => c.status === 'failed').length;
		const pending = group.captures.filter(c => c.status === 'pending' || c.status === 'in_progress').length;
		
		return `${completed}/${total} completed${failed > 0 ? `, ${failed} failed` : ''}${pending > 0 ? `, ${pending} pending` : ''}`;
	}
</script>

<!-- Results Header -->
{#if urlGroups.length > 0}
	<div class="space-y-4">
		<div class="flex items-center justify-between">
			<div class="flex items-center space-x-4">
				<p class="text-sm text-muted-foreground">
					Found {urlGroups.length} URL{urlGroups.length !== 1 ? 's' : ''} 
					({scrapePages.length} capture{scrapePages.length !== 1 ? 's' : ''})
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
							<span class="text-sm font-medium">{selectedCount} captures selected</span>
							<div class="flex space-x-2">
								<Button
									variant="outline"
									size="sm"
									onclick={() => handleBulkAction('retry')}
									class="h-7 px-3 text-xs"
									disabled={selectedCount === 0}
								>
									Retry Selected
								</Button>
								<Button
									variant="outline"
									size="sm"
									onclick={() => handleBulkAction('skip')}
									class="h-7 px-3 text-xs"
									disabled={selectedCount === 0}
								>
									Skip Selected
								</Button>
								<Button
									variant="outline"
									size="sm"
									onclick={() => handleBulkAction('priority')}
									class="h-7 px-3 text-xs"
									disabled={selectedCount === 0}
								>
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

		<!-- URL Groups -->
		<div class="space-y-2">
			<!-- Loading overlay -->
			{#if loading}
				<div class="absolute inset-0 bg-background/80 backdrop-blur-sm z-10 flex items-center justify-center rounded-lg transition-all duration-200">
					<div class="flex items-center space-x-3">
						<div class="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full"></div>
						<span class="text-sm text-muted-foreground">Updating results...</span>
					</div>
				</div>
			{/if}
			
			{#each urlGroups as group (group.url)}
				<Card class="overflow-hidden transition-all duration-200 {loading ? 'opacity-50' : 'opacity-100'}">
					<div class="border-b bg-muted/50">
						<div class="flex items-center justify-between p-3">
							<div class="flex items-center space-x-3 min-w-0 flex-1">
								<!-- Group Selection -->
								{#if inBulkMode}
									<input
										type="checkbox"
										checked={group.selected}
										onchange={(e) => handleGroupSelect(group.url, e.target.checked)}
										class="w-4 h-4 rounded border-border"
									/>
								{/if}
								
								<!-- Expand/Collapse Button -->
								<Button
									variant="ghost"
									size="sm"
									onclick={() => toggleGroupExpansion(group.url)}
									class="h-6 w-6 p-0"
								>
									{#if group.expanded}
										<ChevronDown class="h-4 w-4" />
									{:else}
										<ChevronRight class="h-4 w-4" />
									{/if}
								</Button>
								
								<!-- Status Indicator -->
								<div class="w-2 h-2 rounded-full {getGroupStatusColor(group)}"></div>
								
								<!-- URL Info -->
								<div class="min-w-0 flex-1">
									<div class="flex items-center space-x-2">
										<p class="text-sm font-medium truncate">{group.domain}</p>
										<a 
											href={group.url} 
											target="_blank" 
											rel="noopener noreferrer"
											class="text-muted-foreground hover:text-foreground"
										>
											<ExternalLink class="h-3 w-3" />
										</a>
									</div>
									<p class="text-xs text-muted-foreground truncate">{group.url}</p>
								</div>
								
								<!-- Group Stats -->
								<div class="text-xs text-muted-foreground">
									<Badge variant="outline" class="text-xs">
										{group.captures.length} capture{group.captures.length !== 1 ? 's' : ''}
									</Badge>
								</div>
							</div>
							
							<!-- Group Actions -->
							<div class="flex items-center space-x-1">
								<span class="text-xs text-muted-foreground mr-2">
									{getGroupStatusText(group)}
								</span>
								
								{#if group.hasFailures}
									<Button
										variant="outline"
										size="sm"
										onclick={() => handleGroupAction('retry', group)}
										class="h-6 px-2 text-xs"
									>
										Retry All
									</Button>
								{/if}
								
								{#if group.hasPending}
									<Button
										variant="outline"
										size="sm"
										onclick={() => handleGroupAction('skip', group)}
										class="h-6 px-2 text-xs"
									>
										Skip All
									</Button>
									<Button
										variant="outline"
										size="sm"
										onclick={() => handleGroupAction('priority', group)}
										class="h-6 px-2 text-xs"
									>
										Priority
									</Button>
								{/if}
							</div>
						</div>
					</div>
					
					<!-- Expanded Captures -->
					{#if group.expanded}
						<CardContent class="p-2">
							<div class="space-y-1">
								{#each group.captures as capture, index (capture.id)}
									<URLProgressCard
										scrapePage={capture}
										isSelected={selectedPageIds.has(capture.id)}
										compact={true}
										showUrl={false}
										showIndex={index + 1}
										on:action={handlePageAction}
										on:select={handlePageSelect}
									/>
								{/each}
							</div>
						</CardContent>
					{/if}
				</Card>
			{/each}
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