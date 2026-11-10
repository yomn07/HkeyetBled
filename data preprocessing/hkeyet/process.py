"""Étape 'process' : raw -> nettoyé -> dédupliqué -> annoté -> JSONL final."""
from __future__ import annotations

from .annotate import Annotator
from .clean import clean_record, remove_boilerplate
import re

from .common import CONFIG_DIR, DATA_DIR, RAW_DIR, load_yaml, log, read_jsonl, short_hash, slugify, write_jsonl
from .dedup import deduplicate

MIN_WORDS = {"ar": 60, "fr": 80, "en": 80}

FIELD_ORDER = [
    "id", "title", "lang", "text", "url", "source", "source_type", "license", "redistributable",
    "region", "region_ar", "region_macro", "regions", "theme", "themes", "group_id",
    "categories", "n_words", "n_chars", "revid", "retrieved_at", "annotation",
]


def _ordered(d: dict) -> dict:
    return {k: d.get(k) for k in FIELD_ORDER}


def run_process(strip_diacritics: bool = True, dedup_threshold: float = 0.8) -> dict:
    raws = []
    for name in ("manual", "wikipedia", "wikivoyage", "web"):
        recs = read_jsonl(RAW_DIR / f"{name}.jsonl")
        log.info("raw/%s.jsonl : %d enregistrements", name, len(recs))
        raws += recs
    if not raws:
        raise SystemExit("Aucune donnée brute : lancez d'abord `python run_pipeline.py collect`.")

    # Pages à exclure (titre exact ou URL), une par ligne dans config/exclude.txt
    excl_path = CONFIG_DIR / "exclude.txt"
    exclude = set()
    if excl_path.exists():
        exclude = {l.strip() for l in excl_path.read_text(encoding="utf-8").splitlines()
                   if l.strip() and not l.startswith("#")}

    rejected: list[dict] = []
    docs: list[dict] = []
    for r in raws:
        if r.get("title") in exclude or r.get("url") in exclude:
            rejected.append({"id": None, "title": r.get("title"), "url": r.get("url"), "reason": "exclu manuellement"})
            continue
        d = clean_record(r, strip_diacritics=strip_diacritics)
        d["id"] = f"{d['source']}_{d['lang']}_{slugify(d['title'], 40)}_{short_hash(d['url'], 6)}"
        d["group_id"] = "g_" + short_hash(r.get("group_key") or d["url"], 10)
        docs.append(d)

    n_bp = remove_boilerplate(docs)
    log.info("Boilerplate : %d lignes répétées supprimées", n_bp)

    kept = []
    for d in docs:
        nw = len(d["text"].split())
        if nw < MIN_WORDS.get(d["lang"], 80):
            rejected.append({"id": d["id"], "title": d["title"], "url": d["url"], "reason": f"trop court ({nw} mots)"})
        else:
            kept.append(d)

    kept, dups = deduplicate(kept, threshold=dedup_threshold)
    for d in dups:
        rejected.append({"id": d["id"], "title": d["title"], "url": d["url"],
                         "reason": f"doublon {d['dup_reason']} de {d['duplicate_of']}"})
    log.info("Dédup : %d doublons retirés, %d paragraphes répétés supprimés",
             len(dups), getattr(deduplicate, "paragraphs_removed", 0))

    ann = Annotator()
    filters = load_yaml("filters.yaml") if (CONFIG_DIR / "filters.yaml").exists() else {}
    pats = [re.escape(p) for p in filters.get("offtopic_patterns") or []]
    offtopic = re.compile("|".join(pats), re.I) if pats else None
    drop_autre = filters.get("drop_theme_autre", False)
    final = []
    for d in kept:
        a = ann.annotate(d)
        if not a.pop("_relevant"):
            rejected.append({"id": a["id"], "title": a["title"], "url": a["url"], "reason": "hors sujet (aucune mention de la Tunisie)"})
            continue
        if a["source"] != "equipe" and a["annotation"] != "manuelle":
            where = a["title"] + " | " + " | ".join(a.get("categories") or [])
            m = offtopic.search(where) if offtopic else None
            if m:
                rejected.append({"id": a["id"], "title": a["title"], "url": a["url"],
                                 "reason": f"hors sujet (filtre : {m.group(0).strip()})"})
                continue
            if drop_autre and a["theme"] == "autre":
                rejected.append({"id": a["id"], "title": a["title"], "url": a["url"],
                                 "reason": "hors sujet (aucun thème patrimonial)"})
                continue
        a["n_words"] = len(a["text"].split())
        a["n_chars"] = len(a["text"])
        final.append(_ordered(a))

    final.sort(key=lambda d: (d["theme"], d["region"], d["lang"], d["title"]))
    write_jsonl(DATA_DIR / "corpus.jsonl", final)
    # Version publique : texte complet seulement si la licence le permet, sinon lien + métadonnées
    public = [d if d["redistributable"] else {**d, "text": None} for d in final]
    write_jsonl(DATA_DIR / "corpus_public.jsonl", public)
    write_jsonl(DATA_DIR / "rejected.jsonl", rejected)
    log.info("Corpus final : %d documents (rejetés : %d) -> data/corpus.jsonl", len(final), len(rejected))
    return {"n_raw": len(raws), "n_final": len(final), "n_rejected": len(rejected),
            "n_dups": len(dups), "n_boilerplate_lines": n_bp, "strip_diacritics": strip_diacritics,
            "dedup_threshold": dedup_threshold}