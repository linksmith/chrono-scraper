<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Chart,
		CategoryScale,
		LinearScale,
		PointElement,
		LineElement,
		Title,
		Tooltip,
		Legend,
		TimeScale,
		type ChartConfiguration,
		type ChartData
	} from 'chart.js';
	import 'chartjs-adapter-date-fns';

	// Register Chart.js components
	Chart.register(
		CategoryScale,
		LinearScale,
		TimeScale,
		PointElement,
		LineElement,
		Title,
		Tooltip,
		Legend
	);

	export let data: ChartData<'line', any[], any>;
	export let options: ChartConfiguration<'line'>['options'] = {};
	export let height = 400;
	export let width: number | undefined = undefined;

	let canvas: HTMLCanvasElement;
	let chart: Chart<'line'> | null = null;

	const defaultOptions: ChartConfiguration<'line'>['options'] = {
		responsive: true,
		maintainAspectRatio: false,
		interaction: {
			intersect: false,
			mode: 'index'
		},
		plugins: {
			legend: {
				position: 'top'
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
				type: 'time',
				time: {
					displayFormats: {
						day: 'MMM dd',
						week: 'MMM dd',
						month: 'MMM yyyy'
					}
				},
				grid: {
					color: 'hsl(var(--border))'
				},
				ticks: {
					color: 'hsl(var(--muted-foreground))'
				}
			},
			y: {
				beginAtZero: true,
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
		plugins: {
			...defaultOptions.plugins,
			...options?.plugins
		},
		scales: {
			...defaultOptions.scales,
			...options?.scales
		}
	};

	onMount(() => {
		if (canvas) {
			chart = new Chart(canvas, {
				type: 'line',
				data: data,
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
	$: if (chart && data) {
		chart.data = data;
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