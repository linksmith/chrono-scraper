<script lang="ts">
    let className = '';
    export { className as class };
</script>

<div class="max-h-60 overflow-auto {className}">
    <slot />
</div>