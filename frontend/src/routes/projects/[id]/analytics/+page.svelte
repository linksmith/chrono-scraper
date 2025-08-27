<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Progress } from '$lib/components/ui/progress';
	import { Separator } from '$lib/components/ui/separator';
	import { 
		TimeSeriesChart, 
		DistributionChart, 
		PerformanceBarChart, 
		GaugeChart 
	} from '$lib/components/charts';
	import FilteringInsightsDashboard from '$lib/components/analytics/FilteringInsightsDashboard.svelte';
	import PatternEffectivenessPanel from '$lib/components/analytics/PatternEffectivenessPanel.svelte';
	import DomainAnalyticsPanel from '$lib/components/analytics/DomainAnalyticsPanel.svelte';
	import {
		BarChart3,
		TrendingUp,
		TrendingDown,
		RefreshCw,
		Download,
		Settings,
		Calendar,
		Filter,
		Globe,
		Target,
		Activity,
		AlertTriangle,
		CheckCircle,
		Clock,
		FileText,
		Users,
		Zap,
		Eye,
		Gauge
	} from 'lucide-svelte';
	import {
		analyticsService,
		analyticsState,
		projectAnalytics,
		TIME_RANGES,
		statusDistributionChartData,
		timeSeriesChartData,
		domainPerformanceChartData,
		formatAnalyticsNumber,
		formatPercentage,
		formatDuration,
		getStatusColor,
		type ExportOptions
	} from '$lib/stores/analytics';

	// Get project ID from URL
	$: projectId = parseInt($page.params.id);

	// Local state
	let activeTab = 'overview';
	let customDateStart = '';
	let customDateEnd = '';
	let autoRefresh = false;
	let refreshInterval = 60; // seconds

	// Reactive data from stores
	$: analytics = $projectAnalytics;
	$: state = $analyticsState;
	$: loading = state.loading;
	$: error = state.error;
	$: timeRange = state.timeRange;
	$: lastUpdated = state.lastUpdated;

	// KPI calculations
	$: kpis = analytics ? {
		totalPages: analytics.basicStats.total_pages,
		successRate: analytics.basicStats.success_rate,
		filterRate: analytics.basicStats.filter_rate,
		avgProcessingTime: analytics.domainPerformance.length > 0 
			? analytics.domainPerformance.reduce((sum, d) => sum + d.avgProcessingTime, 0) / analytics.domainPerformance.length 
			: 0,
		manualInterventions: analytics.basicStats.manually_overridden,
		filteringEffectiveness: analytics.insights.filteringEffectiveness
	} : null;

	onMount(() => {
		loadAnalytics();
		
		// Handle tab navigation from URL hash
		const hash = window.location.hash.substring(1);
		if (['overview', 'filtering', 'patterns', 'domains'].includes(hash)) {
			activeTab = hash;
		}
	});

	onDestroy(() => {
		analyticsService.stopAutoRefresh();
	});

	async function loadAnalytics() {
		await analyticsService.loadProjectAnalytics(projectId, timeRange);
	}

	function handleTimeRangeChange(newRange: string) {
		const selectedRange = TIME_RANGES.find(r => r.value === newRange);
		if (selectedRange) {
			analyticsState.update(state => ({ ...state, timeRange: selectedRange }));
			loadAnalytics();
		}
	}

	function toggleAutoRefresh() {
		autoRefresh = !autoRefresh;
		if (autoRefresh) {
			analyticsService.startAutoRefresh(projectId);
		} else {
			analyticsService.stopAutoRefresh();
		}
		
		analyticsState.update(state => ({ 
			...state, 
			autoRefresh, 
			refreshInterval 
		}));
	}

	async function exportAnalytics() {
		if (!analytics) return;

		const options: ExportOptions = {
			format: 'json',
			sections: ['overview', 'filtering', 'domains', 'patterns'],
			timeRange: timeRange,
			includeCharts: true
		};

		try {
			await analyticsService.exportAnalytics(projectId, options);
		} catch (error) {
			console.error('Export failed:', error);
		}
	}

	// Update URL hash when tab changes
	$: if (typeof window !== 'undefined') {
		window.history.replaceState(null, '', `#${activeTab}`);
	}

	// Chart configurations
	const overviewTimeSeriesOptions = {
		plugins: {
			title: {
				display: true,
				text: 'Daily Processing Trends'
			}
		},
		scales: {
			y: {
				beginAtZero: true,
				title: {
					display: true,
					text: 'Number of Pages'
				}
			}
		}
	};
