<script lang="ts">
	import { getContext } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils.js';

	type $$Props = HTMLAttributes<HTMLDivElement> & {
		value: string;
	};

	let className: $$Props['class'] = undefined;
	export { className as class };
	export let value: $$Props['value'];

	const ctx = getContext<any>('tabs');
	const tabValue = ctx?.value;

	$: isSelected = $tabValue === value;
</script>

{#if isSelected}
	<div
		class={cn(
			'mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
			className
		)}
		data-state={isSelected ? 'active' : 'inactive'}
		role="tabpanel"
		tabindex="0"
		{...$$restProps}
	>
		<slot />
	</div>
{/if}