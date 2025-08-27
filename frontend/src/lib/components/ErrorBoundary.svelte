<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import { errorStore } from '$lib/stores/error';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { AlertTriangle, RefreshCw, ChevronDown, ChevronRight, Copy, Bug, ExternalLink, Home } from 'lucide-svelte';

	export let fallback: string = 'Something went wrong';
	export let showDetails: boolean = false;
	export let retryable: boolean = true;
	export let context: string = '';
	export let onRetry: (() => void) | null = null;

	const dispatch = createEventDispatcher<{
		retry: void;
		dismiss: void;
		reportError: { error: Error; context: string };
	}>();

	let error: Error | null = null;
	let errorInfo: any = null;
	let detailsExpanded = false;

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
			stack: error.stack,
			context: context || 'ErrorBoundary'
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
		if (onRetry) {
			onRetry();
		} else {
			dispatch('retry');
		}
		
		error = null;
		errorInfo = null;
	}

	function handleDismiss() {
		error = null;
		errorInfo = null;
		dispatch('dismiss');
	}

	function handleReportError() {
		if (error) {
			dispatch('reportError', { error, context });
		}
	}

	function copyErrorDetails() {
		if (!errorInfo) return;

		const details = `
Error Report
============
Message: ${error?.message || 'Unknown error'}
Context: ${errorInfo.context}
Timestamp: ${errorInfo.timestamp}
URL: ${errorInfo.url}
User Agent: ${errorInfo.userAgent}

Stack Trace:
${errorInfo.stack || 'No stack trace available'}
		`.trim();

		navigator.clipboard.writeText(details).then(() => {
			console.log('Error details copied to clipboard');
		}).catch((err) => {
			console.error('Failed to copy error details:', err);
		});
	}

	function getErrorSeverity(error: Error | null): 'low' | 'medium' | 'high' {
		if (!error) return 'low';

		const errorStr = error.message.toLowerCase();

		// High severity errors
		if (errorStr.includes('network') || 
			errorStr.includes('fetch') ||
			errorStr.includes('connection') ||
			errorStr.includes('timeout') ||
			errorStr.includes('unauthorized') ||
			errorStr.includes('forbidden')) {
			return 'high';
		}

		// Medium severity errors
		if (errorStr.includes('validation') ||
			errorStr.includes('parse') ||
			errorStr.includes('format') ||
			errorStr.includes('not found')) {
			return 'medium';
		}

		return 'low';
	}

	function getErrorSuggestion(error: Error | null): string {
		if (!error) return '';

		const errorStr = error.message.toLowerCase();

		if (errorStr.includes('network') || errorStr.includes('fetch')) {
			return 'Check your internet connection and try again.';
		}
		if (errorStr.includes('unauthorized') || errorStr.includes('403')) {
			return 'You may need to log in again or check your permissions.';
		}
		if (errorStr.includes('not found') || errorStr.includes('404')) {
			return 'The requested resource could not be found.';
		}
		if (errorStr.includes('timeout')) {
			return 'The request took too long to complete. Please try again.';
		}
		if (errorStr.includes('validation')) {
			return 'Please check your input and try again.';
		}
		if (errorStr.includes('server') || errorStr.includes('500')) {
			return 'A server error occurred. Please try again later.';
		}

		return 'An unexpected error occurred. Please try again or contact support.';
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

	$: severity = getErrorSeverity(error);
	$: suggestion = getErrorSuggestion(error);
	$: severityColor = severity === 'high' ? 'destructive' : severity === 'medium' ? 'warning' : 'secondary';
</script>

{#if error}
	<div class="min-h-[400px] flex items-center justify-center p-8">
		<div class="max-w-2xl mx-auto w-full">
			<Card class="border-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-200 bg-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-50">
				<CardHeader class="pb-3">
					<div class="flex items-start justify-between">
						<div class="flex items-start space-x-3">
							<div class="flex-shrink-0">
								<AlertTriangle class="h-8 w-8 text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-600 mt-0.5" />
							</div>
							<div>
								<CardTitle class="text-xl text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-900">
									Oops! Something went wrong
								</CardTitle>
								<p class="text-sm text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-700 mt-1">
									{error.message || fallback}
								</p>
								{#if suggestion}
									<p class="text-xs text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-600 mt-2">
										{suggestion}
									</p>
								{/if}
							</div>
						</div>
						<div class="flex items-center space-x-2">
							<Badge variant={severityColor} class="text-xs">
								{severity} severity
							</Badge>
							{#if context}
								<Badge variant="outline" class="text-xs">
									{context}
								</Badge>
							{/if}
						</div>
					</div>
				</CardHeader>

				<CardContent>
					<div class="space-y-4">
						<!-- Action Buttons -->
						<div class="flex flex-wrap items-center gap-2">
							{#if retryable}
								<Button
									variant="outline"
									size="sm"
									onclick={retry}
									class="h-8"
								>
									<RefreshCw class="h-3 w-3 mr-2" />
									Try Again
								</Button>
							{/if}

							<Button
								variant="ghost"
								size="sm"
								onclick={handleDismiss}
								class="h-8"
							>
								Dismiss
							</Button>

							{#if showDetails}
								<Button
									variant="ghost"
									size="sm"
									onclick={() => detailsExpanded = !detailsExpanded}
									class="h-8"
								>
									{#if detailsExpanded}
										<ChevronDown class="h-3 w-3 mr-2" />
									{:else}
										<ChevronRight class="h-3 w-3 mr-2" />
									{/if}
									Details
								</Button>
							{/if}

							<Button
								variant="ghost"
								size="sm"
								onclick={handleReportError}
								class="h-8"
							>
								<Bug class="h-3 w-3 mr-2" />
								Report Issue
							</Button>

							<Button
								variant="ghost"
								size="sm"
								onclick={() => window.location.href = '/dashboard'}
								class="h-8"
							>
								<Home class="h-3 w-3 mr-2" />
								Dashboard
							</Button>
						</div>

						<!-- Error Details (Expandable) -->
						{#if detailsExpanded && errorInfo}
							<div class="border-t border-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-200 pt-4">
								<div class="space-y-3">
									<div class="flex items-center justify-between">
										<h4 class="text-sm font-medium text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-900">
											Technical Details
										</h4>
										<Button
											variant="ghost"
											size="sm"
											onclick={copyErrorDetails}
											class="h-6 px-2 text-xs"
										>
											<Copy class="h-3 w-3 mr-1" />
											Copy
										</Button>
									</div>

									<div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
										<div>
											<span class="font-medium text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-800">Timestamp:</span>
											<span class="text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-600 ml-2">
												{new Date(errorInfo.timestamp).toLocaleString()}
											</span>
										</div>
										<div>
											<span class="font-medium text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-800">Context:</span>
											<span class="text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-600 ml-2">
												{errorInfo.context}
											</span>
										</div>
										<div class="md:col-span-2">
											<span class="font-medium text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-800">URL:</span>
											<span class="text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-600 ml-2 break-all">
												{errorInfo.url}
											</span>
										</div>
									</div>

									{#if errorInfo.stack}
										<div>
											<span class="font-medium text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-800 text-xs">Stack Trace:</span>
											<pre class="mt-1 p-2 bg-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-100 rounded text-xs text-{severityColor === 'destructive' ? 'red' : severityColor === 'warning' ? 'amber' : 'gray'}-700 overflow-x-auto whitespace-pre-wrap break-words max-h-40 overflow-y-auto">{errorInfo.stack}</pre>
										</div>
									{/if}
								</div>
							</div>
						{/if}
					</div>
				</CardContent>
			</Card>
		</div>
	</div>
{:else}
	<slot />
{/if}