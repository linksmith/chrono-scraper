<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Chart,
		CategoryScale,
		LinearScale,
		BarElement,
		LineElement,
		PointElement,
		Title,
		Tooltip,
		Legend,
		type ChartConfiguration
	} from 'chart.js';
	import type { FilteringInsights } from '$lib/stores/analytics';

	Chart.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, Title, Tooltip, Legend);

	export let insights: FilteringInsights;
	export let height = 400;
	export let width: number | undefined = undefined;

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	// Calculate effectiveness metrics
	$: effectivenessData = {
		labels: [
			'Overall Effectiveness',
			'False Positive Rate', 
			'Manual Override Rate',
			'Confidence Score'
		],
		datasets: [
			{
				type: 'bar' as const,
				label: 'Effectiveness Metrics (%)',
				data: [
					insights.filteringEffectiveness,
					insights.falsePositiveRate * 100,
					insights.manualOverrideRate * 100,
					(insights.topFilterPatterns.reduce((sum, p) => sum + p.avgConfidence, 0) / Math.max(insights.topFilterPatterns.length, 1)) * 100
				],
				backgroundColor: [
					'hsl(142 76% 36%)', // green for effectiveness
					'hsl(0 84% 60%)',   // red for false positives  
					'hsl(48 96% 53%)',  // yellow for manual overrides
					'hsl(221 83% 53%)'  // blue for confidence
				],
				borderColor: [
					'hsl(142 76% 30%)',
					'hsl(0 84% 50%)', 
					'hsl(48 96% 45%)',
					'hsl(221 83% 45%)'
				],
				borderWidth: 1,
				borderRadius: 4
			}
		]
	};

	const chartOptions: ChartConfiguration['options'] = {
		responsive: true,
		maintainAspectRatio: false,
		scales: {
			y: {
				beginAtZero: true,
				max: 100,
				ticks: {
					callback: function(value) {
						return value + '%';
					},
					color: 'hsl(var(--muted-foreground))'
				},
				grid: {
					color: 'hsl(var(--border))'
				}
			},
			x: {
				ticks: {
					color: 'hsl(var(--muted-foreground))'
				},
				grid: {
					display: false
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
					label: function(context) {
						const label = context.dataset.label || '';
						const value = context.parsed.y.toFixed(1);
						
						// Add contextual information
						switch (context.dataIndex) {
							case 0:
								return `${label}: ${value}% (Higher is better)`;
							case 1:
								return `${label}: ${value}% (Lower is better)`;
							case 2:
								return `${label}: ${value}% (Shows user intervention)`;
							case 3:
								return `${label}: ${value}% (Pattern reliability)`;
							default:
								return `${label}: ${value}%`;
						}
					}
				}
			},
			title: {
				display: true,
				text: 'Filtering System Effectiveness Metrics',
				color: 'hsl(var(--foreground))',
				font: {
					size: 16,
					weight: 'bold'
				}
			}
		}
	};

	onMount(() => {
		if (canvas) {
			chart = new Chart(canvas, {
				type: 'bar',
				data: effectivenessData,
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
	$: if (chart && effectivenessData) {
		chart.data = effectivenessData;
		chart.update('none');
	}
</script>

<div class="space-y-4">
	<!-- Metrics Summary Cards -->
	<div class="grid grid-cols-1 md:grid-cols-4 gap-4">
		<div class="bg-card p-4 rounded-lg border">
			<div class="flex items-center justify-between">
				<div>
					<p class="text-sm font-medium text-muted-foreground">Overall Effectiveness</p>
					<p class="text-2xl font-bold text-green-600">
						{insights.filteringEffectiveness.toFixed(1)}%
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
					<p class="text-sm font-medium text-muted-foreground">False Positive Rate</p>
					<p class="text-2xl font-bold text-red-600">
						{(insights.falsePositiveRate * 100).toFixed(1)}%
					</p>
				</div>
				<div class="h-8 w-8 rounded-full bg-red-100 flex items-center justify-center">
					<svg class="h-4 w-4 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"></path>
					</svg>
				</div>
			</div>
		</div>

		<div class="bg-card p-4 rounded-lg border">
			<div class="flex items-center justify-between">
				<div>
					<p class="text-sm font-medium text-muted-foreground">Manual Override Rate</p>
					<p class="text-2xl font-bold text-yellow-600">
						{(insights.manualOverrideRate * 100).toFixed(1)}%
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
					<p class="text-sm font-medium text-muted-foreground">Avg Pattern Confidence</p>
					<p class="text-2xl font-bold text-blue-600">
						{((insights.topFilterPatterns.reduce((sum, p) => sum + p.avgConfidence, 0) / Math.max(insights.topFilterPatterns.length, 1)) * 100).toFixed(1)}%
					</p>
				</div>
				<div class="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center">
					<svg class="h-4 w-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
					</svg>
				</div>
			</div>
		</div>
	</div>

	<!-- Chart Visualization -->
	<div class="bg-card p-6 rounded-lg border">
		<div class="relative" style="height: {height}px; {width ? `width: ${width}px;` : ''}">
			<canvas bind:this={canvas}></canvas>
		</div>
	</div>

	<!-- Processing Time Breakdown -->
	<div class="bg-card p-6 rounded-lg border">
		<h3 class="text-lg font-semibold mb-4">Processing Time by Filter Type</h3>
		<div class="space-y-3">
			{#each Object.entries(insights.processingTimeByType) as [type, time]}
				<div class="flex items-center justify-between">
					<span class="text-sm font-medium capitalize">{type.replace('_', ' ')}</span>
					<div class="flex items-center gap-2">
						<div class="w-24 h-2 bg-muted rounded-full overflow-hidden">
							<div 
								class="h-full bg-primary transition-all duration-300"
								style="width: {Math.min((time / Math.max(...Object.values(insights.processingTimeByType))) * 100, 100)}%"
							></div>
						</div>
						<span class="text-sm text-muted-foreground min-w-12">
							{time < 1 ? `${Math.round(time * 1000)}ms` : `${time.toFixed(1)}s`}
						</span>
					</div>
				</div>
			{/each}
		</div>
	</div>
</div>