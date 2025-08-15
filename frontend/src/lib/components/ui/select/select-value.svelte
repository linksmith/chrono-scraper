<script lang="ts">
	import { getContext } from 'svelte';
	import type { HTMLSpanAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils.js';

	type $$Props = HTMLSpanAttributes & {
		placeholder?: string;
	};

	let className: $$Props['class'] = undefined;
	export { className as class };
	export let placeholder: $$Props['placeholder'] = '';

	const ctx = getContext<any>('select');
	const value = ctx?.value;

	$: displayValue = $value || placeholder;
</script>

<span
	class={cn(
		$value ? '' : 'text-muted-foreground',
		className
	)}
	{...$$restProps}
>
	{displayValue}
</span>