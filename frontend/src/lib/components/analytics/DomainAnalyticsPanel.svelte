<script lang="ts">
	import { onMount } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Progress } from '$lib/components/ui/progress';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
	import { PerformanceBarChart, GaugeChart, HeatmapChart, TimeSeriesChart } from '$lib/components/charts';
	import {
		Globe,
		TrendingUp,
		TrendingDown,
		AlertTriangle,
		CheckCircle,
		Clock,
		Target,
		Activity,
		BarChart3,
		Compare,
		Settings,
		Download,
		RefreshCw,
		Filter,
		Zap,
		Users,
		Database
	} from 'lucide-svelte';
	import {
		projectAnalytics,
		domainPerformanceChartData,
		type DomainAnalytics,
		formatAnalyticsNumber,
		formatPercentage,
		formatDuration
	} from '$lib/stores/analytics';

	export let projectId: number;

	// Local state
	const selectedDomains = writable<number[]>([]);
	const sortBy = writable<'success_rate' | 'total_pages' | 'avg_processing_time' | 'performance_score'>('performance_score');
	const sortOrder = writable<'asc' | 'desc'>('desc');
	const comparisonMode = writable(false);

	// Get domain data from analytics store
	$: domainData = $projectAnalytics?.domainPerformance || [];

	// Sort domains
	$: sortedDomains = [...domainData].sort((a, b) => {
		const aVal = getDomainValue(a, $sortBy);
		const bVal = getDomainValue(b, $sortBy);
		return $sortOrder === 'asc' ? aVal - bVal : bVal - aVal;
	});

	// Comparison data for selected domains
	$: comparisonData = $selectedDomains.length > 0 
		? domainData.filter(domain => $selectedDomains.includes(domain.domainId))
		: [];

	function getDomainValue(domain: DomainAnalytics, sortKey: string): number {
		switch (sortKey) {
			case 'success_rate': return domain.successRate;
			case 'total_pages': return domain.totalPages;
			case 'avg_processing_time': return domain.avgProcessingTime;
			case 'performance_score': return domain.performanceScore;
			default: return 0;
		}
	}

	function getDomainStatusColor(domain: DomainAnalytics): string {
		if (domain.successRate >= 0.9 && domain.performanceScore >= 8) {
			return 'hsl(var(--success))';
		} else if (domain.successRate >= 0.7 && domain.performanceScore >= 6) {
			return 'hsl(var(--warning))';
		} else {
			return 'hsl(var(--destructive))';
		}
	}

	function getDomainStatusBadge(domain: DomainAnalytics) {
		if (domain.successRate >= 0.9 && domain.performanceScore >= 8) {
			return { variant: 'default', text: 'Excellent', icon: CheckCircle };
		} else if (domain.successRate >= 0.7 && domain.performanceScore >= 6) {
			return { variant: 'secondary', text: 'Good', icon: TrendingUp };
		} else if (domain.successRate >= 0.5 && domain.performanceScore >= 4) {
			return { variant: 'outline', text: 'Fair', icon: Activity };
		} else {
			return { variant: 'destructive', text: 'Poor', icon: TrendingDown };
		}
	}

	function toggleDomainSelection(domainId: number) {
		selectedDomains.update(selected => {
			const index = selected.indexOf(domainId);
			if (index === -1) {
				return [...selected, domainId];
			} else {
				return selected.filter(id => id !== domainId);
			}
		});
	}

	function clearDomainSelection() {
		selectedDomains.set([]);
	}

	// Chart data transformations
	$: domainComparisonChartData = comparisonData.length > 0 ? {
		labels: comparisonData.map(d => d.domainName),
		datasets: [
			{
				label: 'Success Rate (%)',
				data: comparisonData.map(d => d.successRate * 100),
				backgroundColor: 'hsl(var(--primary))',
			},
			{
				label: 'Performance Score',
				data: comparisonData.map(d => d.performanceScore),
				backgroundColor: 'hsl(var(--secondary))',
			}
		]
	} : null;

	$: processingTimeComparisonData = comparisonData.length > 0 ? {
		labels: comparisonData.map(d => d.domainName),
		datasets: [
			{
				label: 'Avg Processing Time (s)',
				data: comparisonData.map(d => d.avgProcessingTime),
				backgroundColor: comparisonData.map(d => 
					d.avgProcessingTime < 2 ? 'hsl(var(--success))' :
					d.avgProcessingTime < 5 ? 'hsl(var(--warning))' : 
					'hsl(var(--destructive))'
				),
			}
		]
	} : null;

	// Domain performance heatmap data
	$: domainHeatmapData = domainData.map(domain => ({
		x: 'Success Rate',
		y: domain.domainName,
		v: domain.successRate * 100
	})).concat(domainData.map(domain => ({
		x: 'Perf Score',
		y: domain.domainName,
		v: domain.performanceScore
	}))).concat(domainData.map(domain => ({
		x: 'Proc Time',
		y: domain.domainName,
		v: Math.max(0, 10 - domain.avgProcessingTime) // Invert for better visualization
	})));

	// Mock historical data for selected domain
	$: selectedDomainHistory = $selectedDomains.length === 1 && domainData.length > 0 ? {
		labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
		datasets: [
			{
				label: 'Success Rate (%)',
				data: [85, 87, 90, domainData.find(d => d.domainId === $selectedDomains[0])?.successRate * 100 || 0],
				borderColor: 'hsl(var(--primary))',
				backgroundColor: 'hsl(var(--primary) / 0.1)',
				fill: true
			},
			{
				label: 'Processing Time (s)',
				data: [3.2, 2.8, 2.5, domainData.find(d => d.domainId === $selectedDomains[0])?.avgProcessingTime || 0],
				borderColor: 'hsl(var(--secondary))',
				backgroundColor: 'hsl(var(--secondary) / 0.1)',
				fill: true,
				yAxisID: 'y1'
			}
		]
	} : null;

	function exportDomainAnalytics() {
		console.log('Exporting domain analytics...');
	}
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold flex items-center gap-2">
				<Globe class="w-6 h-6" />
				Domain Performance Analytics
			</h2>
			<p class="text-muted-foreground">
				Compare domain performance and identify optimization opportunities
			</p>
		</div>
		
		<div class="flex gap-2">
			<Button 
				variant={$comparisonMode ? "default" : "outline"} 
				onclick={() => comparisonMode.update(m => !m)}
			>
				<Compare class="w-4 h-4 mr-2" />
				{$comparisonMode ? "Exit" : "Compare"} Mode
			</Button>
			<Button variant="outline" onclick={exportDomainAnalytics}>
				<Download class="w-4 h-4 mr-2" />
				Export
			</Button>
		</div>
	</div>

	<!-- Overview Statistics -->
	<div class="grid grid-cols-1 md:grid-cols-4 gap-4">
		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm text-muted-foreground">Total Domains</p>
						<p class="text-2xl font-bold">{domainData.length}</p>
					</div>
					<Database class="w-8 h-8 text-muted-foreground" />
				</div>
			</CardContent>
		</Card>

		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm text-muted-foreground">Avg Success Rate</p>
						<p class="text-2xl font-bold">
							{domainData.length > 0 ? ((domainData.reduce((sum, d) => sum + d.successRate, 0) / domainData.length) * 100).toFixed(1) : 0}%
						</p>
					</div>
					<Target class="w-8 h-8 text-muted-foreground" />
				</div>
			</CardContent>
		</Card>

		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm text-muted-foreground">Avg Proc Time</p>
						<p class="text-2xl font-bold">
							{domainData.length > 0 ? formatDuration(domainData.reduce((sum, d) => sum + d.avgProcessingTime, 0) / domainData.length) : '0s'}
						</p>
					</div>
					<Clock class="w-8 h-8 text-muted-foreground" />
				</div>
			</CardContent>
		</Card>

		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm text-muted-foreground">Top Performer</p>
						<p class="text-sm font-bold truncate">
							{sortedDomains[0]?.domainName || 'N/A'}
						</p>
						{#if sortedDomains[0]}
							<Badge variant="default" class="mt-1">
								{sortedDomains[0].performanceScore}/10
							</Badge>
						{/if}
					</div>
					<Zap class="w-8 h-8 text-muted-foreground" />
				</div>
			</CardContent>
		</Card>
	</div>

	<!-- Controls -->
	{#if $comparisonMode}
		<Card>
			<CardContent class="pt-4">
				<div class="flex items-center justify-between mb-4">
					<div>
						<h3 class="font-medium">Comparison Mode</h3>
						<p class="text-sm text-muted-foreground">
							Select up to 5 domains to compare ({$selectedDomains.length}/5)
						</p>
					</div>
					<Button variant="outline" size="sm" onclick={clearDomainSelection}>
						Clear Selection
					</Button>
				</div>

				<div class="flex flex-wrap gap-2">
					{#each sortedDomains as domain}
						<Button
							variant={$selectedDomains.includes(domain.domainId) ? "default" : "outline"}
							size="sm"
							disabled={!$selectedDomains.includes(domain.domainId) && $selectedDomains.length >= 5}
							onclick={() => toggleDomainSelection(domain.domainId)}
						>
							{domain.domainName}
						</Button>
					{/each}
				</div>
			</CardContent>
		</Card>
	{:else}
		<div class="flex items-center gap-4 p-4 border rounded-lg bg-muted/50">
			<Select bind:value={$sortBy}>
				<SelectTrigger class="w-48">
					<SelectValue placeholder="Sort by" />
				</SelectTrigger>
				<SelectContent>
					<SelectItem value="performance_score">Performance Score</SelectItem>
					<SelectItem value="success_rate">Success Rate</SelectItem>
					<SelectItem value="total_pages">Total Pages</SelectItem>
					<SelectItem value="avg_processing_time">Processing Time</SelectItem>
				</SelectContent>
			</Select>

			<Button
				variant="outline"
				onclick={() => sortOrder.update(order => order === 'asc' ? 'desc' : 'asc')}
			>
				{$sortOrder === 'asc' ? 'Ascending' : 'Descending'}
			</Button>
		</div>
	{/if}

	<Tabs value="overview" class="space-y-4">
		<TabsList class="grid w-full grid-cols-4">
			<TabsTrigger value="overview">Overview</TabsTrigger>
			<TabsTrigger value="comparison">Comparison</TabsTrigger>
			<TabsTrigger value="heatmap">Performance Map</TabsTrigger>
			<TabsTrigger value="insights">Insights</TabsTrigger>
		</TabsList>

		<!-- Overview Tab -->
		<TabsContent value="overview" class="space-y-6">
			<div class="grid grid-cols-1 xl:grid-cols-3 gap-6">
				<!-- Domain Performance List -->
				<div class="xl:col-span-2">
					<Card>
						<CardHeader>
							<CardTitle>Domain Performance Ranking</CardTitle>
						</CardHeader>
						<CardContent>
							<div class="space-y-3 max-h-96 overflow-y-auto">
								{#each sortedDomains as domain, index}
									<div 
										class="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-colors"
										class:bg-muted/30={$selectedDomains.includes(domain.domainId)}
									>
										<div class="flex items-center gap-3">
											<div class="text-2xl font-bold text-muted-foreground w-8">
												#{index + 1}
											</div>
											
											<div class="flex-1">
												<div class="flex items-center gap-2 mb-1">
													<Globe class="w-4 h-4 text-muted-foreground" />
													<span class="font-medium">{domain.domainName}</span>
													{@const status = getDomainStatusBadge(domain)}
													<Badge variant={status.variant}>
														<svelte:component this={status.icon} class="w-3 h-3 mr-1" />
														{status.text}
													</Badge>
												</div>
												
												<div class="grid grid-cols-3 gap-4 text-sm text-muted-foreground">
													<div>
														<span class="font-medium">Pages:</span> {formatAnalyticsNumber(domain.totalPages)}
													</div>
													<div>
														<span class="font-medium">Success:</span> {(domain.successRate * 100).toFixed(1)}%
													</div>
													<div>
														<span class="font-medium">Proc Time:</span> {formatDuration(domain.avgProcessingTime)}
													</div>
												</div>

												{#if domain.commonPatterns.length > 0}
													<div class="flex gap-1 mt-2">
														{#each domain.commonPatterns.slice(0, 3) as pattern}
															<Badge variant="outline" class="text-xs">
																{pattern}
															</Badge>
														{/each}
													</div>
												{/if}
											</div>
										</div>
										
										<div class="text-right">
											<GaugeChart 
												value={domain.performanceScore}
												max={10}
												height={80}
												width={80}
												title=""
												color={getDomainStatusColor(domain)}
											/>
										</div>
									</div>
								{/each}
							</div>
						</CardContent>
					</Card>
				</div>

				<!-- Performance Distribution -->
				<div class="space-y-4">
					{#if $domainPerformanceChartData}
						<Card>
							<CardHeader>
								<CardTitle>Success Rate Distribution</CardTitle>
							</CardHeader>
							<CardContent>
								<PerformanceBarChart 
									data={$domainPerformanceChartData} 
									height={250}
									orientation="vertical"
								/>
							</CardContent>
						</Card>
					{/if}

					<!-- Quick Stats -->
					<Card>
						<CardHeader>
							<CardTitle>Quick Stats</CardTitle>
						</CardHeader>
						<CardContent class="space-y-3">
							{@const excellentDomains = domainData.filter(d => d.successRate >= 0.9 && d.performanceScore >= 8).length}
							{@const poorDomains = domainData.filter(d => d.successRate < 0.5 || d.performanceScore < 4).length}
							
							<div class="flex items-center justify-between">
								<span class="text-sm">Excellent Performance</span>
								<Badge variant="default">{excellentDomains}</Badge>
							</div>
							
							<div class="flex items-center justify-between">
								<span class="text-sm">Needs Improvement</span>
								<Badge variant="destructive">{poorDomains}</Badge>
							</div>
							
							<div class="flex items-center justify-between">
								<span class="text-sm">Total Pages Processed</span>
								<Badge variant="outline">
									{formatAnalyticsNumber(domainData.reduce((sum, d) => sum + d.totalPages, 0))}
								</Badge>
							</div>
						</CardContent>
					</Card>
				</div>
			</div>
		</TabsContent>

		<!-- Comparison Tab -->
		<TabsContent value="comparison" class="space-y-6">
			{#if comparisonData.length > 0}
				<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
					{#if domainComparisonChartData}
						<Card>
							<CardHeader>
								<CardTitle>Performance Comparison</CardTitle>
							</CardHeader>
							<CardContent>
								<PerformanceBarChart 
									data={domainComparisonChartData} 
									height={300}
								/>
							</CardContent>
						</Card>
					{/if}

					{#if processingTimeComparisonData}
						<Card>
							<CardHeader>
								<CardTitle>Processing Time Comparison</CardTitle>
							</CardHeader>
							<CardContent>
								<PerformanceBarChart 
									data={processingTimeComparisonData} 
									height={300}
								/>
							</CardContent>
						</Card>
					{/if}
				</div>

				<!-- Historical Trend for Single Domain -->
				{#if $selectedDomains.length === 1 && selectedDomainHistory}
					<Card>
						<CardHeader>
							<CardTitle>
								Historical Trends - {comparisonData[0]?.domainName}
							</CardTitle>
						</CardHeader>
						<CardContent>
							<TimeSeriesChart 
								data={selectedDomainHistory} 
								height={300}
								options={{
									scales: {
										y1: {
											type: 'linear',
											display: true,
											position: 'right',
											grid: {
												drawOnChartArea: false,
											},
										}
									}
								}}
							/>
						</CardContent>
					</Card>
				{/if}

				<!-- Comparison Table -->
				<Card>
					<CardHeader>
						<CardTitle>Detailed Comparison</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="overflow-x-auto">
							<table class="w-full text-sm">
								<thead class="border-b">
									<tr class="text-left">
										<th class="p-2">Domain</th>
										<th class="p-2">Total Pages</th>
										<th class="p-2">Success Rate</th>
										<th class="p-2">Error Rate</th>
										<th class="p-2">Avg Proc Time</th>
										<th class="p-2">Performance Score</th>
										<th class="p-2">Status</th>
									</tr>
								</thead>
								<tbody>
									{#each comparisonData as domain}
										<tr class="border-b hover:bg-muted/50">
											<td class="p-2 font-medium">{domain.domainName}</td>
											<td class="p-2">{formatAnalyticsNumber(domain.totalPages)}</td>
											<td class="p-2">{(domain.successRate * 100).toFixed(1)}%</td>
											<td class="p-2">{(domain.errorRate * 100).toFixed(1)}%</td>
											<td class="p-2">{formatDuration(domain.avgProcessingTime)}</td>
											<td class="p-2">{domain.performanceScore.toFixed(1)}/10</td>
											<td class="p-2">
												{@const status = getDomainStatusBadge(domain)}
												<Badge variant={status.variant}>{status.text}</Badge>
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					</CardContent>
				</Card>
			{:else}
				<div class="text-center py-12 text-muted-foreground">
					<Compare class="w-12 h-12 mx-auto mb-4" />
					<p>No domains selected for comparison</p>
					<p class="text-sm">Enable comparison mode and select domains to compare</p>
				</div>
			{/if}
		</TabsContent>

		<!-- Performance Map Tab -->
		<TabsContent value="heatmap" class="space-y-6">
			<Card>
				<CardHeader>
					<CardTitle>Domain Performance Heatmap</CardTitle>
				</CardHeader>
				<CardContent>
					{#if domainHeatmapData.length > 0}
						<HeatmapChart 
							data={domainHeatmapData}
							height={Math.max(300, domainData.length * 50)}
							colorScale="success"
							title=""
						/>
					{:else}
						<div class="text-center py-12 text-muted-foreground">
							<BarChart3 class="w-12 h-12 mx-auto mb-4" />
							<p>No domain performance data available</p>
						</div>
					{/if}
				</CardContent>
			</Card>
		</TabsContent>

		<!-- Insights Tab -->
		<TabsContent value="insights" class="space-y-6">
			<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
				<!-- Performance Insights -->
				<Card>
					<CardHeader>
						<CardTitle>Performance Insights</CardTitle>
					</CardHeader>
					<CardContent class="space-y-4">
						{@const topPerformer = sortedDomains[0]}
						{@const worstPerformer = sortedDomains[sortedDomains.length - 1]}
						
						{#if topPerformer}
							<Alert>
								<CheckCircle class="w-4 h-4" />
								<AlertDescription>
									<strong>{topPerformer.domainName}</strong> is your top performer with 
									{(topPerformer.successRate * 100).toFixed(1)}% success rate and 
									{topPerformer.performanceScore}/10 performance score.
								</AlertDescription>
							</Alert>
						{/if}

						{#if worstPerformer && worstPerformer.performanceScore < 5}
							<Alert variant="destructive">
								<AlertTriangle class="w-4 h-4" />
								<AlertDescription>
									<strong>{worstPerformer.domainName}</strong> needs attention with 
									{(worstPerformer.successRate * 100).toFixed(1)}% success rate. 
									Consider reviewing scraping patterns.
								</AlertDescription>
							</Alert>
						{/if}

						{@const slowDomains = domainData.filter(d => d.avgProcessingTime > 5).length}
						{#if slowDomains > 0}
							<Alert>
								<Clock class="w-4 h-4" />
								<AlertDescription>
									{slowDomains} domain{slowDomains > 1 ? 's have' : ' has'} slow processing times (>5s). 
									Consider optimizing extraction patterns.
								</AlertDescription>
							</Alert>
						{/if}
					</CardContent>
				</Card>

				<!-- Recommendations -->
				<Card>
					<CardHeader>
						<CardTitle>Recommendations</CardTitle>
					</CardHeader>
					<CardContent class="space-y-4">
						{@const avgSuccessRate = domainData.reduce((sum, d) => sum + d.successRate, 0) / domainData.length}
						{@const lowPerformers = domainData.filter(d => d.successRate < avgSuccessRate * 0.8)}
						
						{#if lowPerformers.length > 0}
							<div class="p-3 border rounded-lg">
								<div class="flex items-center gap-2 mb-2">
									<Target class="w-4 h-4" />
									<span class="font-medium">Focus Areas</span>
								</div>
								<p class="text-sm text-muted-foreground mb-2">
									{lowPerformers.length} domain{lowPerformers.length > 1 ? 's' : ''} 
									performing below average:
								</p>
								<div class="flex flex-wrap gap-1">
									{#each lowPerformers.slice(0, 5) as domain}
										<Badge variant="outline" class="text-xs">
											{domain.domainName}
										</Badge>
									{/each}
									{#if lowPerformers.length > 5}
										<Badge variant="secondary" class="text-xs">
											+{lowPerformers.length - 5} more
										</Badge>
									{/if}
								</div>
							</div>
						{/if}

						<div class="space-y-2 text-sm">
							<div class="flex items-start gap-2">
								<div class="w-2 h-2 rounded-full bg-primary mt-2"></div>
								<div>
									<span class="font-medium">Pattern Optimization:</span>
									<p class="text-muted-foreground">Review filtering patterns for low-performing domains</p>
								</div>
							</div>
							
							<div class="flex items-start gap-2">
								<div class="w-2 h-2 rounded-full bg-primary mt-2"></div>
								<div>
									<span class="font-medium">Resource Allocation:</span>
									<p class="text-muted-foreground">Consider increasing resources for high-volume domains</p>
								</div>
							</div>
							
							<div class="flex items-start gap-2">
								<div class="w-2 h-2 rounded-full bg-primary mt-2"></div>
								<div>
									<span class="font-medium">Monitoring:</span>
									<p class="text-muted-foreground">Set up alerts for domains with declining performance</p>
								</div>
							</div>
						</div>
					</CardContent>
				</Card>
			</div>
		</TabsContent>
	</Tabs>
</div>