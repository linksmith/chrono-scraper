<script lang="ts">
    export let placeholder = '';
    export let value = '';
    export let onInput: ((event: Event) => void) | undefined = undefined;
    export let onKeydown: ((event: KeyboardEvent) => void) | undefined = undefined;
    
    let className = '';
    export { className as class };
</script>

<input
    type="text"
    {placeholder}
    bind:value
    on:input={onInput}
    on:keydown={onKeydown}
    class="w-full px-3 py-2 text-sm bg-transparent border-none outline-none placeholder:text-muted-foreground {className}"
/>