<script lang="ts">
    export let open = false;
    
    import { setContext } from 'svelte';
    
    setContext('sheet', {
        open,
        setOpen: (value: boolean) => { open = value; }
    });
</script>

<div>
    <slot />
    
    {#if open}
        <!-- Backdrop -->
        <div 
            class="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm"
            role="button"
            tabindex="0"
            on:click={() => { open = false; }}
            on:keydown={(e) => e.key === 'Escape' && (open = false)}
        ></div>
    {/if}
</div>