<script>
	import { instantMeiliSearch } from '@meilisearch/instant-meilisearch';
	import instantsearch from 'instantsearch.js';
	import {
		searchBox,
		hits,
		pagination,
		refinementList,
		rangeSlider,
		stats,
		clearRefinements
	} from 'instantsearch.js/es/widgets';
	import { onMount, afterUpdate } from 'svelte';
	import { env } from '$env/dynamic/public';

	/**
	 * @type {import("instantsearch.js/es/lib/InstantSearch").default<{ [x: string]: Partial<{ query: string; } & { configure: import("algoliasearch-helper").PlainSearchParameters; } & { geoSearch: { boundingBox: string; }; } & { hierarchicalMenu: { [rootAttribute: string]: string[]; }; } & { hitsPerPage: number; } & { page: number; } & { menu: { [attribute: string]: string; }; } & { numericMenu: { [attribute: string]: string; }; } & { // Loop through the project data and create an option element for each project
	page: number; } & { // currentIndexSlug = select.options[selectedIndex].value;
	range: { [attribute: string]: string; }; } & { ratingMenu: { [attribute: string]: number | undefined; }; } & { refinementList: { [attribute: string]: string[]; }; } & { relevantSort: number; } & { query: string; } & { sortBy: string; } & { toggle: { [attribute: string]: boolean; }; } & { query: string; } & { places: { query: string; position: string; }; }>; }, Record<string, unknown>>}
	 */
	let search;
	/**
	 * @type {any[]}
	 */
	let projects = {};
	let selectedProject = {};

	function updateSelectedProject(event) {
		// Get the selected project
		selectedProject = projects.find((project) => project.key === event.target.value);

		// Set the index to the selected project
		search.helper.setIndex(selectedProject.key);

		// Refresh the search
		search.refresh();
	}

	onMount(() => {
		fetch(
			'http://localhost:1337/api/projects?filters[user][username][$eq]=linksmith&filters[has_index][$eq]=true',
			{
				headers: {
					Authorization: 'Bearer ' + env.PUBLIC_STRAPI_JWT_SECRET
				}
			}
		)
			.then((response) => response.json())
			.then((data) => {
				// map data.data to project with project.attributes.slug : project.attributes.title
				projects = data.data.map((project) => {
					return {
						key: project.attributes.slug,
						value: project.attributes.title
					};
				});

				selectedProject = projects[0];
				console.log(selectedProject);
				search = instantsearch({
					indexName: selectedProject.key,
					attributesForFaceting: ['domain', 'unix_timestamp'],
					searchClient: instantMeiliSearch(
						env.PUBLIC_MEILISEARCH_URL,
						env.PUBLIC_MEILISEARCH_API_KEY,
						{
							attributesToHighlight: ['text', 'title'],
							attributesToSnippet: ['text:36'],
							highlightPreTag: '<strong class="ais-Highlight-highlighted">',
							highlightPostTag: '</strong>',
							limit: 10,
							showMatchesPosition: true,
							showRankingScore: true
						}
					).searchClient
				});

				search.addWidgets([
					searchBox({
						container: '#searchbox'
					}),

					hits({
						container: '#hits',
						templates: {
							item: (hit, { html, components }) =>
								html`
									<span class="hit-domain"
										>${components.Highlight({ attribute: 'domain', hit })}</span
									>
									<h3 class="hit-title">
										<a href="${hit.wayback_machine_url}">
											${components.Highlight({ attribute: 'title', hit })}
										</a>
									</h3>
									<p class="hit-text">${components.Snippet({ attribute: 'text', hit })}</p>
								`
						}
					}),

					pagination({
						container: '#pagination',
						scrollTo: '#hits'
					}),

					refinementList({
						container: '#refinement-list-domain',
						attribute: 'domain',
						showMore: true,
						showMoreLimit: 20
					}),

					rangeSlider({
						container: '#range-slider-dates',
						attribute: 'unix_timestamp',

						tooltips: {
							format: function (unix_timestamp) {
								var date = new Date(unix_timestamp * 1000);
								var year = date.getFullYear();
								var month = '0' + (date.getMonth() + 1);
								var day = '0' + date.getDate();
								var formattedTime = year + '-' + month.substr(-2) + '-' + day.substr(-2);
								return formattedTime;
							}
						}
					}),

					stats({
						container: '#summary',
						templates: {
							text: `
                            {{#helpers.formatNumber}}{{nbHits}}{{/helpers.formatNumber}} results found in {{processingTimeMS}}ms
                        `
						}
					}),

					clearRefinements({
						container: '#clear',
						templates: {
							resetLabel: 'Clear filters'
						}
					})
				]);

				search.start();
			})
			.catch((error) => {
				console.error('Error:', error);
			});
	});
</script>

<div class="container">
	<div class="sidebar">
		<h2>Projects</h2>
		<select id="projects" {selectedProject} on:change={updateSelectedProject}>
			{#each Object.entries(projects) as [key, project]}
				<option value={project.key}>
					{project.value}
				</option>
			{/each}
		</select>
		<h2>Filters</h2>
		<h3>Domains</h3>
		<div id="refinement-list-domain" />
		<h3>Periods</h3>
		<div id="range-slider-dates" />
		<div id="clear" />
	</div>

	<div class="wrapper">
		<h1>Search in '{selectedProject.value}'</h1>
		<div id="searchbox" focus />
		<div id="summary" />
		<div id="hits" />
		<div id="pagination" />
	</div>
</div>

<style>
	@import '../css/reset-min.css';
	@import '../css/algolia-min.css';
	@import '../css/search-page.css';
</style>
