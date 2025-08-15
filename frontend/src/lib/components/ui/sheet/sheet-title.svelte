<script lang="ts">
    let className = '';
    export { className as class };
</script>

<h3 class="text-lg font-semibold {className}">
    <slot />
</h3>