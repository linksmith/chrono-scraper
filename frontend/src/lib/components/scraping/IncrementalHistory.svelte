<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { 
		History,
		Play,
		Pause,
		CheckCircle2,
		XCircle,
		Clock,
		Calendar,
		BarChart3,
		Zap,
		Target,
		AlertTriangle,
		RefreshCw,
		ExternalLink,
		Trash2
	} from 'lucide-svelte';
	
	import { incrementalScrapingApi, type IncrementalRun } from '$lib/services/incrementalScrapingApi';
	import { formatDate, formatNumber, getRelativeTime } from '$lib/utils';

	export let domainId: number;

	const dispatch = createEventDispatcher();

	let runs = writable<IncrementalRun[]>([]);
	let totalCount = writable(0);
	let hasMore = writable(false);
	let isLoading = false;
	let isLoadingMore = false;
	let error = '';
	let currentOffset = 0;
	let limit = 20;

	onMount(async () => {
		await loadHistory();
	});

	async function loadHistory(reset = true) {
		try {
			if (reset) {
				isLoading = true;
				currentOffset = 0;
			} else {
				isLoadingMore = true;
			}
			error = '';
			
			const response = await incrementalScrapingApi.getDomainHistory(
				domainId, 
				limit, 
				currentOffset
			);
			
			if (reset) {
				runs.set(response.runs);
			} else {
				runs.update(currentRuns => [...currentRuns, ...response.runs]);
			}
			
			totalCount.set(response.total_count);
			hasMore.set(response.has_more);
			currentOffset += response.runs.length;
			
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load history';
			console.error('Load history error:', e);
		} finally {
			isLoading = false;
			isLoadingMore = false;
		}
	}

	async function loadMore() {
		if (!$hasMore || isLoadingMore) return;
		await loadHistory(false);
	}

	async function cancelRun(runId: number) {
		try {
			const response = await incrementalScrapingApi.cancelRun(runId);
			if (response.success) {
				dispatch('runCancelled', { run_id: runId });
				// Reload the history to show updated status
				setTimeout(() => loadHistory(), 500);
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to cancel run';
			console.error('Cancel run error:', e);
		}
	}

	function selectRun(run: IncrementalRun) {
		dispatch('runSelected', { run });
	}

	function getRunStatusIcon(status: string) {
		switch (status) {
			case 'running':
				return Play;
			case 'completed':
				return CheckCircle2;
			case 'failed':
				return XCircle;
			case 'pending':
			default:
				return Clock;
		}
	}

	function getRunStatusColor(status: string) {
		switch (status) {
			case 'running':
				return 'text-blue-600';
			case 'completed':
				return 'text-green-600';
			case 'failed':
				return 'text-red-600';
			case 'pending':
			default:
				return 'text-gray-600';
		}
	}

	function getRunStatusBadge(status: string) {
		switch (status) {
			case 'running':
				return 'default';
			case 'completed':
				return 'default';
			case 'failed':
				return 'destructive';
			case 'pending':
			default:
				return 'secondary';
		}
	}

	function getRunTypeColor(runType: string) {
		switch (runType) {
			case 'scheduled':
				return 'bg-blue-100 text-blue-800';
			case 'manual':
				return 'bg-green-100 text-green-800';
			case 'gap_fill':
				return 'bg-purple-100 text-purple-800';
			default:
				return 'bg-gray-100 text-gray-800';
		}
	}

	function getRunTypeIcon(runType: string) {
		switch (runType) {
			case 'scheduled':
				return Calendar;
			case 'manual':
				return Play;
			case 'gap_fill':
				return Zap;
			default:
				return Clock;
		}
	}

	function formatDuration(seconds: number | null) {
		if (!seconds) return 'N/A';
		
		if (seconds < 60) return `${seconds}s`;
		if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
		
		const hours = Math.floor(seconds / 3600);
		const minutes = Math.floor((seconds % 3600) / 60);
		return `${hours}h ${minutes}m`;
	}

	function getSuccessRate(run: IncrementalRun) {
		if (run.pages_discovered === 0) return 0;
		return (run.pages_processed / run.pages_discovered) * 100;
	}

	$: sortedRuns = $runs.sort((a, b) => 
		new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
	);
</script>

<div class="space-y-6">
	{#if error}
		<Alert variant="destructive">
			<AlertTriangle class="h-4 w-4" />
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<Card>
		<CardHeader>
			<CardTitle class="flex items-center justify-between">
				<div class="flex items-center space-x-2">
					<History class="h-5 w-5" />
					<span>Scraping History</span>
					<Badge variant="outline">
						{formatNumber($totalCount)} total runs
					</Badge>
				</div>
				<Button
					variant="outline"
					size="sm"
					onclick={() => loadHistory()}
					disabled={isLoading}
				>
					{#if isLoading}
						<RefreshCw class="h-4 w-4 mr-2 animate-spin" />
					{:else}
						<RefreshCw class="h-4 w-4 mr-2" />
					{/if}
					Refresh
				</Button>
			</CardTitle>
		</CardHeader>
		<CardContent>
			{#if isLoading}
				<div class="space-y-4">
					{#each Array(3) as _}
						<div class="animate-pulse">
							<div class="h-24 bg-gray-200 rounded"></div>
						</div>
					{/each}
				</div>
			{:else if sortedRuns.length === 0}
				<div class="text-center py-8">
					<History class="h-12 w-12 text-gray-400 mx-auto mb-4" />
					<h3 class="text-lg font-medium text-gray-900 mb-2">No History Available</h3>
					<p class="text-gray-600">
						No incremental scraping runs have been executed for this domain yet.
					</p>
				</div>
			{:else}
				<div class="space-y-4 max-h-96 overflow-y-auto">
					{#each sortedRuns as run}
						<div 
							class="border rounded-lg p-4 hover:bg-gray-50 transition-colors cursor-pointer"
							onclick={() => selectRun(run)}
							role="button"
							tabindex="0"
							onkeydown={(e) => {
								if (e.key === 'Enter' || e.key === ' ') {
									e.preventDefault();
									selectRun(run);
								}
							}}
						>
							<div class="flex items-start justify-between">
								<div class="flex-1">
									<div class="flex items-center space-x-3 mb-2">
										<div class="flex items-center space-x-2">
											<svelte:component 
												this={getRunStatusIcon(run.status)}
												class="h-4 w-4 {getRunStatusColor(run.status)}"
											/>
											<Badge variant={getRunStatusBadge(run.status)}>
												{run.status}
											</Badge>
										</div>
										
										<div class="flex items-center space-x-2">
											<svelte:component 
												this={getRunTypeIcon(run.run_type)}
												class="h-4 w-4"
											/>
											<Badge class={getRunTypeColor(run.run_type)}>
												{run.run_type.replace('_', ' ')}
											</Badge>
										</div>
										
										<span class="text-sm text-gray-600">
											{getRelativeTime(run.created_at)}
										</span>
									</div>
									
									<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-sm text-gray-600">
										<div class="flex items-center space-x-2">
											<Calendar class="h-4 w-4" />
											<span>
												{formatDate(run.coverage_start)} - {formatDate(run.coverage_end)}
											</span>
										</div>
										
										<div class="flex items-center space-x-2">
											<BarChart3 class="h-4 w-4" />
											<span>
												{formatNumber(run.pages_processed)} / {formatNumber(run.pages_discovered)} pages
												{#if run.pages_discovered > 0}
													<span class="text-xs">
														({getSuccessRate(run).toFixed(1)}%)
													</span>
												{/if}
											</span>
										</div>
										
										{#if run.gaps_filled > 0}
											<div class="flex items-center space-x-2">
												<Target class="h-4 w-4" />
												<span class="text-green-600">
													{formatNumber(run.gaps_filled)} gaps filled
												</span>
											</div>
										{/if}
										
										<div class="flex items-center space-x-2">
											<Clock class="h-4 w-4" />
											<span>
												{formatDuration(run.duration_seconds)}
											</span>
										</div>
									</div>

									{#if run.error_message && run.status === 'failed'}
										<div class="mt-3 p-2 bg-red-50 border border-red-200 rounded text-sm">
											<div class="flex items-center space-x-2">
												<AlertTriangle class="h-4 w-4 text-red-600" />
												<span class="text-red-800">
													{run.error_message}
												</span>
											</div>
										</div>
									{/if}
								</div>
								
								<div class="flex items-center space-x-2 ml-4">
									{#if run.status === 'running'}
										<Button
											variant="outline"
											size="sm"
											onclick={(e) => {
												e.stopPropagation();
												cancelRun(run.id);
											}}
										>
											<Pause class="h-4 w-4 mr-1" />
											Cancel
										</Button>
									{/if}
									
									<Button
										variant="ghost"
										size="sm"
										onclick={(e) => {
											e.stopPropagation();
											selectRun(run);
										}}
									>
										<ExternalLink class="h-4 w-4" />
									</Button>
								</div>
							</div>
						</div>
					{/each}
				</div>

				{#if $hasMore}
					<div class="flex justify-center pt-4">
						<Button
							variant="outline"
							onclick={loadMore}
							disabled={isLoadingMore}
						>
							{#if isLoadingMore}
								<RefreshCw class="h-4 w-4 mr-2 animate-spin" />
							{/if}
							Load More
						</Button>
					</div>
				{/if}
			{/if}
		</CardContent>
	</Card>
</div>