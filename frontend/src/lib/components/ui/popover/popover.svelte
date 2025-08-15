<script lang="ts">
    export let open = false;
    
    import { setContext } from 'svelte';
    
    setContext('popover', {
        open,
        setOpen: (value: boolean) => { open = value; }
    });
</script>

<div>
    <slot />
</div>