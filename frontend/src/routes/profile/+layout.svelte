<script lang="ts">
	import { onMount } from 'svelte';
	import { requireAuth } from '$lib/stores/auth';
	
	onMount(() => {
		requireAuth();
	});
</script>

<slot />