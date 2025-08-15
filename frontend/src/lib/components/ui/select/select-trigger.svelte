<script lang="ts">
	import { getContext } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils.js';
	import { ChevronDown } from 'lucide-svelte';

	type $$Props = HTMLButtonAttributes;

	let className: $$Props['class'] = undefined;
	export { className as class };

	const ctx = getContext<any>('select');
	const open = ctx?.open;
	const disabled = ctx?.disabled;
	const setOpen = ctx?.setOpen;

	function handleClick() {
		if (setOpen && !$disabled) {
			setOpen(!$open);
		}
	}
</script>

<button
	class={cn(
		'flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50',
		className
	)}
	disabled={$disabled}
	on:click={handleClick}
	{...$$restProps}
>
	<slot />
	<ChevronDown class="h-4 w-4 opacity-50" />
</button>