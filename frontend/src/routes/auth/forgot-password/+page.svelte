<script lang="ts">
	// Redirect to the main password reset page to keep tests working
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	
	onMount(() => {
		goto('/auth/password-reset', { replaceState: true });
	});
</script>

<!-- This page redirects to /auth/password-reset -->