# Gold review checklist

24 gold documents (6 approved, 18 draft). Drafted from **readability** so the primary systems under test (pipeline, trafilatura) don't grade their own output.

**For each draft:** open the archived page, correct `title` + `body` in the linked YAML (body = canonical content only — drop nav/related/boilerplate, add back anything missed), then set `review_status: approved`. Delete the file to reject (🚩 rows below are likely rejects).

Then: `docker compose exec backend python -m evals.runner validate-gold` and re-run `score` (without `--include-drafts`).

## early_static (1)

| ✓ | sample | words | archived page | gold file | note |
|---|--------|-------|---------------|-----------|------|
| ☐ | slashdot-articles--49 | 11627 | [view](https://web.archive.org/web/20050808133911/http://slashdot.org/article.pl?sid=03/03/17/1213212) | [slashdot-articles--49.yaml](slashdot-articles--49.yaml) | story + comment-heavy page. |

## table_layout (6)

| ✓ | sample | words | archived page | gold file | note |
|---|--------|-------|---------------|-----------|------|
| ✅ | bbc-news-stories--383 | 540 | [view](https://web.archive.org/web/20061222135929/http://news.bbc.co.uk/2/hi/4888676.stm) | [bbc-news-stories--383.yaml](bbc-news-stories--383.yaml) | weekly roundup (borderline article). |
| ☐ | hackernews-items--317 | 1542 | [view](https://web.archive.org/web/20210609224556/http://news.ycombinator.com/item?id=2170560&) | [hackernews-items--317.yaml](hackernews-items--317.yaml) | discussion thread — canonical content is the comment thread. |
| ☐ | imdb-title-pages--89 | 292 | [view](https://web.archive.org/web/20060205052107/http://www.imdb.com:80/title/tt0000182/) | [imdb-title-pages--89.yaml](imdb-title-pages--89.yaml) | ⚠️ structured entity page, not prose — known-hard; body ambiguous. Consider **reject**. |
| ☐ | livejournal-brad--75 | 1126 | [view](https://web.archive.org/web/20051122151816/http://brad.livejournal.com:80/2143713.html) | [livejournal-brad--75.yaml](livejournal-brad--75.yaml) |  |
| ☐ | phpbb-community-threads--82 | 3957 | [view](https://web.archive.org/web/20060814225333/http://www.phpbb.com:80/phpBB/viewtopic.php?p=2268463&sid=be3fa142cecb88c6229a7d4d96c5c57f) | [phpbb-community-threads--82.yaml](phpbb-community-threads--82.yaml) | forum thread — body = the posts. |
| ☐ | techcrunch-2008--458 | 656 | [view](https://web.archive.org/web/20080708215557/http://www.techcrunch.com/2008/01/20/should-there-be-a-privacy-line-with-life-streaming/trackback) | [techcrunch-2008--458.yaml](techcrunch-2008--458.yaml) | 🚩 /trackback endpoint — **reject**, not the article |

## css_layout (4)

| ✓ | sample | words | archived page | gold file | note |
|---|--------|-------|---------------|-----------|------|
| ☐ | googleblog-2007--115 | 819 | [view](https://web.archive.org/web/20091208140943/http://googleblog.blogspot.com:80/2009/12/this-week-in-search-12409.html) | [googleblog-2007--115.yaml](googleblog-2007--115.yaml) |  |
| ☐ | w3c-css1-spec--8 | 22933 | [view](https://web.archive.org/web/20081025142738/http://www.w3.org:80/TR/REC-CSS1/) | [w3c-css1-spec--8.yaml](w3c-css1-spec--8.yaml) | W3C spec (long; structured). |
| ✅ | w3c-html401-spec--2 | 2102 | [view](https://web.archive.org/web/20000815083343/http://www.w3.org:80/TR/html401/) | [w3c-html401-spec--2.yaml](w3c-html401-spec--2.yaml) | W3C spec (long; structured). |
| ✅ | wikipedia-2005--101 | 6124 | [view](https://web.archive.org/web/20071202041701/http://en.wikipedia.org/wiki/HTML) | [wikipedia-2005--101.yaml](wikipedia-2005--101.yaml) |  |

## html5_semantic (12)

| ✓ | sample | words | archived page | gold file | note |
|---|--------|-------|---------------|-----------|------|
| ☐ | cern-first-website--1 | 171 | [view](https://web.archive.org/web/20130427093205/http://info.cern.ch:80/hypertext/WWW/TheProject.html) | [cern-first-website--1.yaml](cern-first-website--1.yaml) | the first web page ever (1991 content; short). |
| ☐ | devto-posts--269 | 1710 | [view](https://web.archive.org/web/20200128152732/https://dev.to/configcat/switches-for-future-feature-flags-in-product-development-4pcj) | [devto-posts--269.yaml](devto-posts--269.yaml) |  |
| ✅ | govuk-news--232 | 833 | [view](https://web.archive.org/web/20211202065953/https://www.gov.uk/government/news/children-to-shape-the-future-of-the-family-justice-system) | [govuk-news--232.yaml](govuk-news--232.yaml) |  |
| ✅ | nos-artikelen--206 | 1769 | [view](https://web.archive.org/web/20220518184227/http://nos.nl/artikel/122976-probo-) | [nos-artikelen--206.yaml](nos-artikelen--206.yaml) |  |
| ☐ | pointer-kro-ncrv--242 | 290 | [view](https://web.archive.org/web/20200812200941/https://pointer.kro-ncrv.nl/artikelen/spektakeldebat-rutte-en-baudet-een-hit-op-google?utm_campaign=Pointer%20%28KRO-NCRV%29&utm_medium=email&utm_source=Revue%20newsletter) | [pointer-kro-ncrv--242.yaml](pointer-kro-ncrv--242.yaml) |  |
| ☐ | stackoverflow-questions--126 | 357 | [view](https://web.archive.org/web/20160210011536/http://stackoverflow.com/questions/10000020/ajax-post-to-google-spreadsheet) | [stackoverflow-questions--126.yaml](stackoverflow-questions--126.yaml) |  |
| ✅ | substack-acx--256 | 2892 | [view](https://web.archive.org/web/20220713165520/https://astralcodexten.substack.com/p/a-guide-to-asking-robots-to-design?utm_source=%2Fprofile%2F2-chris-best&utm_medium=reader2&s=w) | [substack-acx--256.yaml](substack-acx--256.yaml) |  |
| ☐ | tumblr-staff-posts--142 | 131 | [view](https://web.archive.org/web/20151109133551/http://staff.tumblr.com:80/post/101707438755/this-bluespace-thing-you-guys-are-doing-hit-the) | [tumblr-staff-posts--142.yaml](tumblr-staff-posts--142.yaml) |  |
| ☐ | twitter-modern-shell--302 | 199 | [view](https://web.archive.org/web/20220607144615/https://twitter.com/elonmusk/status/1008013111058526209?lang=fa) | [twitter-modern-shell--302.yaml](twitter-modern-shell--302.yaml) | ⚠️ client-rendered X shell — body may be only tweet text/og-meta. **Reject** if no real content. |
| ☐ | verge-articles-2016--159 | 2091 | [view](https://web.archive.org/web/20160206104421/http://www.theverge.com:80/2016/1/26/10830274/the-girlfriend-experience-tv-starz-amy-seimetz-lodge-kerrigan/in/10579849) | [verge-articles-2016--159.yaml](verge-articles-2016--159.yaml) |  |
| ☐ | waitbutwhy-posts--498 | 36372 | [view](https://web.archive.org/web/20170929230238/https://waitbutwhy.com/2017/04/neuralink-cleanversion.html) | [waitbutwhy-posts--498.yaml](waitbutwhy-posts--498.yaml) |  |
| ☐ | wikipedia-modern--200 | 17971 | [view](https://web.archive.org/web/20241209210955/https://en.wikipedia.org/wiki/Internet) | [wikipedia-modern--200.yaml](wikipedia-modern--200.yaml) |  |

## spa_hydrated (1)

| ✓ | sample | words | archived page | gold file | note |
|---|--------|-------|---------------|-----------|------|
| ☐ | bbc-news-modern--176 | 1078 | [view](https://web.archive.org/web/20161208085011/http://www.bbc.com/news/blogs-echochambers-28255233) | [bbc-news-modern--176.yaml](bbc-news-modern--176.yaml) |  |

