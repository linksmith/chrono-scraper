<script lang="ts">
    let className = '';
    export { className as class };
</script>

<div class="overflow-auto {className}">
    <slot />
</div>