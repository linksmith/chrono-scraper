<script lang="ts">
	import '../app.css';
	import { ModeWatcher } from 'mode-watcher';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	
	onMount(() => {
		auth.init();
	});
</script>

<ModeWatcher />

<div class="min-h-screen bg-background flex flex-col">	
	<main class="flex-1">
		<slot />
	</main>
	
	<footer class="border-t mt-auto">
		<div class="container mx-auto px-4 py-4 text-center text-sm text-muted-foreground">
			&copy; 2024 Chrono Scraper. All rights reserved.
		</div>
	</footer>
</div>