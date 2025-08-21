<script lang="ts">
	import '../app.css';
	import { ModeWatcher } from 'mode-watcher';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { browser } from '$app/environment';
	import ErrorBoundary from '$lib/components/ErrorBoundary.svelte';
	import Toast from '$lib/components/Toast.svelte';
	import LoadingOverlay from '$lib/components/loading/LoadingOverlay.svelte';
	
	let mounted = false;
	
	onMount(() => {
		auth.init();
		mounted = true;
	});
</script>

{#if mounted}
	<ModeWatcher />
{/if}

<!-- Global Toast Notifications -->
<Toast />

<!-- Global Loading Overlay -->
<LoadingOverlay />

<div class="min-h-screen bg-background">	
	<main>
		<ErrorBoundary fallback="We're having trouble loading this page. Please try refreshing or contact support if the problem persists.">
			<slot />
		</ErrorBoundary>
	</main>
</div>