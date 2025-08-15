<script lang="ts">
	import { getContext } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils.js';

	type $$Props = HTMLAttributes<HTMLDivElement>;

	let className: $$Props['class'] = undefined;
	export { className as class };

	const ctx = getContext<any>('tabs');
	const orientation = ctx?.orientation;
</script>

<div
	class={cn(
		'inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground',
		'data-[orientation=vertical]:flex-col data-[orientation=vertical]:h-auto data-[orientation=vertical]:w-10',
		className
	)}
	data-orientation={$orientation}
	role="tablist"
	{...$$restProps}
>
	<slot />
</div>