<script lang="ts">
	export let progress: number = 0;
	export let max: number = 100;
	export let label: string = '';
	export let showPercentage: boolean = true;
	export let color: 'primary' | 'success' | 'warning' | 'error' = 'primary';
	export let size: 'sm' | 'md' | 'lg' = 'md';

	$: percentage = Math.min(Math.max((progress / max) * 100, 0), 100);

	const colorClasses = {
		primary: 'bg-blue-600',
		success: 'bg-green-600',
		warning: 'bg-yellow-600',
		error: 'bg-red-600'
	};

	const heightClasses = {
		sm: 'h-2',
		md: 'h-3',
		lg: 'h-4'
	};
</script>

<div class="w-full">
	{#if label || showPercentage}
		<div class="flex justify-between text-sm text-gray-600 dark:text-gray-400 mb-2">
			{#if label}
				<span>{label}</span>
			{/if}
			{#if showPercentage}
				<span>{percentage.toFixed(0)}%</span>
			{/if}
		</div>
	{/if}
	
	<div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full {heightClasses[size]}">
		<div 
			class="transition-all duration-300 ease-in-out rounded-full {colorClasses[color]} {heightClasses[size]}"
			style="width: {percentage}%"
			role="progressbar"
			aria-valuenow={progress}
			aria-valuemin={0}
			aria-valuemax={max}
			aria-label={label || `Progress: ${percentage.toFixed(0)}%`}
		></div>
	</div>
</div>