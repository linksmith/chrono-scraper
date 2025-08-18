<script lang="ts">
	import { cn } from '$lib/utils';

	let className: string | undefined = undefined;
	export { className as class };
	export let value: number | null | undefined = undefined;
	export let max = 100;

	$: percentage = value != null ? (value / max) * 100 : 0;
</script>

<div
	class={cn(
		'relative h-4 w-full overflow-hidden rounded-full bg-secondary',
		className
	)}
	{...$$restProps}
>
	<div
		class="h-full w-full flex-1 bg-primary transition-all duration-300 ease-in-out"
		style="transform: translateX(-{100 - percentage}%)"
		role="progressbar"
		aria-valuenow={value}
		aria-valuemax={max}
	></div>
</div>