<script lang="ts">
    import { cn } from '$lib/utils';

    let className: string | undefined = undefined;
    export { className as class };
</script>

<h5 class={cn('mb-1 font-medium leading-none tracking-tight', className)} {...$$restProps}>
    <slot />
</h5>


