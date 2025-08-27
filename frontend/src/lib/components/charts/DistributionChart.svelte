<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Chart,
		ArcElement,
		Tooltip,
		Legend,
		type ChartConfiguration,
		type ChartData
	} from 'chart.js';

	// Register Chart.js components
	Chart.register(ArcElement, Tooltip, Legend);

	export let data: ChartData<'doughnut', any[], any>;
	export let options: ChartConfiguration<'doughnut'>['options'] = {};
	export let height = 300;
	export let width: number | undefined = undefined;
	export let type: 'pie' | 'doughnut' = 'doughnut';

	let canvas: HTMLCanvasElement;
	let chart: Chart<'doughnut' | 'pie'> | null = null;

	// Color palette that matches the app theme
	const themeColors = [
		'hsl(var(--primary))',
		'hsl(var(--secondary))',
		'hsl(var(--accent))',
		'hsl(var(--muted))',
		'hsl(var(--destructive))',
		'hsl(var(--warning))',
		'hsl(221.2 83.2% 53.3%)', // blue
		'hsl(142.1 76.2% 36.3%)', // green
		'hsl(47.9 95.8% 53.1%)', // yellow
		'hsl(0 84.2% 60.2%)' // red
	];

	const defaultOptions: ChartConfiguration<'doughnut' | 'pie'>['options'] = {
		responsive: true,
		maintainAspectRatio: false,
		plugins: {
			legend: {
				position: 'right',
				labels: {
					color: 'hsl(var(--foreground))',
					usePointStyle: true,
					padding: 15,
					font: {
						size: 12
					}
				}
			},
			tooltip: {
				backgroundColor: 'hsl(var(--popover))',
				titleColor: 'hsl(var(--popover-foreground))',
				bodyColor: 'hsl(var(--popover-foreground))',
				borderColor: 'hsl(var(--border))',
				borderWidth: 1,
				callbacks: {
					label: (context) => {
						const label = context.label || '';
						const value = context.parsed;
						const total = context.dataset.data.reduce((sum: number, val: number) => sum + val, 0);
						const percentage = ((value / total) * 100).toFixed(1);
						return `${label}: ${value.toLocaleString()} (${percentage}%)`;
					}
				}
			}
		},
		cutout: type === 'doughnut' ? '60%' : 0
	};

	$: mergedOptions = {
		...defaultOptions,
		...options,
		plugins: {
			...defaultOptions.plugins,
			...options?.plugins
		}
	};

	// Enhance data with colors if not provided
	$: enhancedData = {
		...data,
		datasets: data.datasets.map((dataset, index) => ({
			...dataset,
			backgroundColor: dataset.backgroundColor || themeColors,
			borderColor: 'hsl(var(--background))',
			borderWidth: 2
		}))
	};

	onMount(() => {
		if (canvas) {
			chart = new Chart(canvas, {
				type: type as 'doughnut' | 'pie',
				data: enhancedData,
				options: mergedOptions
			});
		}
	});

	onDestroy(() => {
		if (chart) {
			chart.destroy();
		}
	});

	// Update chart when data changes
	$: if (chart && enhancedData) {
		chart.data = enhancedData;
		chart.update('none');
	}

	// Update chart when options change
	$: if (chart && mergedOptions) {
		chart.options = mergedOptions;
		chart.update('none');
	}
</script>

<div class="relative" style="height: {height}px; {width ? `width: ${width}px;` : ''}">
	<canvas bind:this={canvas}></canvas>
</div>