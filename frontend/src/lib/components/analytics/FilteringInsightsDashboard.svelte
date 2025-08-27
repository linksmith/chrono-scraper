<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Progress } from '$lib/components/ui/progress';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { DistributionChart, PerformanceBarChart, HeatmapChart } from '$lib/components/charts';
	import FilteringEffectivenessChart from './FilteringEffectivenessChart.svelte';
	import PatternEffectivenessHeatmap from './PatternEffectivenessHeatmap.svelte';
	import { 
		TrendingUp,
		TrendingDown,
		AlertTriangle,
		CheckCircle,
		Filter,
		Eye,
		Target,
		Settings,
		Download,
		RefreshCw,
		Info
	} from 'lucide-svelte';
	import { 
		projectAnalytics, 
		analyticsState,
		formatAnalyticsNumber,
		formatPercentage,
		getStatusColor,
		patternEffectivenessHeatmapData
	} from '$lib/stores/analytics';

	export let projectId: number;
	
	// Reactive computations for insights
	$: insights = $projectAnalytics?.insights;
	$: filterAnalysis = $projectAnalytics?.filterAnalysis;
	$: basicStats = $projectAnalytics?.basicStats;

	// Chart data transformations
	$: confidenceDistributionData = insights ? {
		labels: Object.keys(insights.confidenceDistribution),
		datasets: [{
			data: Object.values(insights.confidenceDistribution),
			label: 'Confidence Distribution'
		}]
	} : null;

	$: processingTimeData = insights ? {
		labels: Object.keys(insights.processingTimeByType),
		datasets: [{
			data: Object.values(insights.processingTimeByType),
			label: 'Avg Processing Time (seconds)'
		}]
	} : null;

	$: filterCategoryData = filterAnalysis ? {
		labels: Object.keys(filterAnalysis.filterCategories),
		datasets: [{
			data: Object.values(filterAnalysis.filterCategories),
			label: 'Filtered Pages by Category'
		}]
	} : null;

	// Key performance indicators
	$: kpis = insights ? {
		filteringEffectiveness: {
			value: insights.filteringEffectiveness,
			trend: insights.filteringEffectiveness > 80 ? 'up' : insights.filteringEffectiveness > 60 ? 'stable' : 'down',
			status: insights.filteringEffectiveness > 80 ? 'excellent' : insights.filteringEffectiveness > 60 ? 'good' : 'needs-improvement'
		},
		falsePositiveRate: {
			value: insights.falsePositiveRate * 100,
			trend: insights.falsePositiveRate < 0.1 ? 'up' : insights.falsePositiveRate < 0.2 ? 'stable' : 'down',
			status: insights.falsePositiveRate < 0.1 ? 'excellent' : insights.falsePositiveRate < 0.2 ? 'good' : 'needs-improvement'
		},
		manualOverrideRate: {
			value: insights.manualOverrideRate * 100,
			trend: insights.manualOverrideRate < 0.05 ? 'up' : insights.manualOverrideRate < 0.15 ? 'stable' : 'down',
			status: insights.manualOverrideRate < 0.05 ? 'excellent' : insights.manualOverrideRate < 0.15 ? 'good' : 'needs-improvement'
		}
	} : null;

	function getKpiColor(status: string): string {
		switch (status) {
			case 'excellent': return 'hsl(var(--success))';
			case 'good': return 'hsl(var(--warning))';
			case 'needs-improvement': return 'hsl(var(--destructive))';
			default: return 'hsl(var(--muted-foreground))';
		}
	}

	function getTrendIcon(trend: string) {
		switch (trend) {
			case 'up': return TrendingUp;
			case 'down': return TrendingDown;
			default: return Info;
		}
	}

	function exportInsights(): void {
		// Implementation for exporting insights
		console.log('Exporting filtering insights...');
	}
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold flex items-center gap-2">
				<Filter class="w-6 h-6" />
				Filtering Insights Dashboard
			</h2>
			<p class="text-muted-foreground">
				Comprehensive analysis of filtering effectiveness and patterns
			</p>
		</div>
		
		<div class="flex gap-2">
			<Button variant="outline" onclick={exportInsights}>
				<Download class="w-4 h-4 mr-2" />
				Export Insights
			</Button>
		</div>
	</div>

	{#if $analyticsState.loading}
		<div class="flex items-center justify-center py-12">
			<RefreshCw class="w-8 h-8 animate-spin mr-2" />
			<span>Loading filtering insights...</span>
		</div>
	{:else if $analyticsState.error}
		<Alert variant="destructive">
			<AlertTriangle class="w-4 h-4" />
			<AlertDescription>{$analyticsState.error}</AlertDescription>
		</Alert>
	{:else if insights && kpis}
		<!-- Key Performance Indicators -->
		<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
			<Card>
				<CardContent class="pt-6">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm text-muted-foreground">Filtering Effectiveness</p>
							<div class="flex items-center gap-2">
								<p class="text-2xl font-bold">
									{kpis.filteringEffectiveness.value.toFixed(1)}%
								</p>
								<svelte:component 
									this={getTrendIcon(kpis.filteringEffectiveness.trend)} 
									class="w-4 h-4" 
									style="color: {getKpiColor(kpis.filteringEffectiveness.status)}"
								/>
							</div>
						</div>
						<Target class="w-8 h-8 text-muted-foreground" />
					</div>
					<Progress value={kpis.filteringEffectiveness.value} max={100} class="mt-2" />
				</CardContent>
			</Card>

			<Card>
				<CardContent class="pt-6">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm text-muted-foreground">False Positive Rate</p>
							<div class="flex items-center gap-2">
								<p class="text-2xl font-bold">
									{kpis.falsePositiveRate.value.toFixed(1)}%
								</p>
								<svelte:component 
									this={getTrendIcon(kpis.falsePositiveRate.trend)} 
									class="w-4 h-4" 
									style="color: {getKpiColor(kpis.falsePositiveRate.status)}"
								/>
							</div>
						</div>
						<AlertTriangle class="w-8 h-8 text-muted-foreground" />
					</div>
					<Progress value={100 - kpis.falsePositiveRate.value} max={100} class="mt-2" />
				</CardContent>
			</Card>

			<Card>
				<CardContent class="pt-6">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm text-muted-foreground">Manual Override Rate</p>
							<div class="flex items-center gap-2">
								<p class="text-2xl font-bold">
									{kpis.manualOverrideRate.value.toFixed(1)}%
								</p>
								<svelte:component 
									this={getTrendIcon(kpis.manualOverrideRate.trend)} 
									class="w-4 h-4" 
									style="color: {getKpiColor(kpis.manualOverrideRate.status)}"
								/>
							</div>
						</div>
						<Eye class="w-8 h-8 text-muted-foreground" />
					</div>
					<Progress value={100 - kpis.manualOverrideRate.value} max={100} class="mt-2" />
				</CardContent>
			</Card>
		</div>

		<!-- Comprehensive Filtering Effectiveness Dashboard -->
		<FilteringEffectivenessChart {insights} height={400} />

		<!-- Analysis Tabs -->
		<Tabs value="overview" class="space-y-4">
			<TabsList class="grid w-full grid-cols-4">
				<TabsTrigger value="overview">Overview</TabsTrigger>
				<TabsTrigger value="patterns">Pattern Analysis</TabsTrigger>
				<TabsTrigger value="performance">Performance</TabsTrigger>
				<TabsTrigger value="quality">Quality Trends</TabsTrigger>
			</TabsList>

			<!-- Overview Tab -->
			<TabsContent value="overview" class="space-y-6">
				<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
					<!-- Filter Categories Distribution -->
					{#if filterCategoryData}
						<Card>
							<CardHeader>
								<CardTitle>Filter Categories</CardTitle>
							</CardHeader>
							<CardContent>
								<DistributionChart 
									data={filterCategoryData} 
									height={300}
									type="doughnut" 
								/>
							</CardContent>
						</Card>
					{/if}

					<!-- Confidence Distribution -->
					{#if confidenceDistributionData}
						<Card>
							<CardHeader>
								<CardTitle>Confidence Score Distribution</CardTitle>
							</CardHeader>
							<CardContent>
								<DistributionChart 
									data={confidenceDistributionData} 
									height={300}
									type="pie" 
								/>
							</CardContent>
						</Card>
					{/if}
				</div>

				<!-- Key Insights -->
				<Card>
					<CardHeader>
						<CardTitle>Key Filtering Insights</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="space-y-4">
							<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
								<div class="flex items-center justify-between p-3 border rounded-lg">
									<span class="text-sm">Total Pages Analyzed</span>
									<Badge variant="secondary">
										{formatAnalyticsNumber(insights.totalPagesAnalyzed)}
									</Badge>
								</div>

								<div class="flex items-center justify-between p-3 border rounded-lg">
									<span class="text-sm">Filtering Accuracy</span>
									<Badge variant={insights.filteringEffectiveness > 80 ? 'default' : 'secondary'}>
										{insights.filteringEffectiveness.toFixed(1)}%
									</Badge>
								</div>

								<div class="flex items-center justify-between p-3 border rounded-lg">
									<span class="text-sm">Top Patterns Count</span>
									<Badge variant="outline">
										{insights.topFilterPatterns.length}
									</Badge>
								</div>

								<div class="flex items-center justify-between p-3 border rounded-lg">
									<span class="text-sm">Manual Interventions</span>
									<Badge variant={insights.manualOverrideRate < 0.1 ? 'default' : 'destructive'}>
										{formatPercentage(insights.manualOverrideRate * insights.totalPagesAnalyzed, insights.totalPagesAnalyzed)}
									</Badge>
								</div>
							</div>
						</div>
					</CardContent>
				</Card>
			</TabsContent>

			<!-- Pattern Analysis Tab -->
			<TabsContent value="patterns" class="space-y-6">
				<!-- Advanced Pattern Effectiveness Heatmap -->
				<PatternEffectivenessHeatmap patterns={insights.topFilterPatterns} height={400} />

				<!-- Top Performing Patterns -->
				<Card>
					<CardHeader>
						<CardTitle>Top Performing Patterns</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="space-y-3">
							{#each insights.topFilterPatterns.slice(0, 10) as pattern}
								<div class="flex items-center justify-between p-3 border rounded-lg">
									<div class="flex-1">
										<div class="flex items-center gap-2">
											<Badge variant="outline" class="text-xs">
												{pattern.category}
											</Badge>
											<span class="font-mono text-sm truncate">
												{pattern.pattern}
											</span>
										</div>
										<div class="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
											<span>Matches: {formatAnalyticsNumber(pattern.totalMatches)}</span>
											<span>Confidence: {(pattern.avgConfidence * 100).toFixed(1)}%</span>
											<span>False Positives: {(pattern.falsePositiveRate * 100).toFixed(1)}%</span>
										</div>
									</div>
									<div class="text-right">
										<Badge 
											variant={pattern.effectivenessScore > 0.8 ? 'default' : pattern.effectivenessScore > 0.6 ? 'secondary' : 'destructive'}
										>
											{(pattern.effectivenessScore * 100).toFixed(1)}%
										</Badge>
									</div>
								</div>
							{/each}
						</div>
					</CardContent>
				</Card>
			</TabsContent>

			<!-- Performance Tab -->
			<TabsContent value="performance" class="space-y-6">
				<!-- Processing Time by Content Type -->
				{#if processingTimeData}
					<Card>
						<CardHeader>
							<CardTitle>Processing Time by Content Type</CardTitle>
						</CardHeader>
						<CardContent>
							<PerformanceBarChart 
								data={processingTimeData} 
								height={300}
								orientation="horizontal"
							/>
						</CardContent>
					</Card>
				{/if}

				<!-- Performance Summary -->
				<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
					<Card>
						<CardHeader>
							<CardTitle>Filter Performance Summary</CardTitle>
						</CardHeader>
						<CardContent>
							<div class="space-y-4">
								{#if filterAnalysis}
									<div class="flex items-center justify-between">
										<span class="text-sm">Total Filtered</span>
										<Badge variant="secondary">
											{formatAnalyticsNumber(filterAnalysis.totalFiltered)}
										</Badge>
									</div>

									<div class="flex items-center justify-between">
										<span class="text-sm">Average Confidence</span>
										<Badge variant={filterAnalysis.avgConfidence > 0.8 ? 'default' : 'secondary'}>
											{(filterAnalysis.avgConfidence * 100).toFixed(1)}%
										</Badge>
									</div>

									<div class="flex items-center justify-between">
										<span class="text-sm">Filter Rate</span>
										<Badge variant="outline">
											{basicStats ? formatPercentage(filterAnalysis.totalFiltered, basicStats.total_pages) : '0%'}
										</Badge>
									</div>
								{/if}
							</div>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>Recommendations</CardTitle>
						</CardHeader>
						<CardContent>
							<div class="space-y-3">
								{#if insights.filteringEffectiveness < 70}
									<Alert>
										<AlertTriangle class="w-4 h-4" />
										<AlertDescription class="text-sm">
											Filtering effectiveness is below optimal. Consider reviewing pattern configurations.
										</AlertDescription>
									</Alert>
								{/if}

								{#if insights.falsePositiveRate > 0.2}
									<Alert variant="destructive">
										<AlertTriangle class="w-4 h-4" />
										<AlertDescription class="text-sm">
											High false positive rate detected. Review pattern specificity.
										</AlertDescription>
									</Alert>
								{/if}

								{#if insights.manualOverrideRate > 0.15}
									<Alert>
										<Info class="w-4 h-4" />
										<AlertDescription class="text-sm">
											High manual override rate suggests patterns may be too restrictive.
										</AlertDescription>
									</Alert>
								{/if}

								{#if insights.filteringEffectiveness > 85 && insights.falsePositiveRate < 0.1}
									<Alert>
										<CheckCircle class="w-4 h-4" />
										<AlertDescription class="text-sm">
											Filtering system is performing optimally. Continue monitoring.
										</AlertDescription>
									</Alert>
								{/if}
							</div>
						</CardContent>
					</Card>
				</div>
			</TabsContent>

			<!-- Quality Trends Tab -->
			<TabsContent value="quality" class="space-y-6">
				<Card>
					<CardHeader>
						<CardTitle>Quality Score Trends</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="text-center py-8 text-muted-foreground">
							<Settings class="w-12 h-12 mx-auto mb-4" />
							<p>Quality trends visualization coming soon</p>
							<p class="text-sm">Historical quality score analysis and trending</p>
						</div>
					</CardContent>
				</Card>
			</TabsContent>
		</Tabs>
	{:else}
		<div class="text-center py-12 text-muted-foreground">
			<Filter class="w-12 h-12 mx-auto mb-4" />
			<p>No filtering insights data available</p>
			<p class="text-sm">Run some scraping operations to generate analytics</p>
		</div>
	{/if}
</div>