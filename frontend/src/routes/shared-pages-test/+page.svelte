<script lang="ts">
	import { onMount } from 'svelte';
	import { pageManagementActions, pageManagementStore } from '$lib/stores/page-management';
	import { SharedPagesApiService } from '$lib/services/sharedPagesApi';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
	import { isAuthenticated, auth } from '$lib/stores/auth';
	import { goto } from '$app/navigation';

	let testResults: any[] = [];
	let loading = false;
	let error = '';

	onMount(async () => {
		await auth.init();
		if (!$isAuthenticated) {
			goto('/auth/login?redirect=/shared-pages-test');
			return;
		}
	});

	async function testSharedPagesApi() {
		loading = true;
		error = '';
		testResults = [];

		try {
			// Test 1: Enable shared pages API
			pageManagementActions.enableSharedPagesApi();
			testResults.push({
				test: 'Enable Shared Pages API',
				status: 'success',
				message: 'API enabled successfully'
			});

			// Test 2: Search pages
			const searchResponse = await SharedPagesApiService.searchPages({
				query: 'test',
				limit: 5
			});

			testResults.push({
				test: 'Search Pages',
				status: searchResponse.success ? 'success' : 'error',
				message: searchResponse.success 
					? `Found ${searchResponse.data?.total || 0} pages`
					: searchResponse.error?.message || 'Unknown error',
				data: searchResponse.data
			});

			// Test 3: Load sharing statistics
			try {
				const statsResponse = await SharedPagesApiService.getSharingStatistics();
				testResults.push({
					test: 'Sharing Statistics',
					status: statsResponse.success ? 'success' : 'error',
					message: statsResponse.success 
						? `Total shared pages: ${statsResponse.data?.total_shared_pages || 0}`
						: statsResponse.error?.message || 'Unknown error',
					data: statsResponse.data
				});
			} catch (err) {
				testResults.push({
					test: 'Sharing Statistics',
					status: 'error',
					message: 'Statistics endpoint may not be available yet'
				});
			}

			// Test 4: Load pages using page management store
			try {
				await pageManagementActions.loadPages({}, 1, 10);
				const storeState = $pageManagementStore;
				
				testResults.push({
					test: 'Page Management Store',
					status: storeState.error ? 'error' : 'success',
					message: storeState.error || `Loaded ${storeState.pages.length} pages`,
					data: { 
						pageCount: storeState.pages.length,
						useSharedApi: storeState.useSharedPagesApi
					}
				});
			} catch (err) {
				testResults.push({
					test: 'Page Management Store',
					status: 'error',
					message: err instanceof Error ? err.message : 'Unknown error'
				});
			}

		} catch (err) {
			error = err instanceof Error ? err.message : 'Unknown error occurred';
		} finally {
			loading = false;
		}
	}

	function getStatusColor(status: string) {
		switch (status) {
			case 'success': return 'bg-green-100 text-green-800';
			case 'error': return 'bg-red-100 text-red-800';
			default: return 'bg-gray-100 text-gray-800';
		}
	}
</script>

<svelte:head>
	<title>Shared Pages API Test - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
	<div class="space-y-6">
		<div>
			<h2 class="text-3xl font-bold tracking-tight">Shared Pages API Test</h2>
			<p class="text-muted-foreground">
				Test the new shared pages API integration and functionality.
			</p>
		</div>

		<Card>
			<CardHeader>
				<CardTitle>API Integration Test</CardTitle>
			</CardHeader>
			<CardContent class="space-y-4">
				<Button 
					onclick={testSharedPagesApi} 
					disabled={loading}
					class="w-full"
				>
					{#if loading}
						<div class="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full mr-2"></div>
						Running Tests...
					{:else}
						Run Shared Pages API Tests
					{/if}
				</Button>

				{#if error}
					<div class="p-4 bg-red-50 border border-red-200 rounded-md">
						<p class="text-red-800 font-medium">Error:</p>
						<p class="text-red-700">{error}</p>
					</div>
				{/if}

				{#if testResults.length > 0}
					<div class="space-y-3">
						<h3 class="font-semibold">Test Results:</h3>
						{#each testResults as result}
							<div class="p-3 border rounded-md">
								<div class="flex items-center justify-between mb-2">
									<span class="font-medium">{result.test}</span>
									<Badge class={getStatusColor(result.status)}>
										{result.status}
									</Badge>
								</div>
								<p class="text-sm text-muted-foreground">{result.message}</p>
								{#if result.data}
									<details class="mt-2">
										<summary class="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
											Show data
										</summary>
										<pre class="mt-2 p-2 bg-gray-50 rounded text-xs overflow-auto">
{JSON.stringify(result.data, null, 2)}
										</pre>
									</details>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			</CardContent>
		</Card>

		<Card>
			<CardHeader>
				<CardTitle>Current Store State</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="space-y-2 text-sm">
					<p><strong>Using Shared Pages API:</strong> {$pageManagementStore.useSharedPagesApi ? 'Yes' : 'No'}</p>
					<p><strong>Current Project ID:</strong> {$pageManagementStore.currentProjectId || 'None'}</p>
					<p><strong>Pages Loaded:</strong> {$pageManagementStore.pages.length}</p>
					<p><strong>Loading:</strong> {$pageManagementStore.loading ? 'Yes' : 'No'}</p>
					{#if $pageManagementStore.error}
						<p><strong>Error:</strong> <span class="text-red-600">{$pageManagementStore.error}</span></p>
					{/if}
				</div>
			</CardContent>
		</Card>
	</div>
</DashboardLayout>