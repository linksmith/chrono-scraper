<script lang="ts">
	import { createEventDispatcher, onMount, onDestroy } from 'svelte';
	import { writable } from 'svelte/store';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { Switch } from '$lib/components/ui/switch';
	import { Slider } from '$lib/components/ui/slider';
	import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Progress } from '$lib/components/ui/progress';
	import { 
		Play, 
		Pause, 
		Settings, 
		Calendar, 
		BarChart3, 
		Clock, 
		AlertCircle,
		CheckCircle2,
		RefreshCw,
		Zap,
		Target,
		Gauge,
		History,
		Activity,
		TrendingUp
	} from 'lucide-svelte';
	
	import { incrementalScrapingApi } from '$lib/services/incrementalScrapingApi';
	import { formatDate, formatNumber, getRelativeTime } from '$lib/utils';
	import { websocket } from '$lib/stores/websocket';
	
	import CoverageVisualization from './CoverageVisualization.svelte';
	import IncrementalHistory from './IncrementalHistory.svelte';
	import IncrementalConfig from './IncrementalConfig.svelte';

	export let domainId: number;
	export let projectId: number;
	export let domainName: string = '';
	export let canControl: boolean = true;

	const dispatch = createEventDispatcher();

	let status = writable({
		enabled: false,
		last_run_date: null,
		next_run_date: null,
		coverage_percentage: 0,
		total_gaps: 0,
		overlap_days: 3,
		auto_schedule: false,
		max_pages_per_run: 1000,
		run_frequency_hours: 24
	});

	let projectStats = writable({
		total_domains: 0,
		enabled_domains: 0,
		avg_coverage_percentage: 0,
		total_gaps: 0,
		last_run_date: null,
		next_scheduled_run: null,
		active_runs: 0,
		completed_runs_24h: 0,
		failed_runs_24h: 0
	});

	let isLoading = false;
	let error = '';
	let activeTab = 'overview';
	let isTriggering = false;
	let wsUnsubscribe: (() => void) | null = null;

	// Load initial data
	onMount(async () => {
		await Promise.all([loadDomainStatus(), loadProjectStats()]);
		setupWebSocketListener();
	});

	onDestroy(() => {
		if (wsUnsubscribe) {
			wsUnsubscribe();
		}
	});

	async function loadDomainStatus() {
		try {
			isLoading = true;
			error = '';
			
			const domainStatus = await incrementalScrapingApi.getDomainStatus(domainId);
			status.set(domainStatus);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load domain status';
			console.error('Load domain status error:', e);
		} finally {
			isLoading = false;
		}
	}

	async function loadProjectStats() {
		try {
			const stats = await incrementalScrapingApi.getProjectStats(projectId);
			projectStats.set(stats);
		} catch (e) {
			console.error('Load project stats error:', e);
		}
	}

	function setupWebSocketListener() {
		if (wsUnsubscribe) {
			wsUnsubscribe();
		}

		wsUnsubscribe = websocket.subscribe((message) => {
			if (
				message?.type === 'task_progress' && 
				message.payload?.task_type === 'incremental_scraping'
			) {
				handleIncrementalScrapingUpdate(message.payload);
			}
		});
	}

	function handleIncrementalScrapingUpdate(payload: any) {
		if (payload.domain_id === domainId) {
			// Update domain status if this domain is being processed
			loadDomainStatus();
		}
		
		// Always update project stats for any incremental scraping activity
		loadProjectStats();
		
		dispatch('incrementalUpdate', {
			domain_id: payload.domain_id,
			status: payload.status,
			progress: payload.progress_percentage,
			gaps_filled: payload.gaps_filled
		});
	}

	async function triggerIncrementalScraping(runType: 'manual' | 'gap_fill' = 'manual') {
		if (!canControl || isTriggering) return;
		
		try {
			isTriggering = true;
			error = '';
			
			const response = await incrementalScrapingApi.triggerIncrementalScraping(projectId, {
				run_type: runType,
				domain_ids: [domainId],
				force_full_coverage: false,
				priority_boost: runType === 'gap_fill'
			});
			
			dispatch('scrapeTriggered', {
				task_id: response.task_id,
				run_ids: response.run_ids,
				run_type: runType
			});
			
			// Reload status after a brief delay
			setTimeout(() => {
				loadDomainStatus();
				loadProjectStats();
			}, 1000);
			
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to trigger incremental scraping';
			console.error('Trigger incremental scraping error:', e);
		} finally {
			isTriggering = false;
		}
	}

	async function toggleIncrementalScraping() {
		if (!canControl) return;
		
		try {
			isLoading = true;
			error = '';
			
			const currentStatus = $status;
			const newConfig = {
				enabled: !currentStatus.enabled,
				overlap_days: currentStatus.overlap_days,
				auto_schedule: currentStatus.auto_schedule,
				max_pages_per_run: currentStatus.max_pages_per_run,
				run_frequency_hours: currentStatus.run_frequency_hours
			};
			
			const updatedStatus = await incrementalScrapingApi.updateDomainConfig(domainId, newConfig);
			status.set(updatedStatus);
			
			dispatch('configUpdated', { enabled: updatedStatus.enabled });
			
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to toggle incremental scraping';
			console.error('Toggle incremental scraping error:', e);
		} finally {
			isLoading = false;
		}
	}

	function handleConfigUpdate(event: CustomEvent) {
		const updatedConfig = event.detail;
		status.update(s => ({ ...s, ...updatedConfig }));
		dispatch('configUpdated', updatedConfig);
	}

	function getStatusIcon(enabled: boolean, hasRunning: boolean) {
		if (hasRunning) return Activity;
		if (enabled) return CheckCircle2;
		return Pause;
	}

	function getStatusColor(enabled: boolean, hasRunning: boolean) {
		if (hasRunning) return 'text-blue-600';
		if (enabled) return 'text-green-600';
		return 'text-gray-600';
	}

	function getCoverageColor(percentage: number) {
		if (percentage >= 90) return 'text-green-600';
		if (percentage >= 70) return 'text-yellow-600';
		return 'text-red-600';
	}

	$: isEnabled = $status.enabled;
	$: hasActiveRuns = $projectStats.active_runs > 0;
	$: coveragePercentage = $status.coverage_percentage;
	$: totalGaps = $status.total_gaps;
	$: lastRunDate = $status.last_run_date;
	$: nextRunDate = $status.next_run_date;
