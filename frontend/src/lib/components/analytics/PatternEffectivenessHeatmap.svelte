<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Chart,
		CategoryScale,
		LinearScale,
		Title,
		Tooltip,
		Legend,
		type ChartConfiguration,
		type ScriptableContext
	} from 'chart.js';
	import type { PatternAnalytics } from '$lib/stores/analytics';

	// Register Chart.js components
	Chart.register(CategoryScale, LinearScale, Title, Tooltip, Legend);

	export let patterns: PatternAnalytics[] = [];
	export let height = 400;
	export let width: number | undefined = undefined;

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	// Transform pattern data for heatmap visualization
	$: heatmapData = transformPatternsToHeatmap(patterns);

	function transformPatternsToHeatmap(patterns: PatternAnalytics[]) {
		if (!patterns.length) return { labels: [], datasets: [] };

		// Group patterns by category
		const categoryGroups = patterns.reduce((acc, pattern) => {
			if (!acc[pattern.category]) {
				acc[pattern.category] = [];
			}
			acc[pattern.category].push(pattern);
			return acc;
		}, {} as Record<string, PatternAnalytics[]>);

		// Create data points for heatmap
		const dataPoints: Array<{
			x: string;
			y: string;
			v: number;
			pattern: PatternAnalytics;
		}> = [];

		Object.entries(categoryGroups).forEach(([category, categoryPatterns]) => {
			categoryPatterns
				.sort((a, b) => b.effectivenessScore - a.effectivenessScore)
				.slice(0, 8) // Limit to top 8 patterns per category for readability
				.forEach((pattern, index) => {
					dataPoints.push({
						x: category.replace('_', ' '),
						y: pattern.pattern.length > 25 
							? pattern.pattern.substring(0, 22) + '...'
							: pattern.pattern,
						v: pattern.effectivenessScore,
						pattern
					});
				});
		});

		// Extract unique categories and patterns for axes
		const categories = [...new Set(dataPoints.map(d => d.x))];
		const patternNames = [...new Set(dataPoints.map(d => d.y))];

		return {
			labels: categories,
			datasets: [{
				label: 'Pattern Effectiveness Score',
				data: dataPoints,
				backgroundColor: (context: ScriptableContext<'scatter'>) => {
					const point = context.parsed;
					if (typeof point.y === 'number') {
						const effectiveness = dataPoints[context.dataIndex]?.v || 0;
						const alpha = Math.max(0.3, effectiveness);
						
						if (effectiveness >= 0.8) return `rgba(34, 197, 94, ${alpha})`; // green
						if (effectiveness >= 0.6) return `rgba(251, 191, 36, ${alpha})`; // yellow  
						if (effectiveness >= 0.4) return `rgba(249, 115, 22, ${alpha})`; // orange
						return `rgba(239, 68, 68, ${alpha})`; // red
					}
					return 'rgba(156, 163, 175, 0.3)';
				},
				borderColor: (context: ScriptableContext<'scatter'>) => {
					const effectiveness = dataPoints[context.dataIndex]?.v || 0;
					if (effectiveness >= 0.8) return 'rgb(34, 197, 94)';
					if (effectiveness >= 0.6) return 'rgb(251, 191, 36)';
					if (effectiveness >= 0.4) return 'rgb(249, 115, 22)';
					return 'rgb(239, 68, 68)';
				},
				borderWidth: 2,
				pointRadius: 12,
				pointHoverRadius: 15
			}]
		};
	}

	const chartOptions: ChartConfiguration<'scatter'>['options'] = {
		responsive: true,
		maintainAspectRatio: false,
		scales: {
			x: {
				type: 'category',
				title: {
					display: true,
					text: 'Filter Category',
					color: 'hsl(var(--foreground))',
					font: { size: 12, weight: 'bold' }
				},
				ticks: {
					color: 'hsl(var(--muted-foreground))',
					maxRotation: 45
				},
				grid: {
					color: 'hsl(var(--border))',
					lineWidth: 0.5
				}
			},
			y: {
				type: 'category',
				title: {
					display: true,
					text: 'Filter Pattern',
					color: 'hsl(var(--foreground))',
					font: { size: 12, weight: 'bold' }
				},
				ticks: {
					color: 'hsl(var(--muted-foreground))',
					font: { size: 10 }
				},
				grid: {
					color: 'hsl(var(--border))',
					lineWidth: 0.5
				}
			}
		},
		plugins: {
			legend: {
				display: false
			},
			tooltip: {
				backgroundColor: 'hsl(var(--popover))',
				titleColor: 'hsl(var(--popover-foreground))',
				bodyColor: 'hsl(var(--popover-foreground))',
				borderColor: 'hsl(var(--border))',
				borderWidth: 1,
				callbacks: {
					title: function(context) {
						const dataIndex = context[0].dataIndex;
						const pattern = heatmapData.datasets[0].data[dataIndex]?.pattern;
						return pattern ? `Pattern: ${pattern.pattern}` : 'Pattern Details';
					},
					label: function(context) {
						const dataIndex = context.dataIndex;
						const pattern = heatmapData.datasets[0].data[dataIndex]?.pattern;
						
						if (!pattern) return 'No pattern data';
						
						return [
							`Category: ${pattern.category.replace('_', ' ')}`,
							`Effectiveness: ${(pattern.effectivenessScore * 100).toFixed(1)}%`,
							`Confidence: ${(pattern.avgConfidence * 100).toFixed(1)}%`,
							`Total Matches: ${pattern.totalMatches.toLocaleString()}`,
							`False Positives: ${pattern.falsePositiveCount}`,
							`Recommendation: ${pattern.recommendation.toUpperCase()}`,
							pattern.suggestedImprovement ? `Suggestion: ${pattern.suggestedImprovement}` : ''
						].filter(Boolean);
					}
				}
			},
			title: {
				display: true,
				text: 'Filter Pattern Effectiveness Heatmap',
				color: 'hsl(var(--foreground))',
				font: {
					size: 16,
					weight: 'bold'
				}
			}
		},
		interaction: {
			intersect: false
		}
	};

	onMount(() => {
		if (canvas) {
			chart = new Chart(canvas, {
				type: 'scatter',
				data: heatmapData,
				options: chartOptions
			});
		}
	});

	onDestroy(() => {
		if (chart) {
			chart.destroy();
		}
	});

	// Update chart when data changes
	$: if (chart && heatmapData) {
		chart.data = heatmapData;
		chart.update('none');
	}

	// Group patterns by recommendation for summary
	$: patternSummary = patterns.reduce((acc, pattern) => {
		if (!acc[pattern.recommendation]) {
			acc[pattern.recommendation] = 0;
		}
		acc[pattern.recommendation]++;
		return acc;
	}, {} as Record<string, number>);
