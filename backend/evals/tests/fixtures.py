"""Era-representative HTML fixtures for unit tests.

Each constant is a miniature but *honest* rendition of its era's markup
conventions: real tag soup habits, real layout skeletons, enough body text
for the classifiers to have signal. Tests assert intended classifier
behavior against these, which is what protects thresholds during tuning.
"""

# ~1996: no doctype, <font>/<center>, bgcolor, table wrapper, unclosed <p>.
HTML_1996_PERSONAL = """<HTML>
<HEAD><TITLE>My Trip to the Grand Canyon</TITLE></HEAD>
<BODY BGCOLOR="#FFFFCC" TEXT="#000000" LINK="#0000FF">
<CENTER><FONT SIZE=6 COLOR="#AA0000">My Trip to the Grand Canyon</FONT></CENTER>
<HR>
<TABLE WIDTH=600 BORDER=0 BGCOLOR="#FFFFFF"><TR><TD>
<FONT FACE="Times New Roman">
<P>Last summer my family and I finally visited the Grand Canyon, something we
had been planning for almost three years. We drove from Phoenix in our old
station wagon and arrived just before sunset on the second day of the trip.
<P>The first sight of the canyon from the South Rim is something I will never
forget. Photographs simply do not prepare you for the scale of it. We hiked
part of the Bright Angel Trail the next morning and my brother nearly lost
his hat to a very determined squirrel near the three mile resthouse.
<P>If you ever get the chance to go, take plenty of water and start your hike
before dawn. The mule trains have the right of way on the trail and the
rangers will remind you of this fact many times.
</FONT>
</TD></TR></TABLE>
<CENTER><A HREF="index.html">Home</A> | <A HREF="photos.html">Photos</A> |
<A HREF="guestbook.html">Sign my guestbook!</A></CENTER>
<CENTER><FONT SIZE=1>This page hosted by GeoCities. Best viewed in Netscape.</FONT></CENTER>
</BODY></HTML>"""

# ~2003: HTML 4.01 doctype, cosmetic stylesheet, but layout carried by tables.
HTML_2003_TABLE_NEWS = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html><head><title>City Council Approves New Bridge Plan</title>
<link rel="stylesheet" type="text/css" href="/styles/main.css">
</head>
<body>
<table width="100%" border="0" cellpadding="4">
<tr><td colspan="2"><font size="5"><b>City Council Approves New Bridge Plan</b></font></td></tr>
<tr>
<td width="20%" valign="top" bgcolor="#eeeeee">
<a href="/news/">News</a><br><a href="/sport/">Sport</a><br>
<a href="/weather/">Weather</a><br><a href="/business/">Business</a><br>
<a href="/politics/">Politics</a><br><a href="/education/">Education</a><br>
</td>
<td valign="top">
<p>The city council voted seven to two on Tuesday evening to approve the
long-debated replacement of the Harbour Street bridge, ending a planning
process that has stretched over nearly a decade.</p>
<p>Construction is expected to begin in the spring and will take an estimated
two and a half years to complete. The existing bridge, built in 1936, will
remain open to pedestrians during most of the construction period.</p>
<p>Councillor Mary Edwards, who has championed the project since 1997, called
the vote a victory for common sense. Opponents cited the projected cost of
forty-one million dollars and the loss of two heritage buildings on the
northern approach.</p>
</td>
</tr>
</table>
</body></html>"""

# ~2007: XHTML doctype, div+CSS layout, WordPress fingerprints.
HTML_2007_BLOG = """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
 "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Why I Switched to Linux &#8211; Dave's Tech Blog</title>
