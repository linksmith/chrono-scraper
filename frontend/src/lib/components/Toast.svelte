<script lang="ts">
	import { onMount } from 'svelte';
	import { fly } from 'svelte/transition';
	import { errorStore, type AppError } from '$lib/stores/error';
	import { Button } from '$lib/components/ui/button';
	import { AlertCircle, AlertTriangle, CheckCircle, Info, X } from 'lucide-svelte';

	let errors: AppError[] = [];

	// Subscribe to error store
	const unsubscribe = errorStore.subscribe(state => {
		errors = state.errors;
	});

	// Cleanup subscription
	onMount(() => {
		return () => {
			unsubscribe();
		};
	});

	function getIcon(type: AppError['type']) {
		switch (type) {
			case 'error':
				return AlertCircle;
			case 'warning':
				return AlertTriangle;
			case 'success':
				return CheckCircle;
			case 'info':
			default:
				return Info;
		}
	}

	function getColorClasses(type: AppError['type']) {
		switch (type) {
			case 'error':
				return 'bg-red-50 border-red-200 text-red-800 dark:bg-red-900/20 dark:border-red-800 dark:text-red-200';
			case 'warning':
				return 'bg-yellow-50 border-yellow-200 text-yellow-800 dark:bg-yellow-900/20 dark:border-yellow-800 dark:text-yellow-200';
			case 'success':
				return 'bg-green-50 border-green-200 text-green-800 dark:bg-green-900/20 dark:border-green-800 dark:text-green-200';
			case 'info':
			default:
				return 'bg-blue-50 border-blue-200 text-blue-800 dark:bg-blue-900/20 dark:border-blue-800 dark:text-blue-200';
		}
	}

	function dismiss(id: string) {
		errorStore.remove(id);
	}
</script>

<!-- Toast Container -->
{#if errors.length > 0}
	<div class="fixed top-4 left-4 right-4 sm:left-auto sm:right-4 z-50 space-y-2 max-w-sm sm:max-w-md w-full sm:w-auto">
		{#each errors as error (error.id)}
			<div
				class="border rounded-lg shadow-lg p-3 sm:p-4 {getColorClasses(error.type)}"
				in:fly={{ x: 300, duration: 300 }}
				out:fly={{ x: 300, duration: 200 }}
			>
				<div class="flex items-start gap-2 sm:gap-3">
					<div class="flex-shrink-0 mt-0.5">
						<svelte:component this={getIcon(error.type)} class="h-4 w-4 sm:h-5 sm:w-5" />
					</div>
					
					<div class="flex-1 min-w-0">
						<p class="text-xs sm:text-sm font-medium break-words leading-tight">
							{error.message}
						</p>
						
						{#if error.source}
							<p class="text-xs opacity-75 mt-1 leading-tight">
								Source: {error.source}
							</p>
						{/if}
						
						<p class="text-xs opacity-60 mt-1">
							{error.timestamp.toLocaleTimeString()}
						</p>
					</div>

					{#if error.dismissible}
						<Button
							variant="ghost"
							size="sm"
							class="h-8 w-8 sm:h-6 sm:w-6 p-0 hover:bg-white/20 touch-target-44 flex-shrink-0"
							onclick={() => dismiss(error.id)}
						>
							<X class="h-3 w-3" />
						</Button>
					{/if}
				</div>
			</div>
		{/each}
	</div>
{/if}

<style>
	/* Ensure toast appears above all other content */
	:global(.toast-container) {
		z-index: 1000;
	}
</style>