"""Collecte des sites web (UNESCO, INP, ONTT, blogs) : robots.txt respecté,
extraction du contenu principal (trafilatura si dispo, sinon BeautifulSoup),
et texte des brochures PDF (pypdf). Sortie : data/raw/web.jsonl
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .common import RAW_DIR, PoliteSession, log, read_jsonl

try:
    import trafilatura  # type: ignore
except ImportError:  # pragma: no cover
    trafilatura = None


def html_to_main_text(html: str, url: str = "") -> tuple[str, str]:
    """Return (title, main_text). Keeps headings as '## ' lines."""
    soup = BeautifulSoup(html, "lxml")
    title = ""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    if trafilatura is not None:
        txt = trafilatura.extract(html, url=url, include_comments=False, include_tables=False,
                                  include_formatting=True, favor_precision=True)
        if txt and len(txt.split()) > 50:
            # trafilatura's markdown headings -> our convention
            txt = re.sub(r"^#+\s*", "## ", txt, flags=re.M)
            return title, txt

    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe", "svg"]):
        tag.decompose()
    for sel in ['[class*="menu"]', '[class*="cookie"]', '[class*="share"]', '[class*="breadcrumb"]',
                '[id*="sidebar"]', '[class*="sidebar"]', '[class*="related"]', '[class*="comment"]']:
        for t in soup.select(sel):
            t.decompose()
    root = soup.find("article") or soup.find("main") or soup.find(id=re.compile("content|main", re.I)) or soup.body or soup
    lines = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote"]):
        t = el.get_text(" ", strip=True)
        if not t:
            continue
        lines.append(f"## {t}" if el.name in ("h1", "h2", "h3", "h4") else t)
    return title, "\n".join(lines)


def pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # some brochure pages are images only
            pages.append("")
    return "\n\n".join(pages)


def _discover_links(session: PoliteSession, crawl: dict) -> list[str]:
    inc = re.compile(crawl["link_pattern"])
    exc = re.compile(crawl["exclude_pattern"]) if crawl.get("exclude_pattern") else None
    found: list[str] = []
    for start in crawl["start_urls"]:
        r = session.get(start, check_robots=True)
        if r is None or r.status_code != 200:
            log.warning("  page de départ inaccessible : %s", start)
            continue
        soup = BeautifulSoup(r.text, "lxml")
        host = urlparse(start).netloc
        for a in soup.find_all("a", href=True):
            u = urljoin(start, a["href"]).split("#")[0]
            if urlparse(u).netloc != host or not inc.search(u) or (exc and exc.search(u)):
                continue
            if u not in found and u not in crawl["start_urls"]:
                found.append(u)
    return found[: crawl.get("max_pages", 50)]


def collect_web(cfg: dict, session: PoliteSession, only: list[str] | None = None, limit: int | None = None) -> None:
    out = RAW_DIR / "web.jsonl"
    seen = {r["url"] for r in read_jsonl(out)}
    out.parent.mkdir(parents=True, exist_ok=True)
    n_new, failures = 0, []
    with open(out, "a", encoding="utf-8") as fh:
        for src in cfg.get("web", []):
            if only and src["name"] not in only:
                continue
            urls = list(src.get("urls") or [])
            if src.get("crawl"):
                urls += _discover_links(session, src["crawl"])
            if limit:
                urls = urls[:limit]
            log.info("Web – %s : %d URL", src["name"], len(urls))
            for url in urls:
                if url in seen:
                    continue
                r = session.get(url, check_robots=True)
                if r is None or r.status_code != 200:
                    failures.append(f"{src['name']}\t{url}\t{getattr(r, 'status_code', 'robots/erreur')}")
                    continue
                ctype = r.headers.get("Content-Type", "")
                if "pdf" in ctype or url.lower().endswith(".pdf"):
                    title, text = url.rsplit("/", 1)[-1].replace(".pdf", "").replace("_", " "), pdf_to_text(r.content)
                    content_type = "pdf_text"
                else:
                    r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
                    title, text = html_to_main_text(r.text, url)
                    content_type = "text"
                if len(text.split()) < 40:
                    failures.append(f"{src['name']}\t{url}\ttexte trop court")
                    continue
                rec = {
                    "source": src["name"],
                    "source_type": src["source_type"],
                    "lang": None,  # détectée au nettoyage
                    "title": title or url,
                    "url": url,
                    "content_type": content_type,
                    "content": text,
                    "license": src["license"],
                    "redistributable": src.get("redistributable", False),
                    "theme_hint": src.get("theme_hint"),
                    "group_key": f"web:{url}",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                seen.add(url)
                n_new += 1
    log.info("Web : %d nouvelles pages, %d échecs", n_new, len(failures))
    if failures:
        (RAW_DIR / "web_failures.tsv").write_text("\n".join(failures), encoding="utf-8")
