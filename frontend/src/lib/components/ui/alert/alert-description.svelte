<script lang="ts">
    import { cn } from '$lib/utils';

    let className: string | undefined = undefined;
    export { className as class };
</script>

<div class={cn('text-sm [&_p]:leading-relaxed text-muted-foreground', className)} {...$$restProps}>
    <slot />
</div>


