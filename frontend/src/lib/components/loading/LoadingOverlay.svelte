<script lang="ts">
	import { fade } from 'svelte/transition';
	import Spinner from './Spinner.svelte';
	import { loadingStore } from '$lib/stores/loading';

	export let show: boolean = false;
	export let message: string = 'Loading...';
	export let backdrop: boolean = true;

	let isLoading = false;

	// Subscribe to global loading state
	loadingStore.subscribe(store => {
		isLoading = show || store.global;
	});
</script>

{#if isLoading}
	<div 
		class="fixed inset-0 z-50 flex items-center justify-center"
		transition:fade={{ duration: 200 }}
	>
		<!-- Backdrop -->
		{#if backdrop}
			<div class="absolute inset-0 bg-black bg-opacity-50"></div>
		{/if}
		
		<!-- Loading content -->
		<div class="relative bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8 max-w-sm mx-4">
			<div class="text-center">
				<Spinner size="lg" />
				<p class="mt-4 text-gray-600 dark:text-gray-400 font-medium">
					{message}
				</p>
			</div>
		</div>
	</div>
{/if}