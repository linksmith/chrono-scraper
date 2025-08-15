<script lang="ts">
	import { cn } from '$lib/utils.js';
	import type { HTMLAttributes } from 'svelte/elements';

	type $$Props = HTMLAttributes<HTMLSpanElement>;

	let className: $$Props['class'] = undefined;
	export { className as class };
</script>

<span
	class={cn('font-normal text-foreground', className)}
	role="link"
	aria-disabled="true"
	aria-current="page"
	{...$$restProps}
>
	<slot />
</span>