</script>

<div class="space-y-6">
	<!-- Pattern Summary Cards -->
	<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
		<div class="bg-card p-4 rounded-lg border">
			<div class="flex items-center justify-between">
				<div>
					<p class="text-sm font-medium text-muted-foreground">Keep Patterns</p>
					<p class="text-2xl font-bold text-green-600">
						{patternSummary.keep || 0}
					</p>
				</div>
				<div class="h-8 w-8 rounded-full bg-green-100 flex items-center justify-center">
					<svg class="h-4 w-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
					</svg>
				</div>
			</div>
		</div>

		<div class="bg-card p-4 rounded-lg border">
			<div class="flex items-center justify-between">
				<div>
					<p class="text-sm font-medium text-muted-foreground">Refine Patterns</p>
					<p class="text-2xl font-bold text-yellow-600">
						{patternSummary.refine || 0}
					</p>
				</div>
				<div class="h-8 w-8 rounded-full bg-yellow-100 flex items-center justify-center">
					<svg class="h-4 w-4 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
					</svg>
				</div>
			</div>
		</div>

		<div class="bg-card p-4 rounded-lg border">
			<div class="flex items-center justify-between">
				<div>
					<p class="text-sm font-medium text-muted-foreground">Remove Patterns</p>
					<p class="text-2xl font-bold text-red-600">
						{patternSummary.remove || 0}
					</p>
				</div>
				<div class="h-8 w-8 rounded-full bg-red-100 flex items-center justify-center">
					<svg class="h-4 w-4 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
					</svg>
				</div>
			</div>
		</div>
	</div>

	<!-- Heatmap Chart -->
	<div class="bg-card p-6 rounded-lg border">
		<div class="relative" style="height: {height}px; {width ? `width: ${width}px;` : ''}">
			{#if patterns.length === 0}
				<div class="flex items-center justify-center h-full text-muted-foreground">
					<div class="text-center">
						<svg class="mx-auto h-12 w-12 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
						</svg>
						<p class="text-sm">No pattern effectiveness data available</p>
						<p class="text-xs text-muted-foreground mt-1">Run scraping sessions to see pattern analysis</p>
					</div>
				</div>
			{:else}
				<canvas bind:this={canvas}></canvas>
			{/if}
		</div>
	</div>

	<!-- Legend and Color Scale -->
	<div class="bg-card p-4 rounded-lg border">
		<h4 class="font-medium mb-3">Effectiveness Scale</h4>
		<div class="flex items-center gap-4">
			<div class="flex items-center gap-2">
				<div class="w-4 h-4 rounded bg-green-500"></div>
				<span class="text-sm">Excellent (≥80%)</span>
			</div>
			<div class="flex items-center gap-2">
				<div class="w-4 h-4 rounded bg-yellow-500"></div>
				<span class="text-sm">Good (60-79%)</span>
			</div>
			<div class="flex items-center gap-2">
				<div class="w-4 h-4 rounded bg-orange-500"></div>
				<span class="text-sm">Fair (40-59%)</span>
			</div>
			<div class="flex items-center gap-2">
				<div class="w-4 h-4 rounded bg-red-500"></div>
				<span class="text-sm">Poor (&lt;40%)</span>
			</div>
		</div>
	</div>

	<!-- Top Patterns by Category -->
	{#if patterns.length > 0}
		<div class="bg-card p-6 rounded-lg border">
			<h4 class="font-medium mb-4">Top Performing Patterns by Category</h4>
			<div class="space-y-4">
				{#each Object.entries(patterns.reduce((acc, pattern) => {
					if (!acc[pattern.category]) {
						acc[pattern.category] = [];
					}
					acc[pattern.category].push(pattern);
					return acc;
				}, {})) as [category, categoryPatterns]}
					<div>
						<h5 class="text-sm font-medium capitalize text-muted-foreground mb-2">
							{category.replace('_', ' ')}
						</h5>
						<div class="grid gap-2">
							{#each categoryPatterns.sort((a, b) => b.effectivenessScore - a.effectivenessScore).slice(0, 3) as pattern}
								<div class="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
									<div class="flex-1 min-w-0">
										<p class="text-sm font-mono truncate" title={pattern.pattern}>
											{pattern.pattern}
										</p>
										{#if pattern.suggestedImprovement}
											<p class="text-xs text-muted-foreground mt-1">
												{pattern.suggestedImprovement}
											</p>
										{/if}
									</div>
									<div class="flex items-center gap-3 ml-3">
										<div class="text-right">
											<p class="text-sm font-medium">
												{(pattern.effectivenessScore * 100).toFixed(1)}%
											</p>
											<p class="text-xs text-muted-foreground">
												{pattern.totalMatches.toLocaleString()} matches
											</p>
										</div>
										<div class="px-2 py-1 rounded-full text-xs font-medium {
											pattern.recommendation === 'keep' ? 'bg-green-100 text-green-800' :
											pattern.recommendation === 'refine' ? 'bg-yellow-100 text-yellow-800' :
											'bg-red-100 text-red-800'
										}">
											{pattern.recommendation}
										</div>
									</div>
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>