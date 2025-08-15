<script lang="ts">
    import { getContext } from 'svelte';
    
    export let asChild = false;
    export let builders: any[] = [];
    
    const popover = getContext('popover') as { open: boolean; setOpen: (value: boolean) => void };
    
    function handleClick() {
        popover.setOpen(!popover.open);
    }
    
    let className = '';
    export { className as class };
</script>

{#if asChild}
    <slot {builders} />
{:else}
    <button on:click={handleClick} class={className}>
        <slot />
    </button>
{/if}