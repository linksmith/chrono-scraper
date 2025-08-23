<script lang="ts">
	export let rows: number = 3;
	export let height: string = 'h-4';
	export let width: string = 'w-full';
	export let rounded: string = 'rounded';
	export let spacing: string = 'space-y-3';
</script>

<div class="animate-pulse {spacing}">
	{#each Array(rows) as _, i}
		<div 
			class="bg-gray-200 dark:bg-gray-700 {height} {rounded}"
			class:w-3/4={i === rows - 1}
			class:w-full={i !== rows - 1}
		></div>
	{/each}
</div>