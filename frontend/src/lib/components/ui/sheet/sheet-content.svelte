<script lang="ts">
    import { getContext } from 'svelte';
    
    export let side: 'top' | 'right' | 'bottom' | 'left' = 'right';
    
    const sheet = getContext('sheet') as { open: boolean; setOpen: (value: boolean) => void };
    
    let className = '';
    export { className as class };
    
    const sideClasses = {
        top: 'top-0 left-0 right-0 max-h-[50vh]',
        right: 'top-0 right-0 h-full max-w-sm',
        bottom: 'bottom-0 left-0 right-0 max-h-[50vh]',
        left: 'top-0 left-0 h-full max-w-sm'
    };
</script>

{#if sheet.open}
    <div class="fixed z-50 {sideClasses[side]} bg-background border-l border-border shadow-lg p-6 {className}">
        <slot />
    </div>
{/if}