<script lang="ts">
	import { cn } from '$lib/utils.js';
	import { ChevronRight } from 'lucide-svelte';
	import type { HTMLLiAttributes } from 'svelte/elements';

	type $$Props = HTMLLiAttributes;

	let className: $$Props['class'] = undefined;
	export { className as class };
</script>

<li
	class={cn('[&>svg]:size-3.5', className)}
	role="presentation"
	aria-hidden="true"
	{...$$restProps}
>
	<slot>
		<ChevronRight />
	</slot>
</li>