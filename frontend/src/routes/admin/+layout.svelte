<script lang="ts">
	import { onMount } from 'svelte';
	import { requireAdmin } from '$lib/stores/auth';
	
	onMount(() => {
		requireAdmin();
	});
</script>

<slot />