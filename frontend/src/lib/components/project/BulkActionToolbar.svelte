<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Separator } from '$lib/components/ui/separator';
	import { 
		PlayCircle,
		RotateCcw,
		Ban,
		ArrowUp,
		ShieldCheck,
		X,
		CheckSquare,
		Square,
		Filter,
		AlertTriangle
	} from 'lucide-svelte';

	export let selectedCount: number = 0;
	export let selectedPages: any[] = [];
	export let showToolbar: boolean = false;

	const dispatch = createEventDispatcher<{
		bulkAction: { action: string; pageIds: number[]; data?: any };
		clearSelection: void;
		selectAll: void;
		selectNone: void;
	}>();

	// Analyze selected pages to determine available actions
	$: selectedPageIds = selectedPages.map(p => p.id);
	
	$: analysisResults = analyzeSelectedPages(selectedPages);
	
	function analyzeSelectedPages(pages: any[]) {
		const statusCounts = {
			pending: 0,
			in_progress: 0,
			completed: 0,
			failed: 0,
			skipped: 0,
			filtered: 0,
			awaiting_review: 0
		};
		
		const filterCounts = {
			duplicate: 0,
			list_page: 0,
			low_quality: 0,
			size: 0,
			type: 0,
			custom: 0
		};
		
		let canRetry = 0;
		let canSkip = 0;
		let canManualProcess = 0;
		let canOverrideFilter = 0;
		let alreadyOverridden = 0;
		let hasErrors = 0;
		
		pages.forEach(page => {
			// Count statuses
			const status = page.status?.toLowerCase();
			if (status === 'pending') statusCounts.pending++;
			else if (status === 'in_progress') statusCounts.in_progress++;
			else if (status === 'completed') statusCounts.completed++;
			else if (status === 'failed') statusCounts.failed++;
			else if (status === 'skipped') statusCounts.skipped++;
			else if (status?.startsWith('filtered_')) statusCounts.filtered++;
			else if (status === 'awaiting_manual_review') statusCounts.awaiting_review++;
			
			// Count filter types
			if (status?.includes('duplicate')) filterCounts.duplicate++;
			else if (status?.includes('list_page')) filterCounts.list_page++;
			else if (status?.includes('low_quality')) filterCounts.low_quality++;
			else if (status?.includes('size')) filterCounts.size++;
			else if (status?.includes('type')) filterCounts.type++;
			else if (status?.includes('custom')) filterCounts.custom++;
			
			// Determine available actions
			if (status === 'failed') canRetry++;
			if (status === 'pending' || status === 'failed') canSkip++;
			if (status?.startsWith('filtered_') && page.can_be_manually_processed !== false) {
				canManualProcess++;
			}
			if (status?.startsWith('filtered_') && !page.is_manually_overridden) {
				canOverrideFilter++;
			}
			if (page.is_manually_overridden) alreadyOverridden++;
			if (page.error_message) hasErrors++;
		});
		
		return {
			statusCounts,
			filterCounts,
			canRetry,
			canSkip,
			canManualProcess,
			canOverrideFilter,
			alreadyOverridden,
			hasErrors,
			totalSelected: pages.length
		};
	}

	function handleBulkAction(action: string, data?: any) {
		dispatch('bulkAction', { action, pageIds: selectedPageIds, data });
	}

	function handleClearSelection() {
		dispatch('clearSelection');
	}

	function handleSelectAll() {
		dispatch('selectAll');
	}

	function handleSelectNone() {
		dispatch('selectNone');
	}

	// Get the most relevant filter type for display
	$: primaryFilterType = (() => {
		const filters = analysisResults.filterCounts;
		const maxCount = Math.max(...Object.values(filters));
		if (maxCount === 0) return null;
		
		const primaryFilter = Object.entries(filters).find(([_, count]) => count === maxCount);
		return primaryFilter ? primaryFilter[0] : null;
	})();
</script>