<link rel="stylesheet" href="/wp-content/themes/kubrick/style.css" type="text/css" />
<meta name="generator" content="WordPress 2.2" />
</head>
<body>
<div id="header"><h1><a href="/">Dave's Tech Blog</a></h1></div>
<div id="content">
<div class="post">
<h2>Why I Switched to Linux</h2>
<p>After eleven years of running Windows on every machine I own, last month I
finally wiped my laptop and installed Ubuntu. Several readers asked what
pushed me over the edge, so here is the honest answer.</p>
<p>It was not ideology and it was not the license fees. It was the simple fact
that my four year old laptop had become unusably slow, and a live CD booted
faster from a scratched disc than my installed operating system did from the
hard drive. That comparison is difficult to argue with.</p>
<p>The migration was not painless. Wireless drivers took an evening of forum
archaeology, and I still keep a Windows partition around for tax software.
But three weeks in, I have no plans to go back.</p>
</div>
<div class="comments"><h3>2 Responses</h3>
<div class="comment"><p>Welcome to the club. Wait until you discover package managers properly.</p></div>
<div class="comment"><p>The tax software situation is real. I run mine in a virtual machine.</p></div>
</div>
</div>
<div id="sidebar"><ul><li><a href="/archives/">Archives</a></li>
<li><a href="/category/linux/">Linux</a></li><li><a href="/about/">About</a></li></ul></div>
</body></html>"""

# ~2020: HTML5, semantic tags, Open Graph, viewport.
HTML_2020_ARTICLE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta property="og:type" content="article">
<meta property="og:title" content="Inside the Effort to Archive the Entire Web">
<title>Inside the Effort to Archive the Entire Web | Example News</title>
</head>
<body>
<header><nav><a href="/">Home</a> <a href="/tech">Tech</a></nav></header>
<main>
<article>
<h1>Inside the Effort to Archive the Entire Web</h1>
<p>Every day, the web loses pages. Links rot, companies fold, and entire
platforms disappear with a few months of notice. A loose international
coalition of archivists is trying to keep pace, and their flagship
institution turns twenty-five this year.</p>
<p>The scale of the problem is difficult to overstate. Researchers estimate
that a quarter of the links cited in scholarly articles no longer resolve to
their original content, a phenomenon known as reference rot. For journalism
the picture is worse, since news organizations routinely restructure their
sites without redirects.</p>
<p>The archive's crawlers now collect hundreds of terabytes each week, but
coverage remains uneven. Pages behind logins, content rendered entirely in
the browser, and sites that block crawlers all slip through the net, leaving
holes that future historians will struggle to explain.</p>
</article>
</main>
<footer><a href="/about">About</a> <a href="/privacy">Privacy</a></footer>
</body></html>"""

