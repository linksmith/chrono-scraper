<script lang="ts">
	import { getContext } from 'svelte';
	import type { HTMLDivAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils.js';
	import { Check } from 'lucide-svelte';

	type $$Props = HTMLDivAttributes & {
		value: string;
		disabled?: boolean;
	};

	let className: $$Props['class'] = undefined;
	export { className as class };
	export let value: $$Props['value'];
	export let disabled: $$Props['disabled'] = false;

	const ctx = getContext<any>('select');
	const selectValue = ctx?.value;
	const setValue = ctx?.setValue;
	const setOpen = ctx?.setOpen;

	$: isSelected = $selectValue === value;

	function handleClick() {
		if (!disabled && setValue && setOpen) {
			setValue(value);
			setOpen(false);
		}
	}
</script>

<div
	class={cn(
		'relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none',
		'focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
		className
	)}
	data-disabled={disabled}
	on:click={handleClick}
	{...$$restProps}
>
	<span class="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
		{#if isSelected}
			<Check class="h-4 w-4" />
		{/if}
	</span>
	<slot />
</div>