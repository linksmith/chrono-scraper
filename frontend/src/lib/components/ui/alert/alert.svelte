<script lang="ts">
    import { cn } from '$lib/utils';

    let className: string | undefined = undefined;
    export { className as class };

    export let variant: 'default' | 'destructive' | 'success' | 'warning' | 'info' = 'default';

    const variantClasses: Record<typeof variant, string> = {
        default: 'bg-background text-foreground',
        destructive: 'border-destructive/50 text-destructive dark:border-destructive [&>svg]:text-destructive',
        success: 'border-green-500/50 text-green-700 dark:border-green-500 [&>svg]:text-green-600',
        warning: 'border-yellow-500/50 text-yellow-700 dark:border-yellow-500 [&>svg]:text-yellow-600',
        info: 'border-blue-500/50 text-blue-700 dark:border-blue-500 [&>svg]:text-blue-600'
    };
</script>

<div role="alert" class={cn('relative w-full rounded-lg border p-4 [&>svg~*]:pl-7 [&>svg+div]:translate-y-[-3px] [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg]:text-foreground', variantClasses[variant], className)} {...$$restProps}>
    <slot />
    <slot name="title" />
    <slot name="description" />
    <slot name="actions" />
    <slot name="footer" />
    <slot name="icon" />
</div>






