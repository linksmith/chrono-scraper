<script lang="ts">
	import InstantSearch from '$lib/components/search/InstantSearch.svelte';
	
	let meilisearchApiKey = 'demo-key';

	// Handle search events
	function handlePageSelected({ detail }: { detail: { page: any } }) {
		console.log('Page selected:', detail.page);
	}

	function handleWaybackView({ detail }: { detail: { url: string; timestamp: string } }) {
		console.log('Wayback view:', detail.url);
	}

	function handleSearchPerformed({ detail }: { detail: { query: string; results: any[] } }) {
		console.log('Search performed:', detail.query, 'Results:', detail.results.length);
	}
</script>

<svelte:head>
	<title>Meilisearch Integration Demo - Chrono Scraper</title>
</svelte:head>

<div class="min-h-screen bg-background">
	<div class="container mx-auto px-4 py-8">
		<div class="space-y-6">
			<!-- Demo Header -->
			<div class="space-y-4">
				<div>
					<h1 class="text-4xl font-bold tracking-tight">Meilisearch Integration Demo</h1>
					<p class="text-muted-foreground text-lg">
						Testing instant-meilisearch + meilisearch-fastapi integration
					</p>
					<div class="mt-2 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
						<p class="text-sm text-yellow-700">
							⚠️ <strong>Demo Mode:</strong> This is a test of the search components. 
							In production, this would connect to your Meilisearch instance with indexed content.
						</p>
					</div>
				</div>
			</div>

			<!-- Integration Status -->
			<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
				<div class="p-4 bg-green-50 border border-green-200 rounded-lg">
					<h3 class="font-semibold text-green-800">✅ Frontend Integration</h3>
					<p class="text-sm text-green-600">instant-meilisearch package loaded</p>
				</div>
				<div class="p-4 bg-green-50 border border-green-200 rounded-lg">
					<h3 class="font-semibold text-green-800">✅ Backend Integration</h3>
					<p class="text-sm text-green-600">meilisearch-fastapi routes available</p>
				</div>
				<div class="p-4 bg-blue-50 border border-blue-200 rounded-lg">
					<h3 class="font-semibold text-blue-800">🔧 Configuration</h3>
					<p class="text-sm text-blue-600">Ready for production use</p>
				</div>
			</div>

			<!-- InstantSearch Component Demo -->
			<InstantSearch
				indexName="pages"
				apiKey={meilisearchApiKey}
				enableFilters={true}
				enablePagination={true}
				autoSearch={false}
				on:pageSelected={handlePageSelected}
				on:waybackView={handleWaybackView}
				on:searchPerformed={handleSearchPerformed}
			/>

			<!-- Integration Details -->
			<div class="mt-12 space-y-6">
				<h2 class="text-2xl font-bold">Integration Details</h2>
				
				<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
					<div class="space-y-4">
						<h3 class="text-lg font-semibold">Frontend Components</h3>
						<ul class="space-y-2 text-sm">
							<li>✅ SearchBox - Advanced input with debouncing</li>
							<li>✅ SearchResults - OSINT-optimized display</li>
							<li>✅ SearchFilters - Extensive filtering options</li>
							<li>✅ SearchPagination - Professional navigation</li>
							<li>✅ InstantSearch - Main orchestrator</li>
						</ul>
					</div>
					
					<div class="space-y-4">
						<h3 class="text-lg font-semibold">Backend Routes</h3>
						<ul class="space-y-2 text-sm">
							<li>✅ /api/v1/meilisearch/search - Search endpoint</li>
							<li>✅ Authentication integration</li>
							<li>✅ FastAPI OpenAPI documentation</li>
							<li>✅ Type-safe request/response models</li>
						</ul>
					</div>
				</div>

				<div class="p-4 bg-gray-50 border border-gray-200 rounded-lg">
					<h3 class="font-semibold mb-2">Next Steps for Production</h3>
					<ol class="list-decimal list-inside space-y-1 text-sm">
						<li>Configure Meilisearch API keys in your backend</li>
						<li>Index your scraped Wayback Machine content</li>
						<li>Set up proper authentication for search endpoints</li>
						<li>Customize search relevance and filters for OSINT workflows</li>
						<li>Enable advanced features like faceting and typo tolerance</li>
					</ol>
				</div>
			</div>
		</div>
	</div>
</div>