</script>

<div class="container mx-auto px-4 py-6 space-y-6">
	<!-- Header Section -->
	<div class="flex items-center justify-between">
		<div>
			<div class="flex items-center gap-2 mb-2">
				<Button 
					variant="ghost" 
					size="sm" 
					onclick={() => goto(`/projects/${projectId}`)}
				>
					← Back to Project
				</Button>
				<Separator orientation="vertical" />
				<h1 class="text-3xl font-bold">Analytics Dashboard</h1>
			</div>
			<p class="text-muted-foreground">
				Comprehensive insights and performance analysis for your scraping project
			</p>
		</div>
		
		<div class="flex items-center gap-3">
			<!-- Time Range Selector -->
			<Select value={timeRange.value} onValueChange={handleTimeRangeChange}>
				<SelectTrigger class="w-40">
					<Calendar class="w-4 h-4 mr-2" />
					<SelectValue />
				</SelectTrigger>
				<SelectContent>
					{#each TIME_RANGES as range}
						<SelectItem value={range.value}>{range.label}</SelectItem>
					{/each}
				</SelectContent>
			</Select>

			<!-- Auto Refresh Toggle -->
			<Button 
				variant={autoRefresh ? "default" : "outline"} 
				size="sm"
				onclick={toggleAutoRefresh}
			>
				<RefreshCw class="w-4 h-4 mr-2 {autoRefresh ? 'animate-spin' : ''}" />
				Auto Refresh
			</Button>

			<!-- Manual Refresh -->
			<Button variant="outline" size="sm" onclick={loadAnalytics} disabled={loading}>
				<RefreshCw class="w-4 h-4 mr-2 {loading ? 'animate-spin' : ''}" />
				Refresh
			</Button>

			<!-- Export -->
			<Button variant="outline" size="sm" onclick={exportAnalytics} disabled={loading}>
				<Download class="w-4 h-4 mr-2" />
				Export
			</Button>
		</div>
	</div>

	<!-- Last Updated Indicator -->
	{#if lastUpdated}
		<div class="text-right text-sm text-muted-foreground">
			Last updated: {lastUpdated.toLocaleString()}
		</div>
	{/if}

	<!-- Error Alert -->
	{#if error}
		<Alert variant="destructive">
			<AlertTriangle class="w-4 h-4" />
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Loading State -->
	{#if loading && !analytics}
		<div class="flex items-center justify-center py-12">
			<RefreshCw class="w-8 h-8 animate-spin mr-3" />
			<span class="text-lg">Loading analytics data...</span>
		</div>
	{:else if analytics}
		<!-- Key Performance Indicators -->
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
			{#if kpis}
				<Card>
					<CardContent class="pt-6">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm text-muted-foreground">Total Pages</p>
								<p class="text-2xl font-bold">{formatAnalyticsNumber(kpis.totalPages)}</p>
							</div>
							<FileText class="w-8 h-8 text-muted-foreground" />
						</div>
					</CardContent>
				</Card>

				<Card>
					<CardContent class="pt-6">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm text-muted-foreground">Success Rate</p>
								<div class="flex items-center gap-2">
									<p class="text-2xl font-bold">{(kpis.successRate * 100).toFixed(1)}%</p>
									{#if kpis.successRate >= 0.9}
										<TrendingUp class="w-4 h-4 text-green-500" />
									{:else if kpis.successRate < 0.7}
										<TrendingDown class="w-4 h-4 text-red-500" />
									{/if}
								</div>
							</div>
							<CheckCircle class="w-8 h-8 text-muted-foreground" />
						</div>
						<Progress value={kpis.successRate * 100} max={100} class="mt-2" />
					</CardContent>
				</Card>

				<Card>
					<CardContent class="pt-6">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm text-muted-foreground">Filter Rate</p>
								<p class="text-2xl font-bold">{(kpis.filterRate * 100).toFixed(1)}%</p>
							</div>
							<Filter class="w-8 h-8 text-muted-foreground" />
						</div>
						<Progress value={kpis.filterRate * 100} max={100} class="mt-2" />
					</CardContent>
				</Card>

				<Card>
					<CardContent class="pt-6">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm text-muted-foreground">Avg Proc Time</p>
								<p class="text-2xl font-bold">{formatDuration(kpis.avgProcessingTime)}</p>
							</div>
							<Clock class="w-8 h-8 text-muted-foreground" />
						</div>
					</CardContent>
				</Card>

				<Card>
					<CardContent class="pt-6">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm text-muted-foreground">Manual Reviews</p>
								<p class="text-2xl font-bold">{formatAnalyticsNumber(kpis.manualInterventions)}</p>
							</div>
							<Eye class="w-8 h-8 text-muted-foreground" />
						</div>
					</CardContent>
				</Card>

				<Card>
					<CardContent class="pt-6">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm text-muted-foreground">Filter Quality</p>
								<p class="text-2xl font-bold">{kpis.filteringEffectiveness.toFixed(1)}%</p>
								{#if kpis.filteringEffectiveness >= 85}
									<Badge variant="default" class="mt-1">Excellent</Badge>
								{:else if kpis.filteringEffectiveness >= 70}
									<Badge variant="secondary" class="mt-1">Good</Badge>
								{:else}
									<Badge variant="destructive" class="mt-1">Needs Work</Badge>
								{/if}
							</div>
							<Gauge class="w-8 h-8 text-muted-foreground" />
						</div>
					</CardContent>
				</Card>
			{/if}
		</div>

		<!-- Main Analytics Tabs -->
		<Tabs bind:value={activeTab} class="space-y-6">
			<TabsList class="grid w-full grid-cols-4">
				<TabsTrigger value="overview" class="flex items-center gap-2">
					<BarChart3 class="w-4 h-4" />
					Overview
				</TabsTrigger>
				<TabsTrigger value="filtering" class="flex items-center gap-2">
					<Filter class="w-4 h-4" />
					Filtering Insights
				</TabsTrigger>
				<TabsTrigger value="patterns" class="flex items-center gap-2">
					<Target class="w-4 h-4" />
					Pattern Analysis
				</TabsTrigger>
				<TabsTrigger value="domains" class="flex items-center gap-2">
					<Globe class="w-4 h-4" />
					Domain Performance
				</TabsTrigger>
			</TabsList>

			<!-- Overview Tab -->
			<TabsContent value="overview" class="space-y-6">
				<div class="grid grid-cols-1 xl:grid-cols-3 gap-6">
					<!-- Time Series Chart -->
					<div class="xl:col-span-2">
						<Card>
							<CardHeader>
								<CardTitle>Processing Trends Over Time</CardTitle>
							</CardHeader>
							<CardContent>
								{#if $timeSeriesChartData}
									<TimeSeriesChart 
										data={$timeSeriesChartData} 
										options={overviewTimeSeriesOptions}
										height={400}
									/>
								{:else}
									<div class="flex items-center justify-center py-12 text-muted-foreground">
										<Activity class="w-8 h-8 mr-2" />
										No time series data available
									</div>
								{/if}
							</CardContent>
						</Card>
					</div>

					<!-- Status Distribution -->
					<div class="space-y-4">
						<Card>
							<CardHeader>
								<CardTitle>Status Distribution</CardTitle>
							</CardHeader>
							<CardContent>
								{#if $statusDistributionChartData}
									<DistributionChart 
										data={$statusDistributionChartData} 
										height={250}
										type="doughnut"
									/>
								{:else}
									<div class="flex items-center justify-center py-8 text-muted-foreground">
										<BarChart3 class="w-8 h-8 mr-2" />
										No status data
									</div>
								{/if}
							</CardContent>
						</Card>
					</div>
				</div>

				<!-- Domain Performance Overview -->
				<Card>
					<CardHeader>
						<CardTitle>Domain Performance Summary</CardTitle>
					</CardHeader>
					<CardContent>
						{#if $domainPerformanceChartData}
							<PerformanceBarChart 
								data={$domainPerformanceChartData} 
								height={300}
								orientation="horizontal"
							/>
						{:else}
							<div class="flex items-center justify-center py-12 text-muted-foreground">
								<Globe class="w-8 h-8 mr-2" />
								No domain performance data available
							</div>
						{/if}
					</CardContent>
				</Card>

				<!-- Quick Statistics Grid -->
				<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
					<Card>
						<CardHeader>
							<CardTitle class="text-lg">Processing Summary</CardTitle>
						</CardHeader>
						<CardContent class="space-y-3">
							<div class="flex justify-between text-sm">
								<span>Pages Last 24h:</span>
								<Badge variant="outline">{formatAnalyticsNumber(analytics.basicStats.pages_last_24h)}</Badge>
							</div>
							<div class="flex justify-between text-sm">
								<span>Pages Last Week:</span>
								<Badge variant="outline">{formatAnalyticsNumber(analytics.basicStats.pages_last_week)}</Badge>
							</div>
							<div class="flex justify-between text-sm">
								<span>Pages Last Month:</span>
								<Badge variant="outline">{formatAnalyticsNumber(analytics.basicStats.pages_last_month)}</Badge>
							</div>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle class="text-lg">Quality Metrics</CardTitle>
						</CardHeader>
						<CardContent class="space-y-3">
							<div class="flex justify-between text-sm">
								<span>Retry Rate:</span>
								<Badge variant={analytics.basicStats.retry_rate < 0.1 ? 'default' : 'destructive'}>
									{(analytics.basicStats.retry_rate * 100).toFixed(1)}%
								</Badge>
							</div>
							<div class="flex justify-between text-sm">
								<span>Manual Reviews:</span>
								<Badge variant="secondary">
									{formatAnalyticsNumber(analytics.basicStats.manual_review_pending)}
								</Badge>
							</div>
							<div class="flex justify-between text-sm">
								<span>Overrides:</span>
								<Badge variant="outline">
									{formatAnalyticsNumber(analytics.basicStats.manually_overridden)}
								</Badge>
							</div>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle class="text-lg">System Health</CardTitle>
						</CardHeader>
						<CardContent class="space-y-3">
							<div class="flex justify-between text-sm">
								<span>Filter Effectiveness:</span>
								<Badge variant={analytics.insights.filteringEffectiveness > 80 ? 'default' : 'secondary'}>
									{analytics.insights.filteringEffectiveness.toFixed(1)}%
								</Badge>
							</div>
							<div class="flex justify-between text-sm">
								<span>False Positive Rate:</span>
								<Badge variant={analytics.insights.falsePositiveRate < 0.1 ? 'default' : 'destructive'}>
									{(analytics.insights.falsePositiveRate * 100).toFixed(1)}%
								</Badge>
							</div>
							<div class="flex justify-between text-sm">
								<span>Pattern Count:</span>
								<Badge variant="outline">
									{analytics.insights.topFilterPatterns.length}
								</Badge>
							</div>
						</CardContent>
					</Card>
				</div>
			</TabsContent>

			<!-- Filtering Insights Tab -->
			<TabsContent value="filtering">
				<FilteringInsightsDashboard {projectId} />
			</TabsContent>

			<!-- Pattern Analysis Tab -->
			<TabsContent value="patterns">
				<PatternEffectivenessPanel {projectId} />
			</TabsContent>

			<!-- Domain Performance Tab -->
			<TabsContent value="domains">
				<DomainAnalyticsPanel {projectId} />
			</TabsContent>
		</Tabs>
	{:else}
		<!-- Empty State -->
		<div class="text-center py-12">
			<BarChart3 class="w-16 h-16 mx-auto mb-4 text-muted-foreground" />
			<h2 class="text-2xl font-bold mb-2">No Analytics Data Available</h2>
			<p class="text-muted-foreground mb-4">
				Start scraping pages to generate analytics and insights
			</p>
			<Button onclick={() => goto(`/projects/${projectId}`)}>
				Go to Project Dashboard
			</Button>
		</div>
	{/if}
</div>