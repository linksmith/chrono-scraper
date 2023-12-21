# Chrono Scraper

Chrono Scraper is a web scraping tool designed to extract data from the Wayback Machine API and index this data for full text search. 

## Architecture

- Svelte.js as the app front-end
- Strapi as the CMS
- FastAPI as the app backend
- Meilisearch as the index
- Ngnix: reverse proxy
- Sqlite: as the database (to be changed to Postgres)

## Features

- Full Text Search of websites scraped from the Wayback Machine
- Create a project and add domains to a project.
- Scrape the domains in a project from the Wayback Machine add to Meilisearch index.
- TODO:
    - Client based version with index in browser.
    - Request whitelisting from Wayback Machine to remove reliance on Proxy service

## Installation

To install Chrono Scraper, follow these steps:

0. Install Docker
1. Clone the repository: `git clone https://github.com/your-username/chrono-scraper.git`
2. Run dev: `docker-compose -f docker-compose-dev.yml up`
3. TODO: Run in production: 

## Contributing

Contributions are welcome! If you have any ideas, suggestions, or bug reports, please open an issue or submit a pull request.

## License

This project is licensed under the [GPLv3 License](LICENSE).
