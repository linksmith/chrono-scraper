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

	export let value: number;
	export let max: number = 100;
	export let min: number = 0;
	export let title: string = '';
	export let subtitle: string = '';
	export let height = 300;
	export let width: number | undefined = undefined;
	export let color: string = 'hsl(var(--primary))';
	export let backgroundColor: string = 'hsl(var(--muted))';

	let canvas: HTMLCanvasElement;
	let chart: Chart<'doughnut'> | null = null;

	// Calculate percentage
	$: percentage = Math.min(Math.max(((value - min) / (max - min)) * 100, 0), 100);
	$: remaining = 100 - percentage;

	// Create gauge data
	$: gaugeData = {
		datasets: [
			{
				data: [percentage, remaining],
				backgroundColor: [color, backgroundColor],
				borderWidth: 0,
				circumference: 180,
				rotation: 270,
				cutout: '80%'
			}
		]
	};

	const gaugeOptions: ChartConfiguration<'doughnut'>['options'] = {
		responsive: true,
		maintainAspectRatio: false,
		plugins: {
			legend: {
				display: false
			},
			tooltip: {
				enabled: false
			}
		},
		events: []
	};

	onMount(() => {
		if (canvas) {
			chart = new Chart(canvas, {
				type: 'doughnut',
				data: gaugeData,
				options: gaugeOptions,
				plugins: [
					{
						id: 'gaugeText',
						afterDraw: (chart) => {
							const ctx = chart.ctx;
							const width = chart.width;
							const height = chart.height;

							ctx.restore();
							ctx.font = 'bold 24px sans-serif';
							ctx.textAlign = 'center';
							ctx.fillStyle = 'hsl(var(--foreground))';

							// Main value
							const text = `${value.toLocaleString()}`;
							ctx.fillText(text, width / 2, height / 2 + 10);

							// Title above value
							if (title) {
								ctx.font = 'normal 14px sans-serif';
								ctx.fillStyle = 'hsl(var(--muted-foreground))';
								ctx.fillText(title, width / 2, height / 2 - 20);
							}

							// Subtitle below value
							if (subtitle) {
								ctx.font = 'normal 12px sans-serif';
								ctx.fillStyle = 'hsl(var(--muted-foreground))';
								ctx.fillText(subtitle, width / 2, height / 2 + 35);
							}

							ctx.save();
						}
					}
				]
			});
		}
	});

	onDestroy(() => {
		if (chart) {
			chart.destroy();
		}
	});

	// Update chart when data changes
	$: if (chart && gaugeData) {
		chart.data = gaugeData;
		chart.update('none');
	}
</script>

<div class="relative" style="height: {height}px; {width ? `width: ${width}px;` : ''}">
	<canvas bind:this={canvas}></canvas>
</div>

<style>
	.relative {
		display: flex;
		align-items: center;
		justify-content: center;
	}
</style>