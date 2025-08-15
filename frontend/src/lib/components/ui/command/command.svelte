<script lang="ts">
    let className = '';
    export { className as class };
</script>

<div class="bg-background border border-border rounded-md shadow-md p-2 {className}">
    <slot />
</div>