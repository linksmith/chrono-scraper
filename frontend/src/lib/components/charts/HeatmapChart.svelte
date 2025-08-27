<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

	export let data: Array<{ x: string; y: string; v: number }>;
	export let title: string = '';
	export let height = 400;
	export let width: number | undefined = undefined;
	export let colorScale: 'success' | 'warning' | 'error' | 'info' = 'info';

	let container: HTMLDivElement;
	let heatmapContainer: HTMLDivElement;

	// Get unique x and y values
	$: xLabels = [...new Set(data.map((d) => d.x))];
	$: yLabels = [...new Set(data.map((d) => d.y))];
	
	// Get min and max values for color scaling
	$: maxValue = Math.max(...data.map((d) => d.v));
	$: minValue = Math.min(...data.map((d) => d.v));

	// Color scales based on theme
	const colorScales = {
		success: {
			min: 'hsl(142.1 76.2% 36.3% / 0.1)',
			max: 'hsl(142.1 76.2% 36.3%)'
		},
		warning: {
			min: 'hsl(47.9 95.8% 53.1% / 0.1)',
			max: 'hsl(47.9 95.8% 53.1%)'
		},
		error: {
			min: 'hsl(0 84.2% 60.2% / 0.1)',
			max: 'hsl(0 84.2% 60.2%)'
		},
		info: {
			min: 'hsl(221.2 83.2% 53.3% / 0.1)',
			max: 'hsl(221.2 83.2% 53.3%)'
		}
	};

	// Get color intensity based on value
	function getColor(value: number): string {
		const intensity = maxValue > minValue ? (value - minValue) / (maxValue - minValue) : 0.5;
		const alpha = 0.1 + intensity * 0.9;
		
		const baseColors = {
			success: '142.1 76.2% 36.3%',
			warning: '47.9 95.8% 53.1%',
			error: '0 84.2% 60.2%',
			info: '221.2 83.2% 53.3%'
		};

		return `hsl(${baseColors[colorScale]} / ${alpha})`;
	}

	// Get data value for specific coordinates
	function getValue(x: string, y: string): number | null {
		const item = data.find((d) => d.x === x && d.y === y);
		return item ? item.v : null;
	}

	// Format value for display
	function formatValue(value: number): string {
		if (value >= 1000000) {
			return (value / 1000000).toFixed(1) + 'M';
		} else if (value >= 1000) {
			return (value / 1000).toFixed(1) + 'K';
		} else if (value < 1) {
			return (value * 100).toFixed(1) + '%';
		}
		return value.toLocaleString();
	}
</script>

<div bind:this={container} class="w-full">
	{#if title}
		<h3 class="text-lg font-semibold mb-4">{title}</h3>
	{/if}
	
	<div 
		bind:this={heatmapContainer}
		class="overflow-auto border rounded-lg"
		style="height: {height}px; {width ? `width: ${width}px;` : ''}"
	>
		<div class="grid grid-flow-col auto-cols-fr min-w-full">
			<!-- Header row -->
			<div class="sticky top-0 bg-muted/50 border-b font-medium text-sm p-2">
				<!-- Empty cell for row labels -->
			</div>
			{#each xLabels as xLabel}
				<div class="sticky top-0 bg-muted/50 border-b border-l font-medium text-sm p-2 text-center">
					{xLabel}
				</div>
			{/each}
			
			<!-- Data rows -->
			{#each yLabels as yLabel, yIndex}
				<!-- Row label -->
				<div class="sticky left-0 bg-muted/50 border-r font-medium text-sm p-2 flex items-center">
					{yLabel}
				</div>
				
				<!-- Data cells -->
				{#each xLabels as xLabel, xIndex}
					{@const value = getValue(xLabel, yLabel)}
					<div 
						class="border-l border-b p-2 text-center text-sm relative group cursor-pointer transition-colors hover:ring-2 hover:ring-primary/20"
						style="background-color: {value !== null ? getColor(value) : 'transparent'}"
					>
						{#if value !== null}
							<span class="font-medium">{formatValue(value)}</span>
							
							<!-- Tooltip -->
							<div class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-popover text-popover-foreground text-xs rounded shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 whitespace-nowrap">
								<strong>{xLabel} × {yLabel}</strong><br/>
								Value: {value.toLocaleString()}
							</div>
						{:else}
							<span class="text-muted-foreground">—</span>
						{/if}
					</div>
				{/each}
			{/each}
		</div>
	</div>
	
	<!-- Legend -->
	<div class="flex items-center justify-center gap-4 mt-4 text-sm">
		<div class="flex items-center gap-2">
			<div 
				class="w-4 h-4 rounded border"
				style="background-color: {colorScales[colorScale].min}"
			></div>
			<span class="text-muted-foreground">Low ({formatValue(minValue)})</span>
		</div>
		
		<div class="flex-1 h-2 rounded bg-gradient-to-r" 
			style="background: linear-gradient(to right, {colorScales[colorScale].min}, {colorScales[colorScale].max})"
		></div>
		
		<div class="flex items-center gap-2">
			<span class="text-muted-foreground">High ({formatValue(maxValue)})</span>
			<div 
				class="w-4 h-4 rounded border"
				style="background-color: {colorScales[colorScale].max}"
			></div>
		</div>
	</div>
</div>

<style>
	/* Custom scrollbar styling */
	.overflow-auto::-webkit-scrollbar {
		width: 8px;
		height: 8px;
	}
	
	.overflow-auto::-webkit-scrollbar-track {
		background: hsl(var(--muted));
		border-radius: 4px;
	}
	
	.overflow-auto::-webkit-scrollbar-thumb {
		background: hsl(var(--muted-foreground) / 0.3);
		border-radius: 4px;
	}
	
	.overflow-auto::-webkit-scrollbar-thumb:hover {
		background: hsl(var(--muted-foreground) / 0.5);
	}
</style>