<script lang="ts">
    import { getContext } from 'svelte';
    
    export let align = 'center';
    
    const popover = getContext('popover') as { open: boolean; setOpen: (value: boolean) => void };
    
    let className = '';
    export { className as class };
</script>

{#if popover.open}
    <div class="absolute z-50 min-w-[8rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md {className}">
        <slot />
    </div>
{/if}