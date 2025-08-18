<script lang="ts">
	import '../app.css';
	import { ModeWatcher } from 'mode-watcher';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { browser } from '$app/environment';
	
	onMount(() => {
		auth.init();
	});
</script>

{#if browser}
	<ModeWatcher />
{/if}

<div class="min-h-screen bg-background">	
	<main>
		<slot />
	</main>
</div>