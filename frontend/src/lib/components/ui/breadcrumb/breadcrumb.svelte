<script lang="ts">
	import { cn } from '$lib/utils.js';
	import type { HTMLAttributes } from 'svelte/elements';

	type $$Props = HTMLAttributes<HTMLElement>;

	let className: $$Props['class'] = undefined;
	export { className as class };
</script>

<nav class={cn('', className)} aria-label="breadcrumb" {...$$restProps}>
	<slot />
</nav>