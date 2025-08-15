<script lang="ts">
	import { cn } from '$lib/utils.js';
	import type { HTMLAnchorAttributes } from 'svelte/elements';

	type $$Props = HTMLAnchorAttributes;

	let className: $$Props['class'] = undefined;
	export { className as class };
</script>

<a
	class={cn(
		'transition-colors hover:text-foreground',
		className
	)}
	{...$$restProps}
>
	<slot />
</a>