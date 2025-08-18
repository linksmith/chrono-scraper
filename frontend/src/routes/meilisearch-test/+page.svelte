<script lang="ts">
	import { onMount } from 'svelte';

	let testResults = {
		instantMeilisearchImport: false,
		instantMeilisearchFunction: false,
		error: null
	};

	onMount(async () => {
		try {
			// Test 1: Can we import instant-meilisearch?
			const { instantMeiliSearch } = await import('@meilisearch/instant-meilisearch');
			testResults.instantMeilisearchImport = true;

			// Test 2: Can we create a search client?
			const { searchClient } = instantMeiliSearch(
				'http://localhost:7700',
				'test-key',
				{
					placeholderSearch: true,
					primaryKey: 'id'
				}
			);
			
			if (searchClient) {
				testResults.instantMeilisearchFunction = true;
			}

		} catch (error) {
			testResults.error = error.message;
		}
	});

	async function testMeilisearchAPI() {
		try {
			const response = await fetch('/api/v1/meilisearch/search', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					q: 'test',
					limit: 5
				})
			});

			if (response.ok) {
				alert('✅ Meilisearch FastAPI endpoint is accessible!');
			} else {
				alert(`❌ Meilisearch FastAPI endpoint returned: ${response.status} ${response.statusText}`);
			}
		} catch (error) {
			alert(`❌ Error testing Meilisearch API: ${error.message}`);
		}
	}
</script>

<svelte:head>
	<title>Meilisearch Integration Test</title>
</svelte:head>

<div class="min-h-screen bg-background p-8">
	<div class="max-w-4xl mx-auto space-y-8">
		<div>
			<h1 class="text-3xl font-bold">Meilisearch Integration Test</h1>
			<p class="text-muted-foreground">Testing the integration components</p>
		</div>

		<!-- Frontend Tests -->
		<div class="space-y-4">
			<h2 class="text-2xl font-semibold">Frontend Integration Tests</h2>
			
			<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
				<div class="p-4 border rounded-lg {testResults.instantMeilisearchImport ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}">
					<h3 class="font-semibold">
						{testResults.instantMeilisearchImport ? '✅' : '❌'} instant-meilisearch Import
					</h3>
					<p class="text-sm text-muted-foreground">
						Can import @meilisearch/instant-meilisearch package
					</p>
				</div>

				<div class="p-4 border rounded-lg {testResults.instantMeilisearchFunction ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}">
					<h3 class="font-semibold">
						{testResults.instantMeilisearchFunction ? '✅' : '❌'} Search Client Creation
					</h3>
					<p class="text-sm text-muted-foreground">
						Can create instantMeiliSearch client
					</p>
				</div>
			</div>

			{#if testResults.error}
				<div class="p-4 bg-red-50 border border-red-200 rounded-lg">
					<h3 class="font-semibold text-red-800">Error</h3>
					<p class="text-sm text-red-600">{testResults.error}</p>
				</div>
			{/if}
		</div>

		<!-- Backend Tests -->
		<div class="space-y-4">
			<h2 class="text-2xl font-semibold">Backend Integration Tests</h2>
			
			<div class="p-4 border rounded-lg">
				<h3 class="font-semibold mb-2">Meilisearch FastAPI Endpoint</h3>
				<p class="text-sm text-muted-foreground mb-4">
					Test the /api/v1/meilisearch/search endpoint
				</p>
				<button 
					onclick={testMeilisearchAPI}
					class="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600"
				>
					Test Meilisearch API
				</button>
			</div>
		</div>

		<!-- Integration Summary -->
		<div class="space-y-4">
			<h2 class="text-2xl font-semibold">Integration Summary</h2>
			
			<div class="p-6 border rounded-lg bg-gray-50">
				<h3 class="font-semibold mb-4">✅ Successfully Integrated Components:</h3>
				<ul class="space-y-2 text-sm">
					<li>• <strong>@meilisearch/instant-meilisearch</strong> - Frontend search client</li>
					<li>• <strong>meilisearch-fastapi</strong> - Backend API routes</li>
					<li>• <strong>Search components</strong> - SearchBox, SearchResults, SearchFilters, SearchPagination</li>
					<li>• <strong>State management</strong> - Svelte stores for search state</li>
					<li>• <strong>Authentication integration</strong> - Protected search routes</li>
				</ul>

				<h3 class="font-semibold mt-6 mb-4">🎯 Ready for Production:</h3>
				<ul class="space-y-2 text-sm">
					<li>• Configure proper Meilisearch API keys</li>
					<li>• Index your scraped Wayback Machine content</li>
					<li>• Access advanced search at <code>/search</code> (requires login)</li>
					<li>• Customize search relevance for OSINT workflows</li>
				</ul>
			</div>
		</div>

		<!-- Links -->
		<div class="space-y-4">
			<h2 class="text-2xl font-semibold">Quick Links</h2>
			<div class="flex space-x-4">
				<a href="/search" class="px-4 py-2 bg-primary text-primary-foreground rounded-md">
					Go to Search (requires login)
				</a>
				<a href="/api/v1/docs" target="_blank" class="px-4 py-2 bg-secondary text-secondary-foreground rounded-md">
					View API Docs
				</a>
			</div>
		</div>
	</div>
</div>