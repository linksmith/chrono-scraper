import { instantMeiliSearch } from '@meilisearch/instant-meilisearch';
import instantsearch from 'instantsearch.js';
import {
  searchBox,
  hits,
  pagination,
  refinementList,
  rangeSlider,
  stats,
  clearRefinements,
} from 'instantsearch.js/es/widgets';
import utils from './utils';

export default () => ({
  projects: [],
  selectedProject: null,
  search: null,
  meiliSearchHost: null,

  fetchData() {
    fetch('/api/projects') // Replace with your API URL
      .then((response) => response.json())
      .then((data) => {
        this.projects = data;

        if (this.projects.length > 0) {
          this.selectedProject = this.projects[0];
          this.initInstantSearch(
            this.selectedProject.index_name,
            this.selectedProject.index_search_key,
          );
        }
      });
  },

  updateSelectedProjectId(event) {
    let currentQuery = this.search.helper.state.query;
    this.selectedProject = this.getProject(event.target.value);

    if (this.selectedProject !== null) {
      this.initInstantSearch(
        this.selectedProject.index_name,
        this.selectedProject.index_search_key,
      );
    }
    this.search.helper.state.query = currentQuery;
  },

  getProject(selectedProjectId) {
    if (selectedProjectId === null) {
      console.error('selectedProjectId is null');
      return null;
    }

    // let projects = JSON.parse(JSON.stringify(this.projects))
    for (let i = 0; i < this.projects.length; i++) {
      if (this.projects[i].id === parseInt(selectedProjectId)) {
        return this.projects[i];
      }
    }

    return null;
  },

  initInstantSearch(index_name, index_search_key) {
    this.search = instantsearch({
      indexName: index_name,
      attributesForFaceting: ['domain_name', 'unix_timestamp'],
      hitsPerPage: 16,
      searchClient: instantMeiliSearch(this.meiliSearchHost, index_search_key, {
        attributesToHighlight: ['text', 'title'],
        attributesToSnippet: ['text:36'],
        highlightPreTag: '<mark class="ais-Highlight-highlighted">',
        highlightPostTag: '</mark>',
        showRankingScore: true,
      }).searchClient,
    });

    this.search.addWidgets([
      searchBox({
        container: '#searchbox',
        cssClasses: {
          root: 'w-full',
          form: 'inline',
          input:
            'block h-full w-full border-0 py-0 pr-0 text-gray-900 placeholder:text-gray-400 focus:ring-0 sm:text-sm',
        },
        placeholder: 'Search...',
        showReset: false,
        showSubmit: false,
      }),

      hits({
        container: '#hits',
        templates: {
          item: (hit, { html, components }) => html`
            <div
              role="presentation"
              class="border w-full mx-auto border-gray-400 rounded-lg mb-2 md:p-4 bg-white sm:py-3 py-4 px-2"
              data-article-path="${hit.wayback_machine_url}"
              data-content-user-id="${hit.domain}"
            >
              <div class="flex flex-col">
                <p class="text text-gray-700 text-sm hover:text-black pb-1">
                  ${components.Highlight({ attribute: 'domain_name', hit })}
                </p>
                <p class="block text-xs text-gray-600 hover:text-black">
                  <time datetime="${hit.unix_timestamp}">
                    ${utils.formatTimestamp(hit.unix_timestamp)}
                  </time>
                </p>
              </div>
              <div class="">
                <h2 class="text-2xl font-bold text-gray-900 leading-7">
                  <a
                    href="${hit.wayback_machine_url}"
                    id="article-link-151230"
                    target="_blank"
                  >
                    ${components.Highlight({ attribute: 'title', hit })}
                  </a>
                </h2>
                <!--                                      <div class="mb-2">-->
                <!--                                          <a href="#" class="text-sm text-gray-600 p-1 hover:text-black">-->
                <!--                                            <span class="text-opacity-50">#</span>-->
                <!--                                            tailwind-->
                <!--                                          </a>-->
                <!--                                      </div>-->
                <div class="mb-1 leading-6 text-gray-700">
                  ${components.Snippet({ attribute: 'text', hit })}
                </div>
              </div>
            </div>
          `,
        },
      }),

      pagination({
        container: '#pagination',
        scrollTo: '#header',
        showLast: false,
        showFirst: false,
        cssClasses: {
          root: 'flex items-center justify-center border-t border-gray-200 px-4 sm:px-0 mx-auto',
          list: 'hidden md:-mt-px md:flex',
          item: 'inline-flex items-center border-t-2 border-transparent px-4 pt-4',
          itemSelected:
            'inline-flex items-center border-t-2 border-indigo-500 px-4 pt-4 text-sm font-medium text-indigo-600',
          itemDisabled:
            'inline-flex items-center border-t-2 border-transparent px-4 pt-4 text-sm font-medium text-gray-500 hover:border-gray-300 hover:text-gray-700',
          link: ' text-sm font-medium text-gray-500 hover:border-gray-300 hover:text-gray-7000',
          linkSelected:
            'relative inline-flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-gray-50',
          linkDisabled:
            'relative inline-flex items-center px-4 py-2 text-sm font-medium text-gray-500 bg-gray-50',
        },
      }),

      refinementList({
        container: '#refinement-list-domain',
        attribute: 'domain_name',
        showMore: true,
        showMoreLimit: 20,
      }),

      rangeSlider({
        container: '#range-slider-dates',
        attribute: 'unix_timestamp',

        tooltips: {
          format: function (unix_timestamp) {
            // convert unix_timestamp to string
            unix_timestamp = unix_timestamp.toString();

            const year = parseInt(unix_timestamp.substring(0, 4), 10);
            const month = parseInt(unix_timestamp.substring(4, 6), 10) - 1; // Month is 0-indexed in JavaScript Date
            const day = parseInt(unix_timestamp.substring(6, 8), 10);

            // Create a new Date object
            const date = new Date(year, month, day);

            // Format the date to dd-MM-yyyy
            return date.toLocaleDateString('nl-NL', {
              year: 'numeric',
              month: '2-digit',
              day: '2-digit',
            });
          },
        },
      }),

      stats({
        container: '#summary',
        templates: {
          text: `
                      {{nbHits}} results found in {{processingTimeMS}}ms
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

    this.search.start();
  },

  setMeiliSearchHost() {
    const protocol = window.location.protocol;
    const host = window.location.host;
    const port = 7700;
    this.meiliSearchHost = `${protocol}//${host}:${port}`;
  },

  init() {
    this.setMeiliSearchHost();
    this.fetchData();
  },
});
