<script lang="ts">
	import { onMount, createEventDispatcher } from 'svelte';
	import { getSearchClient, searchState, searchActions, searchFilters, buildMeilisearchFilter } from '$lib/stores/search';
	import SearchBox from './SearchBox.svelte';
	import SearchResults from './SearchResults.svelte';
	import SearchFilters from './SearchFilters.svelte';
	import SearchPagination from './SearchPagination.svelte';

	export let indexName = 'pages'; // Default Meilisearch index for pages
	export let apiKey = ''; // Meilisearch search API key
	export let enableFilters = true;
	export let enablePagination = true;
	export let autoSearch = true; // Auto-search on query change

	const dispatch = createEventDispatcher<{
		pageSelected: { page: any };
		waybackView: { url: string; timestamp: string };
		searchPerformed: { query: string; results: any[] };
	}>();

	let searchTimeout: number;

	// Reactive search function
	async function performSearch(query: string = $searchState.query, page: number = 1) {
		if (!apiKey) {
			console.warn('Meilisearch API key not provided');
			return;
		}

		searchActions.setLoading(true);
		searchActions.setError(null);

		try {
			// Build search parameters
			const searchParams: any = {
				q: query,
				offset: (page - 1) * $searchState.pagination.pageSize,
				limit: $searchState.pagination.pageSize,
				attributesToRetrieve: [
					'id', 'title', 'url', 'domain', 'scraped_at', 'content_preview',
					'word_count', 'content_type', 'language', 'author', 'wayback_url',
					'status_code', 'project_name'
				],
				attributesToHighlight: ['title', 'content_preview'],
				highlightPreTag: '<mark>',
				highlightPostTag: '</mark>',
				attributesToCrop: ['content_preview:200']
			};

			// Add filters if any are set
			const filterString = buildMeilisearchFilter($searchFilters);
			if (filterString) {
				searchParams.filter = filterString;
			}

			// Add facets for filtering
			searchParams.facets = [
				'domain',
				'content_type', 
				'language',
				'status_code',
				'project_name'
			];

			// Get the search client (may be null during SSR)
			const searchClient = getSearchClient();
			if (!searchClient) {
				searchActions.setError('Search client not available');
				return;
			}

			// Perform search using the instantMeiliSearch client
			const searchResults = await searchClient.search([{
				indexName,
				params: searchParams
			}]);

			const results = searchResults.results[0];
			
			if (results.hits) {
				searchActions.setResults(results.hits, results.nbHits || 0);
				searchActions.setFacets(results.facets || {});
				dispatch('searchPerformed', { 
					query, 
					results: results.hits 
				});
			}
		} catch (error) {
			console.error('Search error:', error);
			searchActions.setError('Failed to perform search. Please try again.');
		} finally {
			searchActions.setLoading(false);
		}
	}

	// Handle search box input
	function handleSearch({ detail }: { detail: { query: string } }) {
		const { query } = detail;
		
		if (autoSearch) {
			// Debounce search for performance
			clearTimeout(searchTimeout);
			searchTimeout = setTimeout(() => {
				performSearch(query, 1);
			}, 300);
		}
	}

	// Handle clear search
	function handleClearSearch() {
		clearTimeout(searchTimeout);
		searchActions.reset();
	}

	// Handle filters change
	function handleFiltersChanged() {
		// Re-run search with new filters
		performSearch($searchState.query, 1);
	}

	// Handle pagination
	function handlePageChanged({ detail }: { detail: { page: number } }) {
		performSearch($searchState.query, detail.page);
		// Scroll to top on page change
		window.scrollTo({ top: 0, behavior: 'smooth' });
	}

	function handlePageSizeChanged({ detail }: { detail: { pageSize: number } }) {
		searchState.update(state => ({
			...state,
			pagination: {
				...state.pagination,
				pageSize: detail.pageSize,
				page: 1
			}
		}));
		performSearch($searchState.query, 1);
	}

	// Handle result selection
	function handlePageSelected({ detail }: { detail: { page: any } }) {
		dispatch('pageSelected', detail);
	}

	// Handle Wayback Machine view
	function handleWaybackView({ detail }: { detail: { url: string; timestamp: string } }) {
		dispatch('waybackView', detail);
	}

	// Initialize search on mount if there's a query
	onMount(() => {
		if ($searchState.query && autoSearch) {
			performSearch();
		}
	});

	// Update search client with API key when it changes
	$: if (apiKey) {
		// Update the search client configuration
		// Note: instantMeiliSearch doesn't directly support runtime key updates
		// In a real implementation, you might need to recreate the client
		console.log('API key updated:', apiKey);
	}
</script>

<div class="space-y-6">
	<!-- Search Box -->
	<SearchBox 
		on:search={handleSearch}
		on:clear={handleClearSearch}
	/>

	<!-- Search Filters -->
	{#if enableFilters}
		<SearchFilters
			on:filtersChanged={handleFiltersChanged}
			on:clearFilters={handleFiltersChanged}
		/>
	{/if}

	<!-- Search Results -->
	<SearchResults
		on:select={handlePageSelected}
		on:viewWayback={handleWaybackView}
	/>

	<!-- Pagination -->
	{#if enablePagination && $searchState.results.length > 0}
		<SearchPagination
			on:pageChanged={handlePageChanged}
			on:pageSizeChanged={handlePageSizeChanged}
		/>
	{/if}
</div>