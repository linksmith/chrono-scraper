<script lang="ts">
    export let checked: boolean = false;
    export let onCheckedChange: ((checked: boolean) => void) | undefined = undefined;
    export let id: string | undefined = undefined;
    
    let className = '';
    export { className as class };
    
    function handleChange(event: Event) {
        const target = event.target as HTMLInputElement;
        checked = target.checked;
        
        if (onCheckedChange) {
            onCheckedChange(checked);
        }
    }
</script>

<input
    type="checkbox"
    {id}
    bind:checked
    on:change={handleChange}
    class="h-4 w-4 text-primary border-gray-300 rounded focus:ring-primary {className}"
/>