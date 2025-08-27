<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Grid, List, Filter, ChevronDown, ChevronRight, ExternalLink, Eye, AlertTriangle, Info, PlayCircle, ShieldCheck } from 'lucide-svelte';
	import EnhancedURLProgressCard from './EnhancedURLProgressCard.svelte';
	import BulkActionToolbar from './BulkActionToolbar.svelte';
	import FilteringStatusBadge from './FilteringStatusBadge.svelte';
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
	export let showAllUrls: boolean = false; // New prop to show all URLs including filtered

	const dispatch = createEventDispatcher<{
		viewModeChange: { mode: 'list' | 'grid' };
		bulkActionsToggle: boolean;
		showAllUrlsToggle: boolean;
		pageAction: { type: string; pageId: number; data?: any };
		pageSelect: { pageId: number; selected: boolean; shiftKey?: boolean };
		bulkAction: { action: string; pageIds: number[]; data?: any };
		groupAction: { action: string; urlGroup: string; pageIds: number[]; data?: any };
		groupSelect: { urlGroup: string; selected: boolean };
	}>();

	// Reactive state for bulk selection
	$: inBulkMode = $bulkSelectionMode;
	$: selectedCount = $selectedPagesCount;
	$: showBulkToolbar = $hasSelectedPages;

	// Enhanced group interface with filtering information
	interface URLGroup {
		url: string;
		domain: string;
		captures: any[];
		expanded: boolean;
		selected: boolean;
		hasFailures: boolean;
		hasPending: boolean;
		hasCompleted: boolean;
		hasFiltered: boolean;
		hasManuallyOverridden: boolean;
		canBeManuallyProcessed: boolean;
		filterBreakdown: {
			[key: string]: number;
		};
		statusBreakdown: {
			[key: string]: number;
		};
		priorityDistribution: {
			high: number;
			normal: number;
			low: number;
		};
	}

	let urlGroups: URLGroup[] = [];
	let selectedPageIds: Set<number> = new Set();
	let selectedGroupUrls: Set<string> = new Set();
	let expandedGroups: Set<string> = new Set();

	// Enhanced grouping with filter analysis
	$: {
		if (scrapePages) {
			const groupMap = new Map<string, URLGroup>();
			
			for (const page of scrapePages) {
				const url = page.original_url;
				
				if (!groupMap.has(url)) {
					const domain = extractDomain(url);
					groupMap.set(url, {
						url,
						domain,
						captures: [],
						expanded: expandedGroups.has(url),
						selected: selectedGroupUrls.has(url),
						hasFailures: false,
						hasPending: false,
						hasCompleted: false,
						hasFiltered: false,
						hasManuallyOverridden: false,
						canBeManuallyProcessed: false,
						filterBreakdown: {},
						statusBreakdown: {},
						priorityDistribution: { high: 0, normal: 0, low: 0 }
					});
				}
				
				const group = groupMap.get(url)!;
				group.captures.push(page);
				
				// Enhanced status analysis
				const status = page.status?.toLowerCase() || 'unknown';
				group.statusBreakdown[status] = (group.statusBreakdown[status] || 0) + 1;
				
				// Update group flags
				if (status === 'failed') group.hasFailures = true;
				if (status === 'pending' || status === 'in_progress') group.hasPending = true;
				if (status === 'completed') group.hasCompleted = true;
				if (status.startsWith('filtered_') || status === 'awaiting_manual_review') {
					group.hasFiltered = true;
					
					// Track filter reasons
					const filterReason = page.filter_reason || 'unspecified';
					group.filterBreakdown[filterReason] = (group.filterBreakdown[filterReason] || 0) + 1;
				}
				if (page.is_manually_overridden) group.hasManuallyOverridden = true;
				if (page.can_be_manually_processed !== false && status.startsWith('filtered_')) {
					group.canBeManuallyProcessed = true;
				}
				
				// Priority distribution
				const priority = page.priority_score || 5;
				if (priority >= 7) group.priorityDistribution.high++;
				else if (priority >= 4) group.priorityDistribution.normal++;
				else group.priorityDistribution.low++;
			}
			
			// Sort captures within each group by capture date (newest first)
			for (const group of groupMap.values()) {
				group.captures.sort((a, b) => {
					const dateA = new Date(a.captured_at || a.created_at || 0);
					const dateB = new Date(b.captured_at || b.created_at || 0);
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

	function extractDomain(url: string): string {
		try {
			return new URL(url).hostname;
		} catch {
			return url.split('/')[0] || 'unknown';
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

	function handleGroupAction(action: string, urlGroup: URLGroup, data?: any) {
		const pageIds = urlGroup.captures.map(c => c.id);
		dispatch('groupAction', { action, urlGroup: urlGroup.url, pageIds, data });
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

	function handleShowAllUrlsToggle() {
		dispatch('showAllUrlsToggle', !showAllUrls);
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

	function handleBulkAction(event: CustomEvent) {
		const { action, pageIds, data } = event.detail;
		dispatch('bulkAction', { action, pageIds, data });
	}

	// Get status color for URL groups
	function getGroupStatusColor(group: URLGroup): string {
		if (group.hasFailures) return 'bg-red-500';
		if (group.hasFiltered && !group.hasManuallyOverridden) return 'bg-amber-500';
		if (group.hasPending) return 'bg-blue-500';
		if (group.hasCompleted) return 'bg-green-500';
		return 'bg-gray-500';
	}

	// Get comprehensive status text for URL groups
	function getGroupStatusText(group: URLGroup): string {
		const total = group.captures.length;
		const parts = [];
		
		if (group.statusBreakdown.completed) {
			parts.push(`${group.statusBreakdown.completed} complete`);
		}
		if (group.hasFiltered) {
			const filteredCount = Object.entries(group.statusBreakdown)
				.filter(([status]) => status.startsWith('filtered_'))
				.reduce((sum, [_, count]) => sum + count, 0);
			parts.push(`${filteredCount} filtered`);
		}
		if (group.statusBreakdown.failed) {
			parts.push(`${group.statusBreakdown.failed} failed`);
		}
		if (group.statusBreakdown.pending || group.statusBreakdown.in_progress) {
			const pendingCount = (group.statusBreakdown.pending || 0) + (group.statusBreakdown.in_progress || 0);
			parts.push(`${pendingCount} pending`);
		}
		
		return `${total} total: ${parts.join(', ')}`;
	}

	// Get selected pages for bulk action toolbar
	$: selectedPages = scrapePages.filter(page => selectedPageIds.has(page.id));

	// Filter statistics
	$: filteredCount = scrapePages.filter(page => 
		page.status?.toLowerCase().startsWith('filtered_') || 
		page.status?.toLowerCase() === 'awaiting_manual_review'
	).length;
	
	$: processableCount = scrapePages.filter(page => 
		(page.status?.toLowerCase().startsWith('filtered_') || page.status?.toLowerCase() === 'awaiting_manual_review') &&
		page.can_be_manually_processed !== false
	).length;
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
				
				{#if filteredCount > 0}
					<div class="flex items-center space-x-2">
						<Badge variant="outline" class="text-xs bg-amber-50 border-amber-200 text-amber-800">
							{filteredCount} filtered
						</Badge>
						{#if processableCount > 0}
							<Badge variant="outline" class="text-xs bg-green-50 border-green-200 text-green-800">
								{processableCount} can override
							</Badge>
						{/if}
					</div>
				{/if}
				
				{#if inBulkMode && selectedCount > 0}
					<Badge variant="secondary" class="text-xs">
						{selectedCount} selected
					</Badge>
				{/if}
			</div>
			
			<div class="flex items-center space-x-2">
				<!-- Show All URLs Toggle -->
				<Button
					variant={showAllUrls ? "default" : "outline"}
					size="sm"
					onclick={handleShowAllUrlsToggle}
					class="h-7 px-3 text-xs"
					title={showAllUrls ? "Currently showing all URLs including filtered" : "Show all URLs including filtered content"}
				>
					<Eye class="h-3 w-3 mr-1" />
					{showAllUrls ? "Showing All" : "Show All URLs"}
				</Button>

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

		<!-- Enhanced Bulk Action Toolbar -->
		<BulkActionToolbar
			{selectedCount}
			selectedPages={selectedPages}
			showToolbar={showBulkToolbar && inBulkMode}
			on:bulkAction={handleBulkAction}
			on:clearSelection={handleSelectNone}
			on:selectAll={handleSelectAll}
			on:selectNone={handleSelectNone}
		/>

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
								
								<!-- Enhanced Status Indicator -->
								<div class="w-2 h-2 rounded-full {getGroupStatusColor(group)}"></div>
								
								<!-- URL Info with Enhanced Status -->
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
										
										<!-- Enhanced status badges -->
										{#if group.hasFiltered}
											<Badge variant="outline" class="text-xs bg-amber-50 border-amber-200 text-amber-800">
												<Filter class="h-2.5 w-2.5 mr-1" />
												Filtered
											</Badge>
										{/if}
										{#if group.hasManuallyOverridden}
											<Badge variant="success" class="text-xs">
												<ShieldCheck class="h-2.5 w-2.5 mr-1" />
												Override
											</Badge>
										{/if}
										{#if group.priorityDistribution.high > 0}
											<Badge variant="default" class="text-xs">
												High Priority
											</Badge>
										{/if}
									</div>
									<p class="text-xs text-muted-foreground truncate">{group.url}</p>
								</div>
								
								<!-- Group Stats with Enhanced Details -->
								<div class="text-xs text-muted-foreground">
									<Badge variant="outline" class="text-xs">
										{group.captures.length} capture{group.captures.length !== 1 ? 's' : ''}
									</Badge>
								</div>
							</div>
							
							<!-- Enhanced Group Actions -->
							<div class="flex items-center space-x-1">
								<span class="text-xs text-muted-foreground mr-2">
									{getGroupStatusText(group)}
								</span>
								
								{#if group.canBeManuallyProcessed}
									<Button
										variant="outline"
										size="sm"
										onclick={() => handleGroupAction('manual_process', group)}
										class="h-6 px-2 text-xs bg-green-50 hover:bg-green-100 border-green-200"
										title="Process all filterable pages in this group"
									>
										<PlayCircle class="h-3 w-3 mr-1" />
										Process
									</Button>
								{/if}
								
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
					
					<!-- Expanded Captures with Enhanced Display -->
					{#if group.expanded}
						<CardContent class="p-2">
							<!-- Filter Analysis for this group -->
							{#if group.hasFiltered && Object.keys(group.filterBreakdown).length > 0}
								<div class="mb-3 p-2 bg-amber-50 border border-amber-200 rounded text-xs">
									<div class="flex items-center gap-2 font-medium text-amber-800 mb-1">
										<Info class="h-3 w-3" />
										Filtering Analysis for this URL:
									</div>
									<div class="grid grid-cols-2 gap-1 text-amber-700">
										{#each Object.entries(group.filterBreakdown) as [reason, count]}
											<div>• {count}x {reason.replace('_', ' ')}</div>
										{/each}
									</div>
								</div>
							{/if}
							
							<div class="space-y-1">
								{#each group.captures as capture, index (capture.id)}
									<EnhancedURLProgressCard
										scrapePage={capture}
										isSelected={selectedPageIds.has(capture.id)}
										compact={true}
										showUrl={false}
										showIndex={index + 1}
										showFilteringDetails={true}
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
					{#if !showAllUrls}
						<Button 
							variant="outline" 
							size="sm" 
							onclick={handleShowAllUrlsToggle} 
							class="mt-2"
						>
							<Eye class="h-3 w-3 mr-1" />
							Show All URLs (including filtered)
						</Button>
					{/if}
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
					{#if !showAllUrls}
						<p class="text-sm text-muted-foreground mt-2">
							Tip: Use "Show All URLs" to see filtered content that was automatically skipped.
						</p>
					{/if}
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
				<AlertTriangle class="h-4 w-4" />
				<p>{error}</p>
			</div>
		</CardContent>
	</Card>
{/if}