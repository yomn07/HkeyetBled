"""Shared helpers: config, polite HTTP, robots.txt, text matching utilities."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DOCS_DIR = ROOT / "docs"

log = logging.getLogger("hkeyet")


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )


def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ----------------------------------------------------------------------------
# JSONL helpers
# ----------------------------------------------------------------------------
def write_jsonl(path: Path, records) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def short_hash(s: str, n: int = 8) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def slugify(s: str, max_len: int = 60) -> str:
    s = strip_accents(s.lower())
    s = re.sub(r"[^\w؀-ۿ]+", "-", s).strip("-")
    return s[:max_len] or "doc"


# ----------------------------------------------------------------------------
# Polite HTTP client (retries, delay per host, robots.txt)
# ----------------------------------------------------------------------------
class PoliteSession:
    def __init__(self, user_agent: str, delay: float = 1.0, timeout: int = 30, max_retries: int = 3):
        import requests

        self.requests = requests
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent, "Accept-Language": "fr,ar;q=0.8,en;q=0.6"})
        self.ua = user_agent
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}

    def _wait(self, host: str) -> None:
        last = self._last.get(host, 0.0)
        dt = time.time() - last
        if dt < self.delay:
            time.sleep(self.delay - dt)
        self._last[host] = time.time()

    def allowed(self, url: str) -> bool:
        """Respect robots.txt. Unreachable/404 robots => allowed; 401/403 => disallowed."""
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            try:
                r = self.s.get(base + "/robots.txt", timeout=self.timeout)
                if r.status_code in (401, 403):
                    rp.disallow_all = True
                elif r.status_code >= 400:
                    rp.allow_all = True
                else:
                    rp.parse(r.text.splitlines())
            except Exception as e:  # network error: be permissive but log it
                log.warning("robots.txt unreachable for %s (%s) -> assuming allowed", base, e)
                rp.allow_all = True
            self._robots[base] = rp
        return self._robots[base].can_fetch(self.ua, url)

    def get(self, url: str, params: dict | None = None, check_robots: bool = False):
        if check_robots and not self.allowed(url):
            log.warning("Blocked by robots.txt: %s", url)
            return None
        host = urlparse(url).netloc
        for attempt in range(1, self.max_retries + 1):
            self._wait(host)
            try:
                r = self.s.get(url, params=params, timeout=self.timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    wait = int(r.headers.get("Retry-After", 5 * attempt))
                    log.warning("HTTP %s on %s, retry in %ss", r.status_code, url, wait)
                    time.sleep(wait)
                    continue
                return r
            except self.requests.RequestException as e:
                log.warning("Request error %s (attempt %d/%d): %s", url, attempt, self.max_retries, e)
                time.sleep(2 * attempt)
        return None


# ----------------------------------------------------------------------------
# Text matching helpers (shared by annotation)
# ----------------------------------------------------------------------------
AR_LETTERS = "ء-يٱ-ۓ"
_AR_CHAR = re.compile(f"[{AR_LETTERS}]")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize_latin(s: str) -> str:
    """Lowercase, no accents, unified apostrophes/hyphens -> for keyword matching."""
    s = strip_accents(s.lower())
    s = s.replace("’", "'").replace("‘", "'")
    s = re.sub(r"[-‐-―]", " ", s)
    return s


def normalize_arabic_for_search(s: str) -> str:
    """Normalisation arabe agressive (pour matching / BM25) — PAS pour l'affichage.
    alef variants -> ا, ى -> ي, ة -> ه, supprime harakat/tatweel."""
    s = re.sub("[ً-ْٰـ]", "", s)
    s = re.sub("[إأآٱ]", "ا", s)
    s = s.replace("ى", "ي").replace("ة", "ه")
    return s


def is_arabic(s: str) -> bool:
    return bool(_AR_CHAR.search(s))


def latin_pattern(kw: str) -> str:
    """'medina' -> word-start prefix; 'plat ' (trailing space) -> whole word."""
    kw_n = normalize_latin(kw)
    whole = kw_n.endswith(" ")
    body = re.escape(kw_n.strip()).replace(r"\ ", r"\s+")
    return rf"\b{body}\b" if whole else rf"\b{body}"


_AR_PREFIX = r"(?:و|ف|ب|ل|ك)?(?:ال)?"
# applied on normalize_arabic_for_search() text, where ة has become ه
_AR_SUFFIX = r"(?:ات|يه|ي|ين|ون|ان|ها|ه)?"


def arabic_pattern(kw: str) -> str:
    """Token-bounded Arabic match tolerant to clitic prefixes/suffixes."""
    kw_n = normalize_arabic_for_search(kw)
    if kw_n.startswith("ال"):
        kw_n = kw_n[2:]
    body = re.escape(kw_n).replace(r"\ ", r"\s+")
    return rf"(?<![{AR_LETTERS}]){_AR_PREFIX}{body}{_AR_SUFFIX}(?![{AR_LETTERS}])"
