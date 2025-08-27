<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Chart,
		CategoryScale,
		LinearScale,
		BarElement,
		Title,
		Tooltip,
		Legend,
		type ChartConfiguration,
		type ChartData
	} from 'chart.js';

	// Register Chart.js components
	Chart.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

	export let data: ChartData<'bar', any[], any>;
	export let options: ChartConfiguration<'bar'>['options'] = {};
	export let height = 300;
	export let width: number | undefined = undefined;
	export let orientation: 'vertical' | 'horizontal' = 'vertical';

	let canvas: HTMLCanvasElement;
	let chart: Chart<'bar'> | null = null;

	const themeColors = [
		'hsl(var(--primary))',
		'hsl(var(--secondary))',
		'hsl(var(--accent))',
		'hsl(221.2 83.2% 53.3%)', // blue
		'hsl(142.1 76.2% 36.3%)', // green
		'hsl(47.9 95.8% 53.1%)', // yellow
		'hsl(0 84.2% 60.2%)', // red
		'hsl(262.1 83.3% 57.8%)', // violet
		'hsl(346.8 77.2% 49.8%)', // pink
		'hsl(24.6 95% 53.1%)' // orange
	];

	const defaultOptions: ChartConfiguration<'bar'>['options'] = {
		responsive: true,
		maintainAspectRatio: false,
		indexAxis: (orientation === 'horizontal' ? 'y' : 'x') as 'x' | 'y',
		interaction: {
			intersect: false,
			mode: 'index'
		},
		plugins: {
			legend: {
				position: 'top',
				labels: {
					color: 'hsl(var(--foreground))',
					usePointStyle: true,
					padding: 15
				}
			},
			tooltip: {
				backgroundColor: 'hsl(var(--popover))',
				titleColor: 'hsl(var(--popover-foreground))',
				bodyColor: 'hsl(var(--popover-foreground))',
				borderColor: 'hsl(var(--border))',
				borderWidth: 1
			}
		},
		scales: {
			x: {
				beginAtZero: orientation === 'vertical',
				grid: {
					color: 'hsl(var(--border))'
				},
				ticks: {
					color: 'hsl(var(--muted-foreground))'
				}
			},
			y: {
				beginAtZero: orientation === 'horizontal',
				grid: {
					color: 'hsl(var(--border))'
				},
				ticks: {
					color: 'hsl(var(--muted-foreground))'
				}
			}
		}
	};

	$: mergedOptions = {
		...defaultOptions,
		...options,
		indexAxis: (orientation === 'horizontal' ? 'y' : 'x') as 'x' | 'y',
		plugins: {
			...defaultOptions.plugins,
			...options?.plugins
		},
		scales: {
			...defaultOptions.scales,
			...options?.scales
		}
	};

	// Enhance data with colors if not provided
	$: enhancedData = {
		...data,
		datasets: data.datasets.map((dataset, index) => ({
			...dataset,
			backgroundColor: dataset.backgroundColor || themeColors[index % themeColors.length],
			borderColor: dataset.borderColor || themeColors[index % themeColors.length],
			borderWidth: dataset.borderWidth || 1,
			borderRadius: 4,
			borderSkipped: false
		}))
	};

	onMount(() => {
		if (canvas) {
			chart = new Chart(canvas, {
				type: 'bar',
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