</script>

<Card class="w-full">
	<CardHeader>
		<CardTitle class="flex items-center justify-between">
			<div class="flex items-center space-x-2">
				<TrendingUp class="h-5 w-5" />
				<span>Incremental Scraping</span>
				{#if domainName}
					<Badge variant="outline" class="text-xs">
						{domainName}
					</Badge>
				{/if}
			</div>
			<div class="flex items-center space-x-2">
				<svelte:component 
					this={getStatusIcon(isEnabled, hasActiveRuns)} 
					class="h-4 w-4 {getStatusColor(isEnabled, hasActiveRuns)}" 
				/>
				<Badge variant={isEnabled ? 'default' : 'secondary'}>
					{isEnabled ? 'Enabled' : 'Disabled'}
				</Badge>
				{#if hasActiveRuns}
					<Badge variant="default" class="bg-blue-100 text-blue-800">
						{$projectStats.active_runs} Running
					</Badge>
				{/if}
			</div>
		</CardTitle>
	</CardHeader>
	<CardContent>
		{#if error}
			<Alert class="mb-4" variant="destructive">
				<AlertCircle class="h-4 w-4" />
				<AlertDescription>{error}</AlertDescription>
			</Alert>
		{/if}

		<Tabs bind:value={activeTab} class="w-full">
			<TabsList class="grid w-full grid-cols-4">
				<TabsTrigger value="overview" class="flex items-center gap-2">
					<Gauge class="h-4 w-4" />
					Overview
				</TabsTrigger>
				<TabsTrigger value="coverage" class="flex items-center gap-2">
					<BarChart3 class="h-4 w-4" />
					Coverage
				</TabsTrigger>
				<TabsTrigger value="history" class="flex items-center gap-2">
					<History class="h-4 w-4" />
					History
				</TabsTrigger>
				<TabsTrigger value="config" class="flex items-center gap-2">
					<Settings class="h-4 w-4" />
					Config
				</TabsTrigger>
			</TabsList>

			<TabsContent value="overview" class="space-y-4">
				<!-- Status Overview -->
				<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
					<Card>
						<CardContent class="pt-6">
							<div class="flex items-center justify-between">
								<div>
									<p class="text-sm font-medium text-gray-600">Coverage</p>
									<div class="flex items-center space-x-2">
										<p class="text-2xl font-bold {getCoverageColor(coveragePercentage)}">
											{coveragePercentage.toFixed(1)}%
										</p>
									</div>
								</div>
								<BarChart3 class="h-8 w-8 text-gray-400" />
							</div>
							<Progress value={coveragePercentage} class="mt-3" />
						</CardContent>
					</Card>

					<Card>
						<CardContent class="pt-6">
							<div class="flex items-center justify-between">
								<div>
									<p class="text-sm font-medium text-gray-600">Gaps Detected</p>
									<p class="text-2xl font-bold {totalGaps > 0 ? 'text-yellow-600' : 'text-green-600'}">
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
									<p class="text-sm font-medium text-gray-600">Last Run</p>
									<p class="text-sm font-bold text-gray-900">
										{lastRunDate ? getRelativeTime(lastRunDate) : 'Never'}
									</p>
									{#if nextRunDate && isEnabled}
										<p class="text-xs text-gray-500 mt-1">
											Next: {getRelativeTime(nextRunDate)}
										</p>
									{/if}
								</div>
								<Clock class="h-8 w-8 text-gray-400" />
							</div>
						</CardContent>
					</Card>
				</div>

				<!-- Control Actions -->
				<div class="flex flex-wrap items-center gap-3">
					<Button
						variant="outline"
						size="sm"
						onclick={toggleIncrementalScraping}
						disabled={!canControl || isLoading}
					>
						{#if isLoading}
							<RefreshCw class="h-4 w-4 mr-2 animate-spin" />
						{:else if isEnabled}
							<Pause class="h-4 w-4 mr-2" />
						{:else}
							<Play class="h-4 w-4 mr-2" />
						{/if}
						{isEnabled ? 'Disable' : 'Enable'}
					</Button>

					{#if isEnabled}
						<Button
							onclick={() => triggerIncrementalScraping('manual')}
							disabled={!canControl || isTriggering || hasActiveRuns}
							size="sm"
						>
							{#if isTriggering}
								<RefreshCw class="h-4 w-4 mr-2 animate-spin" />
							{:else}
								<Play class="h-4 w-4 mr-2" />
							{/if}
							Run Now
						</Button>

						{#if totalGaps > 0}
							<Button
								variant="secondary"
								size="sm"
								onclick={() => triggerIncrementalScraping('gap_fill')}
								disabled={!canControl || isTriggering || hasActiveRuns}
							>
								{#if isTriggering}
									<RefreshCw class="h-4 w-4 mr-2 animate-spin" />
								{:else}
									<Zap class="h-4 w-4 mr-2" />
								{/if}
								Fill Gaps ({totalGaps})
							</Button>
						{/if}
					{/if}
				</div>

				<!-- Project-wide Statistics -->
				<Card>
					<CardHeader>
						<CardTitle class="text-base">Project Statistics</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
							<div>
								<p class="text-gray-600">Enabled Domains</p>
								<p class="font-semibold">
									{$projectStats.enabled_domains} / {$projectStats.total_domains}
								</p>
							</div>
							<div>
								<p class="text-gray-600">Avg Coverage</p>
								<p class="font-semibold {getCoverageColor($projectStats.avg_coverage_percentage)}">
									{$projectStats.avg_coverage_percentage.toFixed(1)}%
								</p>
							</div>
							<div>
								<p class="text-gray-600">Completed (24h)</p>
								<p class="font-semibold text-green-600">
									{$projectStats.completed_runs_24h}
								</p>
							</div>
							<div>
								<p class="text-gray-600">Failed (24h)</p>
								<p class="font-semibold {$projectStats.failed_runs_24h > 0 ? 'text-red-600' : 'text-gray-600'}">
									{$projectStats.failed_runs_24h}
								</p>
							</div>
						</div>
					</CardContent>
				</Card>
			</TabsContent>

			<TabsContent value="coverage">
				<CoverageVisualization 
					{domainId} 
					{projectId}
					on:gapSelected
				/>
			</TabsContent>

			<TabsContent value="history">
				<IncrementalHistory 
					{domainId} 
					on:runSelected
					on:runCancelled
				/>
			</TabsContent>

			<TabsContent value="config">
				<IncrementalConfig 
					{domainId}
					config={$status}
					{canControl}
					on:configUpdated={handleConfigUpdate}
				/>
			</TabsContent>
		</Tabs>
	</CardContent>
</Card>