<script lang="ts">
    let className = '';
    export { className as class };
</script>

<div class="py-6 text-center text-sm text-muted-foreground {className}">
    <slot />
</div>