"""Collecte Wikipédia (FR/AR/EN) et Wikivoyage via l'API MediaWiki officielle.

Pas de scraping HTML des pages : on passe par api.php (recommandé par Wikimedia),
avec User-Agent identifiable, pause entre requêtes et reprise sur cache.
Sortie : data/raw/wikipedia.jsonl et data/raw/wikivoyage.jsonl (HTML brut + métadonnées).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import quote

from .common import RAW_DIR, PoliteSession, log, read_jsonl


def _api(project: str, lang: str) -> str:
    return f"https://{lang}.{project}.org/w/api.php"


def _similar(asked: str, found: str) -> bool:
    """Accept a search fallback only if it is plausibly the same page
    ('Le Kef' -> 'El Kef' OK ; 'Nefta' -> 'Tozeur' rejected)."""
    from difflib import SequenceMatcher

    from .common import normalize_latin

    a, f = normalize_latin(asked).strip(), normalize_latin(found).strip()
    return a in f or f in a or SequenceMatcher(None, a, f).ratio() >= 0.6


def _page_url(project: str, lang: str, title: str) -> str:
    return f"https://{lang}.{project}.org/wiki/{quote(title.replace(' ', '_'))}"


class MediaWikiCollector:
    def __init__(self, session: PoliteSession, project: str, out_name: str, meta: dict):
        self.http = session
        self.project = project  # "wikipedia" | "wikivoyage"
        self.out_path = RAW_DIR / f"{out_name}.jsonl"
        self.meta = meta
        self.seen: set[tuple[str, str]] = {(r["lang"], r["title"]) for r in read_jsonl(self.out_path)}
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.out_path, "a", encoding="utf-8")
        self.n_new = 0
        self.missing: list[str] = []

    def close(self):
        self._fh.close()

    # -- API calls ------------------------------------------------------------
    def _call(self, lang: str, **params) -> dict | None:
        params = {"format": "json", "formatversion": 2, "maxlag": 5, **params}
        r = self.http.get(_api(self.project, lang), params=params)
        if r is None or r.status_code != 200:
            log.warning("API failure %s/%s %s", self.project, lang, params.get("titles") or params.get("page"))
            return None
        try:
            return r.json()
        except json.JSONDecodeError:
            return None

    def resolve(self, lang: str, title: str, _depth: int = 0) -> dict | None:
        """Resolve redirects, skip disambiguation, get langlinks. Falls back to search."""
        d = self._call(lang, action="query", titles=title, redirects=1,
                       prop="langlinks|pageprops|info", lllimit="max", ppprop="disambiguation")
        page = (d or {}).get("query", {}).get("pages", [{}])[0]
        if not page or page.get("missing") or page.get("invalid"):
            s = self._call(lang, action="query", list="search", srsearch=title, srlimit=1, srnamespace=0)
            hits = (s or {}).get("query", {}).get("search", [])
            if not hits:
                return None
            if not _similar(title, hits[0]["title"]):
                log.info("  '%s' introuvable (résultat de recherche '%s' rejeté : trop différent)", title, hits[0]["title"])
                return None
            log.info("  '%s' introuvable -> meilleur résultat de recherche : '%s'", title, hits[0]["title"])
            return self.resolve(lang, hits[0]["title"], _depth + 1) if hits[0]["title"] != title and _depth < 2 else None
        if "disambiguation" in page.get("pageprops", {}):
            alt = self._tunisian_meaning(lang, page["title"])
            if alt:
                log.info("  '%s' est une page d'homonymie -> sens tunisien : '%s'", page["title"], alt)
                return self.resolve(lang, alt, _depth=1) if _depth == 0 else None
            log.info("  '%s' est une page d'homonymie -> ignorée", page["title"])
            return None
        return page

    def _tunisian_meaning(self, lang: str, title: str) -> str | None:
        """Sur une page d'homonymie, cherche la page « Titre (…) » liée à la Tunisie."""
        from .common import normalize_latin

        country = {"fr": "Tunisie", "en": "Tunisia", "ar": "تونس"}.get(lang, "Tunisie")
        s = self._call(lang, action="query", list="search", srsearch=f'intitle:"{title}" {country}',
                       srlimit=5, srnamespace=0)
        base = normalize_latin(title).strip()
        for h in (s or {}).get("query", {}).get("search", []):
            t = h["title"]
            if re.search(r"homonymie|disambiguation|توضيح", t, re.I):
                continue
            if t != title and normalize_latin(t).startswith(base):
                return t
        return None

    def fetch(self, lang: str, title: str, theme_hint: str | None, group_key: str) -> bool:
        if (lang, title) in self.seen:
            return False
        d = self._call(lang, action="parse", page=title, redirects=1,
                       prop="text|revid|categories|displaytitle", disableeditsection=1, disabletoc=1)
        p = (d or {}).get("parse")
        if not p:
            self.missing.append(f"{lang}:{title}")
            return False
        real_title = p["title"]
        if (lang, real_title) in self.seen:
            return False
        rec = {
            "source": self.project,
            "source_type": self.meta["source_type"],
            "lang": lang,
            "title": real_title,
            "url": _page_url(self.project, lang, real_title),
            "pageid": p.get("pageid"),
            "revid": p.get("revid"),
            "categories": [c.get("category", "").replace("_", " ") for c in p.get("categories", []) if not c.get("hidden")],
            "content_type": "html",
            "content": p.get("text", ""),
            "license": self.meta["license"],
            "redistributable": self.meta["redistributable"],
            "theme_hint": theme_hint,
            "group_key": group_key,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._fh.flush()
        self.seen.add((lang, title))
        self.seen.add((lang, real_title))
        self.n_new += 1
        return True

    def category_members(self, lang: str, category: str, limit: int) -> list[str]:
        d = self._call(lang, action="query", list="categorymembers", cmtitle=category,
                       cmtype="page", cmnamespace=0, cmlimit=min(limit, 500))
        members = (d or {}).get("query", {}).get("categorymembers", [])
        if not members:
            log.warning("  Catégorie vide ou inexistante : %s:%s", lang, category)
        return [m["title"] for m in members][:limit]


def collect_wikipedia(cfg: dict, session: PoliteSession, langs: list[str], limit: int | None = None) -> None:
    wp = cfg["wikipedia"]
    pivot = wp["pivot_lang"]
    extra = [l for l in wp.get("follow_langlinks", []) if l in langs]
    c = MediaWikiCollector(session, "wikipedia", "wikipedia", wp)
    try:
        n_seeds = 0
        for theme, titles in wp["seeds"].items():
            hint = None if theme == "villes" else theme
            log.info("Wikipédia – thème %s (%d titres)", theme, len(titles))
            for t in titles:
                if limit and n_seeds >= limit:
                    break
                n_seeds += 1
                page = c.resolve(pivot, t)
                if not page:
                    c.missing.append(f"{pivot}:{t}")
                    continue
                group = f"wp:{page['title']}"
                if pivot in langs:
                    c.fetch(pivot, page["title"], hint, group)
                for ll in page.get("langlinks", []):
                    if ll["lang"] in extra:
                        c.fetch(ll["lang"], ll["title"], hint, group)

        # Amorces directement dans une autre langue (article sans équivalent FR)
        for lang, by_theme in (wp.get("extra_seeds") or {}).items():
            if lang not in langs:
                continue
            for theme, titles in by_theme.items():
                for t in titles[: limit or None]:
                    page = c.resolve(lang, t)
                    if not page:
                        c.missing.append(f"{lang}:{t}")
                        continue
                    group = f"wp:{lang}:{page['title']}"
                    c.fetch(lang, page["title"], theme, group)
                    for ll in page.get("langlinks", []):
                        if ll["lang"] in langs and ll["lang"] != lang:
                            c.fetch(ll["lang"], ll["title"], theme, group)

        for lang, cats in (wp.get("categories") or {}).items():
            if lang not in langs:
                continue
            for cat in cats:
                cat, _, n = cat.partition("|")  # "Catégorie:X|30" = plafond propre à la catégorie
                cap = int(n) if n.strip().isdigit() else wp.get("max_per_category", 60)
                members = c.category_members(lang, cat.strip(), limit or cap)
                log.info("Catégorie %s:%s -> %d pages", lang, cat, len(members))
                for t in members:
                    c.fetch(lang, t, None, f"wp:{lang}:{t}")
    finally:
        c.close()
    log.info("Wikipédia : %d nouvelles pages, %d introuvables", c.n_new, len(c.missing))
    if c.missing:
        (RAW_DIR / "wikipedia_missing.txt").write_text("\n".join(c.missing), encoding="utf-8")


def collect_wikivoyage(cfg: dict, session: PoliteSession, langs: list[str], limit: int | None = None) -> None:
    wv = cfg["wikivoyage"]
    c = MediaWikiCollector(session, "wikivoyage", "wikivoyage", wv)
    en_titles = wv.get("en_titles", {}) or {}
    try:
        for i, t in enumerate(wv["pages"]):
            if limit and i >= limit:
                break
            for lang in wv["langs"]:
                if lang not in langs:
                    continue
                title = en_titles.get(t, t) if lang == "en" else t
                page = c.resolve(lang, title)
                if page:
                    c.fetch(lang, page["title"], None, f"wv:{t}")
                else:
                    c.missing.append(f"{lang}:{title}")
    finally:
        c.close()
    log.info("Wikivoyage : %d nouvelles pages, %d introuvables", c.n_new, len(c.missing))