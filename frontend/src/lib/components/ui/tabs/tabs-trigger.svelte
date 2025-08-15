<script lang="ts">
	import { getContext } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils.js';

	type $$Props = HTMLButtonAttributes & {
		value: string;
		disabled?: boolean;
	};

	let className: $$Props['class'] = undefined;
	export { className as class };
	export let value: $$Props['value'];
	export let disabled: $$Props['disabled'] = false;

	const ctx = getContext<any>('tabs');
	const tabValue = ctx?.value;
	const orientation = ctx?.orientation;
	const setValue = ctx?.setValue;

	$: isSelected = $tabValue === value;

	function handleClick() {
		if (!disabled && setValue) {
			setValue(value);
		}
	}
</script>

<button
	class={cn(
		'inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
		'data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm',
		'data-[orientation=vertical]:justify-start',
		className
	)}
	data-state={isSelected ? 'active' : 'inactive'}
	data-orientation={$orientation}
	{disabled}
	role="tab"
	aria-selected={isSelected}
	tabindex={isSelected ? 0 : -1}
	on:click={handleClick}
	{...$$restProps}
>
	<slot />
</button>