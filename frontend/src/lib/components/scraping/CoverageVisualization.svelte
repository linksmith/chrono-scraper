<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Progress } from '$lib/components/ui/progress';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { 
		Calendar,
		Clock,
		AlertTriangle,
		TrendingUp,
		Target,
		Zap,
		BarChart3,
		Info
	} from 'lucide-svelte';
	
	import { incrementalScrapingApi, type CoverageGap } from '$lib/services/incrementalScrapingApi';
	import { formatDate, formatNumber, getRelativeTime } from '$lib/utils';

	export let domainId: number;
	export let projectId: number;

	const dispatch = createEventDispatcher();

	let gaps = writable<CoverageGap[]>([]);
	let isLoading = false;
	let error = '';
	let selectedGaps = new Set<number>();
	let isFillingGaps = false;

	onMount(async () => {
		await loadCoverageGaps();
	});

	async function loadCoverageGaps() {
		try {
			isLoading = true;
			error = '';
			
			const coverageGaps = await incrementalScrapingApi.getDomainGaps(domainId);
			gaps.set(coverageGaps);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load coverage gaps';
			console.error('Load coverage gaps error:', e);
		} finally {
			isLoading = false;
		}
	}

	async function fillSelectedGaps() {
		if (selectedGaps.size === 0 || isFillingGaps) return;
		
		try {
			isFillingGaps = true;
			error = '';
			
			const gapIds = Array.from(selectedGaps);
			const response = await incrementalScrapingApi.fillCoverageGaps(gapIds);
			
			dispatch('gapSelected', {
				action: 'fill',
				gap_ids: gapIds,
				task_id: response.task_id,
				run_ids: response.run_ids
			});
			
			// Clear selection and reload gaps
			selectedGaps.clear();
			selectedGaps = selectedGaps;
			setTimeout(loadCoverageGaps, 1000);
			
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to fill coverage gaps';
			console.error('Fill gaps error:', e);
		} finally {
			isFillingGaps = false;
		}
	}

	function toggleGapSelection(gapIndex: number) {
		if (selectedGaps.has(gapIndex)) {
			selectedGaps.delete(gapIndex);
		} else {
			selectedGaps.add(gapIndex);
		}
		selectedGaps = selectedGaps;
	}

	function selectAllGaps() {
		selectedGaps = new Set($gaps.map((_, index) => index));
	}

	function clearSelection() {
		selectedGaps.clear();
		selectedGaps = selectedGaps;
	}

	function getPriorityColor(priority: number) {
		if (priority >= 8) return 'bg-red-100 text-red-800';
		if (priority >= 6) return 'bg-yellow-100 text-yellow-800';
		if (priority >= 4) return 'bg-blue-100 text-blue-800';
		return 'bg-gray-100 text-gray-800';
	}

	function getPriorityLabel(priority: number) {
		if (priority >= 8) return 'High';
		if (priority >= 6) return 'Medium';
		if (priority >= 4) return 'Low';
		return 'Very Low';
	}

	function getDurationColor(days: number) {
		if (days >= 30) return 'text-red-600';
		if (days >= 7) return 'text-yellow-600';
		return 'text-blue-600';
	}

	$: totalGaps = $gaps.length;
	$: totalMissingDays = $gaps.reduce((sum, gap) => sum + gap.days_missing, 0);
	$: totalEstimatedPages = $gaps.reduce((sum, gap) => sum + gap.estimated_pages, 0);
	$: highPriorityGaps = $gaps.filter(gap => gap.priority_score >= 8).length;
	$: selectedGapsCount = selectedGaps.size;
	$: selectedEstimatedPages = $gaps
		.filter((_, index) => selectedGaps.has(index))
		.reduce((sum, gap) => sum + gap.estimated_pages, 0);
</script>

