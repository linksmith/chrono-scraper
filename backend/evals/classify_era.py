"""Era classification from structural markup fingerprints.

Buckets pages into web-design eras by *how they are built*, not when they
were captured — a 2010 capture of a page last redesigned in 1997 should land
in the table-layout era, because that is what the extractor has to cope with.
The snapshot year is only used as a weak tiebreak when structure is mute.

Eras (ordered):

* ``early_static``   ~1993–1998: no CSS, ``<font>``/``<center>``/bgcolor,
                      framesets, often no doctype.
* ``table_layout``   ~1997–2004: layout carried by nested tables, CSS at most
                      cosmetic.
* ``css_layout``     ~2003–2012: div+CSS layout, HTML4/XHTML doctypes.
* ``html5_semantic`` ~2011–present: HTML5 doctype, semantic tags, viewport.
* ``spa_hydrated``   ~2016–present: client-side framework shells; the payload
                      HTML may contain little or no readable content.
"""

from __future__ import annotations

from dataclasses import dataclass

from evals.config import EraConfig
from evals.html_features import PageFeatures

ERAS = ["early_static", "table_layout", "css_layout", "html5_semantic", "spa_hydrated"]

# Weak priors used only when structure gives no signal at all.
_YEAR_PRIORS = [
    (1998, "early_static"),
    (2004, "table_layout"),
    (2011, "css_layout"),
    (2017, "html5_semantic"),
    (9999, "spa_hydrated"),
]


@dataclass(frozen=True)
class EraResult:
    label: str
    confidence: float
    signals: list[str]


def doctype_flavor(doctype: str) -> str:
    """'html5' | 'xhtml' | 'html4' | 'html32' | 'html2' | 'none' | 'other'."""
    d = doctype.strip().lower()
    if not d:
        return "none"
    if d == "doctype html":
        return "html5"
    if "xhtml" in d:
        return "xhtml"
    if "html 4" in d:
        return "html4"
    if "html 3.2" in d:
        return "html32"
    if "html 2" in d or "html level 2" in d:
        return "html2"
    return "other"


def classify_era(
    features: PageFeatures,
    config: EraConfig | None = None,
    snapshot_year: int | None = None,
) -> EraResult:
    cfg = config or EraConfig()
    f = features
    flavor = doctype_flavor(f.doctype)
    has_css = f.stylesheet_links > 0 or f.style_tags > 0
    signals: list[str] = []

    # 1) SPA / hydration shells — framework markers are near-conclusive.
    if f.framework_markers:
        signals.append(f"framework:{','.join(f.framework_markers)}")
        return EraResult("spa_hydrated", 0.95, signals)
    if f.script_ratio >= cfg.spa_script_ratio and f.total_text_chars < cfg.spa_max_text_chars:
        signals.append(
            f"script_heavy_shell(ratio={f.script_ratio:.2f},text={f.total_text_chars})"
        )
        return EraResult("spa_hydrated", 0.75, signals)

    # 2) HTML5-era markup.
    if flavor == "html5" or f.html5_tag_count >= 2:
        if flavor == "html5":
            signals.append("doctype:html5")
        if f.html5_tag_count >= 2:
            signals.append(f"html5_tags:{f.html5_tag_count}")
        if f.meta_viewport:
            signals.append("meta_viewport")
        confidence = min(0.95, 0.6 + 0.15 * len(signals))
        return EraResult("html5_semantic", confidence, signals)

    # 3) Early static web — framesets, legacy markup, and no CSS at all.
    early_points = 0
    if f.has_frameset:
        signals.append("frameset")
        early_points += 2
    if not has_css:
        if f.legacy_tag_count >= 2 or f.legacy_attr_count >= 2:
            signals.append(
                f"legacy_markup(tags={f.legacy_tag_count},attrs={f.legacy_attr_count})"
            )
            early_points += 2
        if flavor in ("none", "html2", "html32"):
            signals.append(f"doctype:{flavor}")
            early_points += 1
    if early_points >= 2:
        return EraResult("early_static", min(0.9, 0.5 + 0.15 * early_points), signals)

    # 4) Table layout — most text lives inside tables; CSS may exist but the
    #    skeleton is <table>. (Checked before css_layout so 2001-style sites
    #    with a cosmetic stylesheet land here.)
    if f.table_text_ratio >= cfg.table_layout_text_ratio and f.table_count >= 1:
        signals.append(f"table_text_ratio:{f.table_text_ratio:.2f}")
        if f.font_count:
            signals.append(f"font_tags:{f.font_count}")
        if f.legacy_attr_count:
            signals.append(f"legacy_attrs:{f.legacy_attr_count}")
        confidence = min(0.9, 0.5 + 0.15 * len(signals))
        return EraResult("table_layout", confidence, signals)

    # 5) CSS/div layout — positive evidence version.
    if has_css and f.div_count > f.table_count:
        signals.append(f"css_layout(stylesheets={f.stylesheet_links},divs={f.div_count})")
        if flavor in ("xhtml", "html4"):
            signals.append(f"doctype:{flavor}")
        return EraResult("css_layout", min(0.85, 0.5 + 0.15 * len(signals)), signals)

    # 6) Structure is ambiguous — fall back to the capture-year prior.
    if snapshot_year:
        for cutoff, label in _YEAR_PRIORS:
            if snapshot_year <= cutoff:
                signals.append(f"year_prior:{snapshot_year}")
                return EraResult(label, 0.35, signals)

    signals.append("no_signals_default")
    return EraResult("css_layout", 0.25, signals)
