<script lang="ts">
	import { onMount } from 'svelte';
	import { errorStore } from '$lib/stores/error';
	import { Button } from '$lib/components/ui/button';
	import { AlertTriangle, RefreshCw } from 'lucide-svelte';

	export let fallback: string = 'Something went wrong';
	export let showDetails: boolean = false;
	export let retryable: boolean = true;

	let error: Error | null = null;
	let errorInfo: any = null;

	// Catch errors in child components
	function handleError(event: ErrorEvent | PromiseRejectionEvent) {
		const errorMessage = event instanceof ErrorEvent 
			? event.message 
			: `Promise rejected: ${event.reason}`;
			
		error = new Error(errorMessage);
		errorInfo = {
			timestamp: new Date().toISOString(),
			userAgent: navigator.userAgent,
			url: window.location.href,
			stack: error.stack
		};

		// Log to error store
		errorStore.add({
			message: `Component Error: ${errorMessage}`,
			type: 'error',
			source: 'ErrorBoundary',
			details: errorInfo,
			dismissible: false,
			autoRemove: false
		});
	}

	function retry() {
		error = null;
		errorInfo = null;
		// Trigger a re-render by updating a reactive variable
		window.location.reload();
	}

	onMount(() => {
		// Add error listeners for this component's scope
		const errorHandler = (event: ErrorEvent) => handleError(event);
		const rejectionHandler = (event: PromiseRejectionEvent) => handleError(event);

		window.addEventListener('error', errorHandler);
		window.addEventListener('unhandledrejection', rejectionHandler);

		return () => {
			window.removeEventListener('error', errorHandler);
			window.removeEventListener('unhandledrejection', rejectionHandler);
		};
	});
</script>

{#if error}
	<div class="min-h-[400px] flex items-center justify-center p-8">
		<div class="text-center max-w-md mx-auto">
			<div class="mb-6">
				<AlertTriangle class="h-16 w-16 text-red-500 mx-auto mb-4" />
				<h2 class="text-2xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
					Oops! Something went wrong
				</h2>
				<p class="text-gray-600 dark:text-gray-400 mb-4">
					{fallback}
				</p>
			</div>

			{#if showDetails && errorInfo}
				<details class="text-left mb-6 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
					<summary class="cursor-pointer text-sm font-medium mb-2">
						Technical Details
					</summary>
					<div class="text-xs text-gray-600 dark:text-gray-400 font-mono">
						<p><strong>Error:</strong> {error.message}</p>
						<p><strong>Time:</strong> {errorInfo.timestamp}</p>
						<p><strong>URL:</strong> {errorInfo.url}</p>
						{#if error.stack}
							<p><strong>Stack:</strong></p>
							<pre class="mt-2 whitespace-pre-wrap">{error.stack}</pre>
						{/if}
					</div>
				</details>
			{/if}

			<div class="space-y-3">
				{#if retryable}
					<Button on:click={retry} class="w-full">
						<RefreshCw class="h-4 w-4 mr-2" />
						Try Again
					</Button>
				{/if}
				
				<Button 
					variant="outline" 
					on:click={() => window.location.href = '/dashboard'}
					class="w-full"
				>
					Go to Dashboard
				</Button>
			</div>
		</div>
	</div>
{:else}
	<slot />
{/if}