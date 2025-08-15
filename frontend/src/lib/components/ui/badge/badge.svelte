<script lang="ts">
	import { cn } from '$lib/utils';
	import { badgeVariants, type Variant } from '.';

	let className: string | undefined = undefined;
	export { className as class };
	export let variant: Variant = 'default';
</script>

<div class={cn(badgeVariants({ variant }), className)} {...$$restProps}>
	<slot />
</div>