<div class="space-y-6">
	{#if error}
		<Alert variant="destructive">
			<AlertTriangle class="h-4 w-4" />
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Coverage Overview -->
	<div class="grid grid-cols-1 md:grid-cols-4 gap-4">
		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-medium text-gray-600">Total Gaps</p>
						<p class="text-2xl font-bold text-red-600">
							{formatNumber(totalGaps)}
						</p>
					</div>
					<Target class="h-8 w-8 text-gray-400" />
				</div>
			</CardContent>
		</Card>

		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-medium text-gray-600">Missing Days</p>
						<p class="text-2xl font-bold text-yellow-600">
							{formatNumber(totalMissingDays)}
						</p>
					</div>
					<Calendar class="h-8 w-8 text-gray-400" />
				</div>
			</CardContent>
		</Card>

		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-medium text-gray-600">Est. Pages</p>
						<p class="text-2xl font-bold text-blue-600">
							{formatNumber(totalEstimatedPages)}
						</p>
					</div>
					<BarChart3 class="h-8 w-8 text-gray-400" />
				</div>
			</CardContent>
		</Card>

		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-medium text-gray-600">High Priority</p>
						<p class="text-2xl font-bold text-red-600">
							{formatNumber(highPriorityGaps)}
						</p>
					</div>
					<AlertTriangle class="h-8 w-8 text-gray-400" />
				</div>
			</CardContent>
		</Card>
	</div>

	{#if totalGaps > 0}
		<!-- Gap Management Actions -->
		<div class="flex items-center justify-between">
			<div class="flex items-center space-x-4">
				<Button
					variant="outline"
					size="sm"
					onclick={selectAllGaps}
					disabled={isLoading}
				>
					Select All
				</Button>
				<Button
					variant="outline"
					size="sm"
					onclick={clearSelection}
					disabled={selectedGapsCount === 0}
				>
					Clear Selection
				</Button>
				{#if selectedGapsCount > 0}
					<Badge variant="secondary">
						{selectedGapsCount} selected ({formatNumber(selectedEstimatedPages)} pages)
					</Badge>
				{/if}
			</div>
			
			{#if selectedGapsCount > 0}
				<Button
					onclick={fillSelectedGaps}
					disabled={isFillingGaps}
					size="sm"
				>
					{#if isFillingGaps}
						<div class="animate-spin h-4 w-4 mr-2 border-2 border-current border-r-transparent rounded-full"></div>
					{:else}
						<Zap class="h-4 w-4 mr-2" />
					{/if}
					Fill {selectedGapsCount} Gap{selectedGapsCount !== 1 ? 's' : ''}
				</Button>
			{/if}
		</div>

		<!-- Coverage Gaps List -->
		<Card>
			<CardHeader>
				<CardTitle class="flex items-center space-x-2">
					<Calendar class="h-5 w-5" />
					<span>Coverage Gaps</span>
					{#if isLoading}
						<div class="animate-spin h-4 w-4 border-2 border-current border-r-transparent rounded-full"></div>
					{/if}
				</CardTitle>
			</CardHeader>
			<CardContent>
				{#if isLoading}
					<div class="space-y-3">
						{#each Array(3) as _}
							<div class="animate-pulse">
								<div class="h-20 bg-gray-200 rounded"></div>
							</div>
						{/each}
					</div>
				{:else}
					<div class="space-y-3 max-h-96 overflow-y-auto">
						{#each $gaps as gap, index}
							<div 
								class="border rounded-lg p-4 hover:bg-gray-50 transition-colors {selectedGaps.has(index) ? 'ring-2 ring-primary bg-primary/5' : ''}"
								role="button"
								tabindex="0"
								onclick={() => toggleGapSelection(index)}
								onkeydown={(e) => {
									if (e.key === 'Enter' || e.key === ' ') {
										e.preventDefault();
										toggleGapSelection(index);
									}
								}}
							>
								<div class="flex items-start justify-between">
									<div class="flex-1">
										<div class="flex items-center space-x-3 mb-2">
											<div class="flex items-center space-x-2">
												<Calendar class="h-4 w-4 text-gray-400" />
												<span class="font-medium">
													{formatDate(gap.gap_start)} - {formatDate(gap.gap_end)}
												</span>
											</div>
											<Badge class={getPriorityColor(gap.priority_score)}>
												{getPriorityLabel(gap.priority_score)}
											</Badge>
										</div>
										
										<div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm text-gray-600">
											<div class="flex items-center space-x-2">
												<Clock class="h-4 w-4" />
												<span class={getDurationColor(gap.days_missing)}>
													{gap.days_missing} days missing
												</span>
											</div>
											<div class="flex items-center space-x-2">
												<BarChart3 class="h-4 w-4" />
												<span>~{formatNumber(gap.estimated_pages)} pages</span>
											</div>
											<div class="flex items-center space-x-2">
												<TrendingUp class="h-4 w-4" />
												<span>Priority: {gap.priority_score.toFixed(1)}/10</span>
											</div>
										</div>
									</div>
									
									<div class="flex items-center space-x-2 ml-4">
										<input
											type="checkbox"
											class="h-4 w-4 text-primary focus:ring-primary border-gray-300 rounded"
											checked={selectedGaps.has(index)}
											onchange={() => toggleGapSelection(index)}
											onclick={(e) => e.stopPropagation()}
										/>
									</div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</CardContent>
		</Card>
	{:else if !isLoading}
		<!-- No Gaps State -->
		<Card>
			<CardContent class="pt-6">
				<div class="text-center py-8">
					<Target class="h-12 w-12 text-gray-400 mx-auto mb-4" />
					<h3 class="text-lg font-medium text-gray-900 mb-2">No Coverage Gaps</h3>
					<p class="text-gray-600">
						This domain has complete coverage with no gaps detected. 
						Incremental scraping will focus on maintaining current coverage.
					</p>
				</div>
			</CardContent>
		</Card>
	{/if}

	{#if totalGaps > 0}
		<!-- Information Panel -->
		<Alert>
			<Info class="h-4 w-4" />
			<AlertDescription>
				<strong>Coverage gaps</strong> represent periods where no content was captured. 
				Gaps are prioritized based on content density, recency, and domain importance. 
				Use "Fill Gaps" to target specific time periods for incremental scraping.
			</AlertDescription>
		</Alert>
	{/if}
</div>