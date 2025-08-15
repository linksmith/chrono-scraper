<script lang="ts">
    export let onSelect: (() => void) | undefined = undefined;
    
    let className = '';
    export { className as class };
    
    function handleClick() {
        if (onSelect) {
            onSelect();
        }
    }
</script>

<div
    role="button"
    tabindex="0"
    on:click={handleClick}
    on:keydown={(e) => e.key === 'Enter' && handleClick()}
    class="px-2 py-1.5 text-sm rounded-sm hover:bg-accent hover:text-accent-foreground cursor-pointer {className}"
>
    <slot />
</div>