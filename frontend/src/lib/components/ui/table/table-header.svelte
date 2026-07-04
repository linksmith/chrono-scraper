<script lang="ts">
	import { cn } from '$lib/utils';

	let className: string | undefined = undefined;
	export { className as class };
</script>

<thead class={cn('[&_tr]:border-b', className)} {...$$restProps}>
	<slot />
</thead>
