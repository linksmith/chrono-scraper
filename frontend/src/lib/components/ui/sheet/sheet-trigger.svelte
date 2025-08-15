<script lang="ts">
    import { getContext } from 'svelte';
    
    export let asChild = false;
    export let builders: any[] = [];
    
    const sheet = getContext('sheet') as { open: boolean; setOpen: (value: boolean) => void };
    
    function handleClick() {
        sheet.setOpen(true);
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