<script lang="ts">
	import { cn } from '$lib/utils.js';
	import type { HTMLLiAttributes } from 'svelte/elements';

	type $$Props = HTMLLiAttributes;

	let className: $$Props['class'] = undefined;
	export { className as class };
</script>

<li
	class={cn('inline-flex items-center gap-1.5', className)}
	{...$$restProps}
>
	<slot />
</li>