{#if showToolbar && selectedCount > 0}
	<Card class="bg-blue-50 border-blue-200 shadow-md">
		<CardContent class="py-4">
			<div class="space-y-4">
				<!-- Selection Summary -->
				<div class="flex items-center justify-between">
					<div class="flex items-center space-x-4">
						<div class="flex items-center space-x-2">
							<CheckSquare class="h-4 w-4 text-blue-600" />
							<span class="font-medium text-blue-900">{selectedCount} pages selected</span>
						</div>
						
						<!-- Status breakdown -->
						<div class="flex items-center space-x-2">
							{#if analysisResults.statusCounts.pending > 0}
								<Badge variant="warning" class="text-xs">
									{analysisResults.statusCounts.pending} pending
								</Badge>
							{/if}
							{#if analysisResults.statusCounts.failed > 0}
								<Badge variant="destructive" class="text-xs">
									{analysisResults.statusCounts.failed} failed
								</Badge>
							{/if}
							{#if analysisResults.statusCounts.filtered > 0}
								<Badge variant="outline" class="text-xs">
									{analysisResults.statusCounts.filtered} filtered
								</Badge>
							{/if}
							{#if analysisResults.statusCounts.completed > 0}
								<Badge variant="success" class="text-xs">
									{analysisResults.statusCounts.completed} complete
								</Badge>
							{/if}
						</div>
					</div>
					
					<!-- Selection Controls -->
					<div class="flex items-center space-x-2">
						<Button
							variant="ghost"
							size="sm"
							onclick={handleSelectAll}
							class="h-7 px-2 text-xs"
							title="Select all visible pages"
						>
							<CheckSquare class="h-3 w-3 mr-1" />
							All
						</Button>
						<Button
							variant="ghost"
							size="sm"
							onclick={handleSelectNone}
							class="h-7 px-2 text-xs"
							title="Clear selection"
						>
							<Square class="h-3 w-3 mr-1" />
							None
						</Button>
						<Separator orientation="vertical" class="h-4" />
						<Button
							variant="ghost"
							size="sm"
							onclick={handleClearSelection}
							class="h-7 px-2 text-xs text-muted-foreground"
						>
							<X class="h-3 w-3" />
						</Button>
					</div>
				</div>

				<!-- Action Buttons -->
				<div class="space-y-3">
					<!-- Processing Actions -->
					<div class="flex items-center space-x-2 flex-wrap gap-2">
						<!-- Manual Processing (for filtered content) -->
						{#if analysisResults.canManualProcess > 0}
							<Button
								variant="outline"
								size="sm"
								onclick={() => handleBulkAction('manual_process')}
								class="h-8 px-3 text-xs bg-green-50 hover:bg-green-100 border-green-200 text-green-800 dark:bg-green-950/20 dark:hover:bg-green-900/30 dark:border-green-700 dark:text-green-200"
								title="Process {analysisResults.canManualProcess} filtered pages anyway"
							>
								<PlayCircle class="h-3 w-3 mr-2" />
								Process {analysisResults.canManualProcess} Filtered
							</Button>
						{/if}

						<!-- Retry Failed -->
						{#if analysisResults.canRetry > 0}
							<Button
								variant="outline"
								size="sm"
								onclick={() => handleBulkAction('retry')}
								class="h-8 px-3 text-xs"
								title="Retry {analysisResults.canRetry} failed pages"
							>
								<RotateCcw class="h-3 w-3 mr-2" />
								Retry {analysisResults.canRetry} Failed
							</Button>
						{/if}

						<!-- Skip Pending -->
						{#if analysisResults.canSkip > 0}
							<Button
								variant="outline"
								size="sm"
								onclick={() => handleBulkAction('skip')}
								class="h-8 px-3 text-xs"
								title="Skip {analysisResults.canSkip} pages"
							>
								<Ban class="h-3 w-3 mr-2" />
								Skip {analysisResults.canSkip}
							</Button>
						{/if}

						<!-- Priority Boost -->
						{#if analysisResults.statusCounts.pending > 0 || analysisResults.statusCounts.failed > 0}
							<Button
								variant="outline"
								size="sm"
								onclick={() => handleBulkAction('priority')}
								class="h-8 px-3 text-xs"
								title="Bump to high priority queue"
							>
								<ArrowUp class="h-3 w-3 mr-2" />
								High Priority
							</Button>
						{/if}
					</div>

					<!-- Filter Override Actions -->
					{#if analysisResults.canOverrideFilter > 0 || analysisResults.alreadyOverridden > 0}
						<div class="flex items-center space-x-2 pt-2 border-t border-blue-200">
							<span class="text-xs text-muted-foreground font-medium">Filter Overrides:</span>
							
							{#if analysisResults.canOverrideFilter > 0}
								<Button
									variant="outline"
									size="sm"
									onclick={() => handleBulkAction('override_filter')}
									class="h-7 px-3 text-xs bg-amber-50 hover:bg-amber-100 border-amber-200 text-amber-800 dark:bg-amber-950/20 dark:hover:bg-amber-900/30 dark:border-amber-700 dark:text-amber-200"
									title="Override filter decisions for {analysisResults.canOverrideFilter} pages"
								>
									<ShieldCheck class="h-3 w-3 mr-1" />
									Override {analysisResults.canOverrideFilter}
								</Button>
							{/if}

							{#if analysisResults.alreadyOverridden > 0}
								<Button
									variant="outline"
									size="sm"
									onclick={() => handleBulkAction('restore_filter')}
									class="h-7 px-3 text-xs"
									title="Restore original filter decisions for {analysisResults.alreadyOverridden} pages"
								>
									<Filter class="h-3 w-3 mr-1" />
									Restore {analysisResults.alreadyOverridden}
								</Button>
							{/if}
						</div>
					{/if}

					<!-- Filter Analysis -->
					{#if analysisResults.statusCounts.filtered > 0}
						<div class="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-700 rounded p-2">
							<div class="text-xs space-y-1">
								<div class="flex items-center gap-2 text-amber-800 dark:text-amber-200 font-medium">
									<Filter class="h-3 w-3" />
									Filter Analysis:
								</div>
								<div class="grid grid-cols-2 gap-2 text-amber-700 dark:text-amber-300">
									{#if analysisResults.filterCounts.duplicate > 0}
										<div>• {analysisResults.filterCounts.duplicate} duplicates</div>
									{/if}
									{#if analysisResults.filterCounts.list_page > 0}
										<div>• {analysisResults.filterCounts.list_page} list pages</div>
									{/if}
									{#if analysisResults.filterCounts.low_quality > 0}
										<div>• {analysisResults.filterCounts.low_quality} low quality</div>
									{/if}
									{#if analysisResults.filterCounts.size > 0}
										<div>• {analysisResults.filterCounts.size} size filtered</div>
									{/if}
									{#if analysisResults.filterCounts.type > 0}
										<div>• {analysisResults.filterCounts.type} type filtered</div>
									{/if}
									{#if analysisResults.filterCounts.custom > 0}
										<div>• {analysisResults.filterCounts.custom} custom rules</div>
									{/if}
								</div>
								{#if primaryFilterType}
									<div class="text-amber-600 text-xs italic mt-1">
										Most common: {primaryFilterType.replace('_', ' ')} pages
									</div>
								{/if}
							</div>
						</div>
					{/if}

					<!-- Error Summary -->
					{#if analysisResults.hasErrors > 0}
						<div class="bg-red-50 border border-red-200 rounded p-2">
							<div class="flex items-center gap-2 text-red-800 text-xs">
								<AlertTriangle class="h-3 w-3" />
								<span class="font-medium">{analysisResults.hasErrors} pages have errors</span>
								<Button
									variant="link"
									size="sm"
									onclick={() => handleBulkAction('view_errors')}
									class="h-auto p-0 text-xs text-red-600 underline"
								>
									View Details
								</Button>
							</div>
						</div>
					{/if}
				</div>
			</div>
		</CardContent>
	</Card>
{/if}