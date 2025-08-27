<script lang="ts">
	import { createEventDispatcher, onMount, onDestroy } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Progress } from '$lib/components/ui/progress';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Separator } from '$lib/components/ui/separator';
	import { 
		TrendingUp,
		BarChart3,
		Target,
		Clock,
		Activity,
		CheckCircle2,
		AlertTriangle,
		Play,
		RefreshCw,
		Calendar,
		Gauge,
		Zap,
		Globe,
		Settings
	} from 'lucide-svelte';
	
	import { incrementalScrapingApi, type IncrementalScrapingStats } from '$lib/services/incrementalScrapingApi';
	import { formatNumber, formatDate, getRelativeTime } from '$lib/utils';
	import { websocket } from '$lib/stores/websocket';

	export let projectId: number;
	export let projectName: string = '';
	export let showDomainBreakdown: boolean = true;

	const dispatch = createEventDispatcher();

	let stats = writable<IncrementalScrapingStats>({
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

	let domainBreakdown = writable<Array<{
		domain_id: number;
		domain_name: string;
		enabled: boolean;
		coverage_percentage: number;
		total_gaps: number;
		last_run_date: string | null;
		status: string;
	}>>([]);

	let isLoading = false;
	let error = '';
	let wsUnsubscribe: (() => void) | null = null;

	onMount(async () => {
		await loadStats();
		if (showDomainBreakdown) {
			await loadDomainBreakdown();
		}
		setupWebSocketListener();
	});

	onDestroy(() => {
		if (wsUnsubscribe) {
			wsUnsubscribe();
		}
	});

	async function loadStats() {
		try {
			isLoading = true;
			error = '';
			
			const projectStats = await incrementalScrapingApi.getProjectStats(projectId);
			stats.set(projectStats);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load statistics';
			console.error('Load stats error:', e);
		} finally {
			isLoading = false;
		}
	}

	async function loadDomainBreakdown() {
		try {
			// This would require a new API endpoint for domain-level breakdown
			// For now, we'll mock this or skip it
			console.log('Domain breakdown loading would go here');
		} catch (e) {
			console.error('Load domain breakdown error:', e);
		}
	}

	function setupWebSocketListener() {
		if (wsUnsubscribe) {
			wsUnsubscribe();
		}

		wsUnsubscribe = websocket.subscribe((message) => {
			if (
				message?.type === 'task_progress' && 
				message.payload?.task_type === 'incremental_scraping' &&
				message.payload?.project_id === projectId
			) {
				// Reload stats when incremental scraping updates occur
				setTimeout(loadStats, 1000);
			}
		});
	}

	async function triggerProjectWideIncremental() {
		try {
			const response = await incrementalScrapingApi.triggerIncrementalScraping(projectId, {
				run_type: 'manual',
				force_full_coverage: false,
				priority_boost: false
			});
			
			dispatch('scrapeTriggered', {
				task_id: response.task_id,
				run_ids: response.run_ids,
				scope: 'project'
			});
			
			// Reload stats after a brief delay
			setTimeout(loadStats, 1000);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to trigger project-wide incremental scraping';
			console.error('Trigger project incremental error:', e);
		}
	}

	function getCoverageColor(percentage: number) {
		if (percentage >= 90) return 'text-green-600';
		if (percentage >= 70) return 'text-yellow-600';
		return 'text-red-600';
	}

	function getHealthIndicator() {
		const avgCoverage = $stats.avg_coverage_percentage;
		const failureRate = $stats.failed_runs_24h / Math.max($stats.completed_runs_24h + $stats.failed_runs_24h, 1);
		
		if (avgCoverage >= 90 && failureRate <= 0.1) return { status: 'excellent', color: 'text-green-600', icon: CheckCircle2 };
		if (avgCoverage >= 75 && failureRate <= 0.2) return { status: 'good', color: 'text-blue-600', icon: TrendingUp };
		if (avgCoverage >= 50 && failureRate <= 0.3) return { status: 'fair', color: 'text-yellow-600', icon: AlertTriangle };
		return { status: 'needs attention', color: 'text-red-600', icon: AlertTriangle };
	}

	$: healthIndicator = getHealthIndicator();
	$: hasActiveRuns = $stats.active_runs > 0;
	$: enabledDomainPercentage = $stats.total_domains > 0 ? ($stats.enabled_domains / $stats.total_domains) * 100 : 0;
</script>

<div class="space-y-6">
	{#if error}
		<Alert variant="destructive">
			<AlertTriangle class="h-4 w-4" />
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold flex items-center space-x-2">
				<TrendingUp class="h-6 w-6" />
				<span>Incremental Scraping</span>
			</h2>
			{#if projectName}
				<p class="text-muted-foreground">Project: {projectName}</p>
			{/if}
		</div>
		
		<div class="flex items-center space-x-3">
			<Button
				variant="outline"
				size="sm"
				onclick={loadStats}
				disabled={isLoading}
			>
				{#if isLoading}
					<RefreshCw class="h-4 w-4 mr-2 animate-spin" />
				{:else}
					<RefreshCw class="h-4 w-4 mr-2" />
				{/if}
				Refresh
			</Button>
			
			<Button
				onclick={triggerProjectWideIncremental}
				disabled={hasActiveRuns}
				size="sm"
			>
				<Play class="h-4 w-4 mr-2" />
				Run All Domains
			</Button>
		</div>
	</div>

	<!-- Overview Statistics -->
	<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-medium text-gray-600">System Health</p>
						<div class="flex items-center space-x-2 mt-1">
							<svelte:component 
								this={healthIndicator.icon}
								class="h-5 w-5 {healthIndicator.color}"
							/>
							<span class="font-bold {healthIndicator.color} capitalize">
								{healthIndicator.status}
							</span>
						</div>
					</div>
					<Gauge class="h-8 w-8 text-gray-400" />
				</div>
			</CardContent>
		</Card>

		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-medium text-gray-600">Avg Coverage</p>
						<p class="text-2xl font-bold {getCoverageColor($stats.avg_coverage_percentage)}">
							{$stats.avg_coverage_percentage.toFixed(1)}%
						</p>
					</div>
					<BarChart3 class="h-8 w-8 text-gray-400" />
				</div>
				<Progress value={$stats.avg_coverage_percentage} class="mt-3" />
			</CardContent>
		</Card>

		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-medium text-gray-600">Enabled Domains</p>
						<p class="text-2xl font-bold">
							{$stats.enabled_domains} / {$stats.total_domains}
						</p>
						<p class="text-xs text-gray-500">
							{enabledDomainPercentage.toFixed(0)}% enabled
						</p>
					</div>
					<Globe class="h-8 w-8 text-gray-400" />
				</div>
			</CardContent>
		</Card>

		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-medium text-gray-600">Total Gaps</p>
						<p class="text-2xl font-bold {$stats.total_gaps > 0 ? 'text-yellow-600' : 'text-green-600'}">
							{formatNumber($stats.total_gaps)}
						</p>
					</div>
					<Target class="h-8 w-8 text-gray-400" />
				</div>
			</CardContent>
		</Card>
	</div>

	<!-- Activity Overview -->
	<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
		<Card>
			<CardHeader>
				<CardTitle class="flex items-center space-x-2">
					<Activity class="h-5 w-5" />
					<span>Recent Activity</span>
				</CardTitle>
			</CardHeader>
			<CardContent class="space-y-4">
				<div class="grid grid-cols-2 gap-4">
					<div>
						<p class="text-sm text-gray-600">Active Runs</p>
						<div class="flex items-center space-x-2">
							<span class="text-2xl font-bold {hasActiveRuns ? 'text-blue-600' : 'text-gray-600'}">
								{$stats.active_runs}
							</span>
							{#if hasActiveRuns}
								<Badge variant="default" class="bg-blue-100 text-blue-800">
									Running
								</Badge>
							{/if}
						</div>
					</div>
					<div>
						<p class="text-sm text-gray-600">Success Rate (24h)</p>
						<span class="text-2xl font-bold">
							{#if $stats.completed_runs_24h + $stats.failed_runs_24h > 0}
								{Math.round(($stats.completed_runs_24h / ($stats.completed_runs_24h + $stats.failed_runs_24h)) * 100)}%
							{:else}
								N/A
							{/if}
						</span>
					</div>
				</div>

				<Separator />

				<div class="space-y-3">
					<div class="flex items-center justify-between">
						<span class="text-sm text-gray-600">Completed (24h)</span>
						<span class="font-semibold text-green-600">{$stats.completed_runs_24h}</span>
					</div>
					<div class="flex items-center justify-between">
						<span class="text-sm text-gray-600">Failed (24h)</span>
						<span class="font-semibold {$stats.failed_runs_24h > 0 ? 'text-red-600' : 'text-gray-600'}">
							{$stats.failed_runs_24h}
						</span>
					</div>
				</div>
			</CardContent>
		</Card>

		<Card>
			<CardHeader>
				<CardTitle class="flex items-center space-x-2">
					<Clock class="h-5 w-5" />
					<span>Schedule Information</span>
				</CardTitle>
			</CardHeader>
			<CardContent class="space-y-4">
				<div class="space-y-3">
					<div>
						<p class="text-sm text-gray-600">Last Run</p>
						<p class="font-semibold">
							{#if $stats.last_run_date}
								{getRelativeTime($stats.last_run_date)}
								<span class="text-xs text-gray-500 block">
									{formatDate($stats.last_run_date)}
								</span>
							{:else}
								Never
							{/if}
						</p>
					</div>
					<div>
						<p class="text-sm text-gray-600">Next Scheduled</p>
						<p class="font-semibold">
							{#if $stats.next_scheduled_run}
								{getRelativeTime($stats.next_scheduled_run)}
								<span class="text-xs text-gray-500 block">
									{formatDate($stats.next_scheduled_run)}
								</span>
							{:else}
								No scheduled runs
							{/if}
						</p>
					</div>
				</div>

				{#if $stats.next_scheduled_run}
					<div class="pt-3 border-t">
						<Button
							variant="outline"
							size="sm"
							onclick={() => dispatch('viewSchedule')}
							class="w-full"
						>
							<Calendar class="h-4 w-4 mr-2" />
							View Schedule
						</Button>
					</div>
				{/if}
			</CardContent>
		</Card>
	</div>

	<!-- Quick Actions -->
	<Card>
		<CardHeader>
			<CardTitle class="flex items-center space-x-2">
				<Settings class="h-5 w-5" />
				<span>Quick Actions</span>
			</CardTitle>
		</CardHeader>
		<CardContent>
			<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
				<Button
					variant="outline"
					onclick={triggerProjectWideIncremental}
					disabled={hasActiveRuns}
					class="h-20 flex-col"
				>
					<Play class="h-6 w-6 mb-2" />
					<span class="text-sm">Run All Domains</span>
				</Button>
				
				<Button
					variant="outline"
					onclick={() => dispatch('fillAllGaps')}
					disabled={$stats.total_gaps === 0 || hasActiveRuns}
					class="h-20 flex-col"
				>
					<Zap class="h-6 w-6 mb-2" />
					<span class="text-sm">Fill All Gaps</span>
					{#if $stats.total_gaps > 0}
						<Badge variant="secondary" class="mt-1 text-xs">
							{$stats.total_gaps} gaps
						</Badge>
					{/if}
				</Button>
				
				<Button
					variant="outline"
					onclick={() => dispatch('configureSchedule')}
					class="h-20 flex-col"
				>
					<Calendar class="h-6 w-6 mb-2" />
					<span class="text-sm">Configure Schedule</span>
				</Button>
			</div>
		</CardContent>
	</Card>

	<!-- Status Information -->
	{#if $stats.total_domains === 0}
		<Alert>
			<Globe class="h-4 w-4" />
			<AlertDescription>
				<strong>No domains configured.</strong>
				Add domains to your project to start using incremental scraping.
			</AlertDescription>
		</Alert>
	{:else if $stats.enabled_domains === 0}
		<Alert>
			<Settings class="h-4 w-4" />
			<AlertDescription>
				<strong>Incremental scraping is disabled for all domains.</strong>
				Enable it for specific domains to maintain continuous coverage.
			</AlertDescription>
		</Alert>
	{:else if $stats.avg_coverage_percentage < 50}
		<Alert variant="destructive">
			<AlertTriangle class="h-4 w-4" />
			<AlertDescription>
				<strong>Low coverage detected.</strong>
				Consider running gap-filling operations or adjusting your incremental scraping configuration.
			</AlertDescription>
		</Alert>
	{/if}
</div>