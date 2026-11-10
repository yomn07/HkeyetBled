"""Nettoyage : HTML Wikipédia/Wikivoyage -> texte structuré, réparation d'encodage,
normalisation Unicode et arabe, suppression des appels de notes, détection de langue,
suppression du boilerplate répété sur un même site.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict

from bs4 import BeautifulSoup, NavigableString, Tag

try:
    import ftfy  # type: ignore
except ImportError:  # pragma: no cover
    ftfy = None

# ----------------------------------------------------------------------------
# HTML MediaWiki
# ----------------------------------------------------------------------------
STOP_SECTIONS = {
    # fr
    "notes et references", "references", "notes", "bibliographie", "liens externes", "voir aussi",
    "annexes", "articles connexes", "sources", "notes et sources", "references et notes",
    # en
    "external links", "see also", "further reading", "bibliography", "citations", "footnotes",
    # ar
    "مراجع", "المراجع", "وصلات خارجية", "روابط خارجية", "انظر أيضا", "انظر أيضًا", "انظر ايضا",
    "مصادر", "المصادر", "الهوامش", "هوامش", "ملاحظات", "قراءات إضافية", "المراجع والهوامش",
}

REMOVE_SELECTORS = [
    "style", "script", "table", "figure", "sup.reference", "sup", ".mw-editsection", ".reference",
    ".references", ".reflist", ".mw-references-wrap", ".navbox", ".metadata", ".hatnote", ".dablink",
    ".ambox", ".bandeau-container", ".bandeau-portail", '[class*="bandeau"]', ".homonymie", ".thumb",
    ".gallery", ".toc", "#toc", ".mw-empty-elt", ".noprint", ".catlinks", ".printfooter", ".error",
    "#coordinates", ".coordinates", ".geo-dms", ".geo", '[class*="infobox"]', ".mw-kartographer-maplink",
    ".listing-metadata", ".listing-edit", ".listing-coordinates", ".mw-collapsible", ".navigation-only",
    ".plainlinks.metadata", ".bandeau-section", ".pagebanner", ".wv-pagebanner", ".mapframe",
    ".mw-cite-backlink", ".autres-projets", ".sisterproject", ".portail",
]

_HEADINGS = {"h2", "h3", "h4", "h5"}


def _norm_heading(t: str) -> str:
    from .common import strip_accents

    return strip_accents(t.lower()).strip(" :.")


def _blocks(node: Tag):
    for child in node.children:
        if isinstance(child, NavigableString) or not isinstance(child, Tag):
            continue
        if child.name in _HEADINGS or child.name in ("p", "ul", "ol", "dl", "blockquote", "pre"):
            yield child
        elif child.name in ("div", "section"):
            yield from _blocks(child)


def mediawiki_html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for sel in REMOVE_SELECTORS:
        for t in soup.select(sel):
            t.decompose()
    for br in soup.find_all("br"):
        br.replace_with(" ")
    root = soup.select_one(".mw-parser-output") or soup.body or soup
    lines: list[str] = []
    for b in _blocks(root):
        if b.name in _HEADINGS:
            h = _txt(b)
            if _norm_heading(h) in STOP_SECTIONS:
                break  # tout ce qui suit = références / liens
            lines.append(f"## {h}")
        elif b.name in ("ul", "ol"):
            for li in b.find_all("li", recursive=False):
                t = _txt(li)
                if t:
                    lines.append(f"- {t}")
        elif b.name == "dl":
            for d in b.find_all(["dt", "dd"]):
                t = _txt(d)
                if t:
                    lines.append(t)
        else:
            t = _txt(b)
            if t:
                lines.append(t)
    return "\n".join(lines)


def _txt(el: Tag) -> str:
    """Inline text without spurious spaces around <b>/<a> tags ("L'<b>amphithéâtre</b>")."""
    return re.sub(r"\s+", " ", el.get_text("")).strip()


# ----------------------------------------------------------------------------
# Normalisation du texte
# ----------------------------------------------------------------------------
_INVISIBLE = re.compile("[­​-‏‪-‮⁠-⁩﻿]")
_HARAKAT = re.compile("[ً-ٰٟۖ-ۭ]")
_TATWEEL = "ـ"
_CITATIONS = re.compile(
    r"\[\s*(?:\d+|[a-z]|[ivx]+|note\s*\d+|n\s*\d+|r[ée]f\.?\s*n[ée]cessaire|citation\s+n[ée]cessaire|"
    r"citation needed|clarification needed|when\?|which\?|lien mort|archive|"
    r"[٠-٩]+|بحاجة لمصدر|من صاهو|متى؟|ملاحظة\s*\d+|\d+\s*[,:–-]\s*\d+)\s*\]",
    re.I,
)
_SPACES = re.compile(r"[ \t  -   　]+")


def normalize_text(s: str, strip_diacritics: bool = True) -> str:
    if ftfy is not None:
        s = ftfy.fix_text(s)  # répare le mojibake type "Ã©" -> "é"
    s = unicodedata.normalize("NFKC", s)  # formes de présentation arabes -> lettres standard
    s = _INVISIBLE.sub("", s)
    s = s.replace(_TATWEEL, "")
    if strip_diacritics:
        s = _HARAKAT.sub("", s)
    s = _CITATIONS.sub("", s)
    s = s.replace("\r", "\n")
    out: list[str] = []
    for line in s.split("\n"):
        line = _SPACES.sub(" ", line).strip()
        line = re.sub(r"\s+([,.;:!?،؛])", r"\1", line)  # espace avant ponctuation (sauf fr ;:!? gardés lisibles)
        line = re.sub(r"\(\s*\)", "", line).strip()
        if len(line) < 3 or line in ("-", "##"):
            continue
        out.append(line)
    # retire les titres de section vides (titre suivi d'un autre titre ou fin)
    cleaned: list[str] = []
    for i, line in enumerate(out):
        if line.startswith("## ") and (i + 1 == len(out) or out[i + 1].startswith("## ")):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


# ----------------------------------------------------------------------------
# Langue
# ----------------------------------------------------------------------------
_FR = set("le la les des du de et est un une dans pour sur au aux par qui que avec son sa ses plus ce cette sont été".split())
_EN = set("the of and is in to was for on with as by that from at are which this an it its were be has".split())


def detect_lang(text: str) -> str:
    letters = [c for c in text[:5000] if c.isalpha()]
    if not letters:
        return "und"
    ar = sum(1 for c in letters if "؀" <= c <= "ۿ")
    if ar / len(letters) > 0.4:
        return "ar"
    words = re.findall(r"[a-zA-Zàâçéèêëîïôûùüÿœ']+", text[:5000].lower())
    fr = sum(w in _FR for w in words)
    en = sum(w in _EN for w in words)
    return "fr" if fr >= en else "en"


# ----------------------------------------------------------------------------
# Boilerplate (lignes répétées dans >= k documents d'une même source web)
# ----------------------------------------------------------------------------
def remove_boilerplate(docs: list[dict], min_docs: int = 3, min_len: int = 15) -> int:
    by_source: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        if d["source"] not in ("wikipedia", "wikivoyage", "equipe"):
            by_source[d["source"]].append(d)
    removed = 0
    for src_docs in by_source.values():
        if len(src_docs) < min_docs:
            continue
        cnt = Counter()
        for d in src_docs:
            cnt.update(set(l for l in d["text"].split("\n") if len(l) >= min_len))
        bad = {l for l, c in cnt.items() if c >= min_docs}
        for d in src_docs:
            kept = [l for l in d["text"].split("\n") if l not in bad]
            removed += d["text"].count("\n") + 1 - len(kept)
            d["text"] = "\n".join(kept)
    return removed


def clean_record(raw: dict, strip_diacritics: bool = True) -> dict:
    if raw["content_type"] == "html":
        text = mediawiki_html_to_text(raw["content"])
    elif raw["content_type"] == "pdf_text":
        # PDF : recolle les mots coupés en fin de ligne et les lignes d'un même paragraphe
        t = re.sub(r"-\n(\w)", r"\1", raw["content"])
        text = re.sub(r"(?<![.!?:])\n(?=[a-zà-ÿ])", " ", t)
    else:
        text = raw["content"]
    text = normalize_text(text, strip_diacritics=strip_diacritics)
    title = normalize_text(raw.get("title") or "", strip_diacritics=strip_diacritics).replace("\n", " ")
    title = re.sub(r"\s*[|–—-]\s*[^|–—-]{2,40}$", "", title) if raw["source"] not in ("wikipedia", "wikivoyage", "equipe") else title
    return {**{k: v for k, v in raw.items() if k != "content"}, "title": title, "text": text,
            "lang": raw.get("lang") or detect_lang(text)}
