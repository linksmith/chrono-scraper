<script lang="ts">
    let className = '';
    export { className as class };
</script>

<div class="space-y-1 {className}">
    <slot />
</div>