# Modern client-rendered shell: framework marker, no readable content.
HTML_SPA_SHELL = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Post</title>
<meta name="viewport" content="width=device-width"></head>
<body>
<div id="root"></div>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"id":"1234567890","hydrate":true,"chunks":["main","post"],
"buildId":"abc123","runtimeConfig":{"api":"https://api.example.com/graphql"}}}}
</script>
<script src="/_next/static/chunks/main-8f7d2a.js"></script>
</body></html>"""

# Category/archive listing: repeated teaser template, pagination.
_TEASERS = "\n".join(
    f'<div class="teaser"><h3><a href="/news/story-{i}">Council story number {i} headline</a></h3>'
    f'<p class="excerpt">Short summary.</p>'
    f'<a href="/news/story-{i}" class="more">Read more</a></div>'
    for i in range(1, 13)
)
HTML_LIST_CATEGORY = f"""<!DOCTYPE html>
<html><head><title>News archive - page 2 | Example News</title></head>
<body>
<h1>News archive</h1>
{_TEASERS}
<div class="pagination"><a href="?page=1">1</a> <a href="?page=2">2</a>
<a href="?page=3">3</a> <a href="?page=3" rel="next">next</a></div>
</body></html>"""

# Search results page.
_RESULTS = "\n".join(
    f'<div class="result"><a href="/doc/{i}">Result document {i} about space jam</a></div>'
    for i in range(1, 11)
)
HTML_SEARCH_RESULTS = f"""<!DOCTYPE html>
<html><head><title>Search results for 'space jam' | Example</title></head>
<body>
<form action="/search"><input type="text" name="q" value="space jam"><input type="submit" value="Go"></form>
{_RESULTS}
</body></html>"""

# 1997-style frameset shell.
HTML_FRAMESET = """<HTML><HEAD><TITLE>Welcome to CyberWorld</TITLE></HEAD>
<FRAMESET COLS="150,*">
<FRAME SRC="nav.html" NAME="nav">
<FRAME SRC="main.html" NAME="main">
<NOFRAMES><BODY>Your browser does not support frames.
<A HREF="main.html">Enter here</A></BODY></NOFRAMES>
</FRAMESET></HTML>"""

# Forum / discussion thread: an opening post plus many comment posts. Lots of
# cumulative prose in small blocks, moderate (not link-dominated) link density,
# repeated post template — the structurally-hard "canonical content that looks
# like a list" case (forums, HN, reddit, Slashdot).
_POSTS = "\n".join(
    f'<div class="post"><div class="author"><a href="/user/u{i}">user{i}</a></div>'
    f'<div class="body"><p>This is comment number {i} in the thread. It makes a '
    f'substantive point about the topic under discussion, adding detail and a '
    f'concrete example so the exchange reads like real prose rather than a list '
    f'of links or navigation items strung together.</p></div>'
    f'<div class="meta"><a href="#p{i}">permalink</a> <a href="/reply/{i}">reply</a></div></div>'
    for i in range(1, 16)
)
HTML_FORUM_THREAD = f"""<!DOCTYPE html>
<html><head><title>How do I parse malformed HTML? - Dev Forum</title></head>
<body>
<div id="nav"><a href="/">Home</a> <a href="/forums">Forums</a> <a href="/tags">Tags</a></div>
<h1>How do I parse malformed HTML?</h1>
<div class="post opening"><div class="body"><p>I am trying to extract the main
article text from decades of archived web pages and many of them have badly
broken markup: unclosed tags, framesets, uppercase elements and tag soup that
defeats strict DOM parsers. What is the most robust approach that still works on
both 1996-era pages and modern documents without falling over?</p></div></div>
{_POSTS}
</body></html>"""

# 404 page.
HTML_ERROR_404 = """<!DOCTYPE html>
<html><head><title>404 Not Found</title></head>
<body><h1>404 Not Found</h1><p>The page you requested could not be found.</p></body></html>"""

# Home-ish portal page: many links, no repeated template classes, root path.
_PORTAL_LINKS = "\n".join(
    f'<a href="/section-{i}/">Section {i}</a>' for i in range(1, 21)
)
HTML_PORTAL_HOME = f"""<!DOCTYPE html>
<html><head><title>Example Portal</title></head>
<body>
<h1>Example Portal</h1>
<p>Welcome to the portal. Choose one of our sections below to begin reading,
or visit the help desk if you are new here and want a guided introduction.</p>
{_PORTAL_LINKS}
</body></html>"""


# --- plain-text bodies for dedup tests -------------------------------------

BODY_LONG_A = (
    "The municipal archive reopened to the public on Monday after a renovation "
    "that lasted almost three years and cost twelve million euros. Visitors can "
    "now consult the city's building records, census ledgers and photographic "
    "collections in a reading room that seats eighty people. The director said "
    "that digitisation of the most fragile documents would continue for another "
    "decade, with priority given to materials from before the great fire of "
    "1911. Around four hundred thousand pages have been scanned so far, and the "
    "archive plans to publish them online in quarterly batches. Local historians "
    "welcomed the reopening but warned that funding for specialist staff remains "
    "uncertain beyond the next budget cycle, which ends in two years."
)
# Same body with two small edits (typo fix + one word swapped).
BODY_LONG_A_EDIT = BODY_LONG_A.replace("almost three years", "nearly three years").replace(
    "quarterly batches", "monthly batches"
)
BODY_LONG_B = (
    "Astronomers announced on Thursday the discovery of a ring system around a "
    "small icy world orbiting far beyond Neptune, a finding that challenges "
    "current models of how rings form and survive. The object, roughly two "
    "hundred and thirty kilometres across, was observed as it passed in front "
    "of a distant star, briefly dimming the starlight twice before and twice "
    "after the main occultation. That symmetric pattern is the signature of a "
    "ring. What puzzles researchers is the ring's distance from the body, well "
    "outside the zone where tidal forces are thought to prevent moon formation. "
    "Several teams are now competing for telescope time to confirm the result "
    "during the next favourable alignment in the coming observing season."
)
