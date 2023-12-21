<script>
	import { instantMeiliSearch } from '@meilisearch/instant-meilisearch';
	import instantsearch from 'instantsearch.js';
    import { searchBox, hits, pagination, refinementList, rangeSlider, stats, clearRefinements } from 'instantsearch.js/es/widgets';
    import { onMount, afterUpdate } from 'svelte';

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
        selectedProject = projects.find(project => project.key === event.target.value);

        // Set the index to the selected project
        search.helper.setIndex(selectedProject.key);

        // Refresh the search
        search.refresh();
    }

    onMount(() => {
        fetch('http://localhost:1337/api/projects?filters[user][username][$eq]=linksmith&filters[has_index][$eq]=true', {
            headers: {
                'Authorization': 'Bearer d7593f69a4b63daf56107726d502c9e83c32c1c5bf82f05118feb888f3eb1849dd07474f49c8305734796eb08d43bd9bfb0fc4c0998a892531e4e844741b7838eeb467140a7d1c65d72cb5b9308fe9d9e5b01d3344f8ec111a6a3d8f3fbdd10515ba354131fbbfa313f1d8311132ee78d522bde60e384eaf94a2fcb04c6f9037'
            }
        })
        .then(response => response.json())
        .then(data => {
            // map data.data to project with project.attributes.slug : project.attributes.title
            projects = data.data.map(project => {
                return {
                    key: project.attributes.slug,
                    value: project.attributes.title
                }
            });                    

            selectedProject = projects[0];
            console.log(selectedProject);
            search = instantsearch({
                indexName: selectedProject.key,
                attributesForFaceting: ['domain', 'unix_timestamp'],
                searchClient: instantMeiliSearch('https://meilisearch.linksmith.nl', 'BLJq9qcZh5nPqSTXhpAN', {
                    attributesToHighlight: ['text', 'title', ],
                    attributesToSnippet: ['text:36'],
                    highlightPreTag: '<strong class="ais-Highlight-highlighted">',
                    highlightPostTag: '</strong>',
                    limit: 10,
                    showMatchesPosition: true,
                    showRankingScore: true,
                }).searchClient
            });

            search.addWidgets([
                searchBox({
                    container: '#searchbox',
                }),

                hits({
                    container: '#hits',
                    templates: {
                        item: (hit, { html, components }) =>
                            html`
                                <span class="hit-domain">${components.Highlight({ attribute: 'domain', hit })}</span>
                                <h3 class="hit-title">
                                    <a href="${hit.wayback_machine_url}" >
                                        ${components.Highlight({ attribute: 'title', hit })}
                                    </a>
                                </h3>
                                <p class="hit-text">${components.Snippet({ attribute: 'text', hit })}</p>
                            `,
                    }
                }),

                pagination({
                    container: '#pagination',
                    scrollTo: '#hits',
                }),

                refinementList({
                    container: '#refinement-list-domain',
                    attribute: 'domain',
                    showMore: true,
                    showMoreLimit: 20,            
                }),

                rangeSlider({
                    container: '#range-slider-dates',
                    attribute: 'unix_timestamp',

                    tooltips: {
                            format: function(unix_timestamp) {
                                var date = new Date(unix_timestamp * 1000);
                                var year = date.getFullYear();
                                var month = "0" + (date.getMonth() + 1);
                                var day = "0" + date.getDate();
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
                        `,
                    },
                }),

                clearRefinements({
                    container: '#clear',
                    templates: {
                        resetLabel: 'Clear filters',
                    },
                }),

            ]);

            search.start();

        })
        .catch(error => {
            console.error('Error:', error);
        });
    });
</script>

<style>
    @import '../css/reset-min.css';
    @import '../css/algolia-min.css';
    @import '../css/search-page.css';
</style>

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
        <div id="refinement-list-domain"></div>
        <h3>Periods</h3>
        <div id="range-slider-dates"></div>
        <div id="clear"></div>
    </div>

    <div class="wrapper">
        <h1>Search in '{selectedProject.value}' </h1>
        <div id="searchbox" focus></div>
        <div id="summary"></div>
        <div id="hits"></div>
        <div id="pagination"></div>
    </div>

</div>