<script lang="ts">
	import { getContext } from 'svelte';
	import type { HTMLDivAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils.js';

	type $$Props = HTMLDivAttributes & {
		position?: 'item-aligned' | 'popper';
	};

	let className: $$Props['class'] = undefined;
	export { className as class };
	export let position: $$Props['position'] = 'item-aligned';

	const ctx = getContext<any>('select');
	const open = ctx?.open;
</script>

{#if $open}
	<div
		class={cn(
			'relative z-50 min-w-[8rem] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md',
			'data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
			position === 'popper' &&
				'data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2',
			className
		)}
		data-state={$open ? 'open' : 'closed'}
		{...$$restProps}
	>
		<div
			class={cn(
				'p-1',
				position === 'popper' &&
					'h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)]'
			)}
		>
			<slot />
		</div>
	</div>
{/if}