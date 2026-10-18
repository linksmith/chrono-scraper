"""Extraction-quality evaluation harness for Chrono Scraper.

Standalone package (importable alongside ``app``) that builds an era-diverse
corpus of archived pages from the Wayback Machine and Common Crawl, classifies
them by structure and page type, near-dup detects extracted bodies, and scores
content extractors against human-approved gold annotations.

Entry point: ``python -m evals.runner --help`` (run inside the backend container).
"""

__version__ = "0.1.0"
