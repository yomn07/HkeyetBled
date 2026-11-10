#!/usr/bin/env python3
"""Hkeyet Bled RAG — Lot 1 : corpus et collecte.

Exemples :
  python run_pipeline.py all                      # collecte + traitement + fiche de corpus
  python run_pipeline.py collect --limit 5        # test rapide (5 titres par source)
  python run_pipeline.py collect --only wikipedia wikivoyage
  python run_pipeline.py process report           # relancer après avoir modifié overrides.csv
"""
from __future__ import annotations

import argparse
import json

from hkeyet.common import DATA_DIR, PoliteSession, load_yaml, log, setup_logging


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("steps", nargs="+", choices=["collect", "process", "report", "all"])
    ap.add_argument("--only", nargs="*", default=None,
                    help="sources à collecter : equipe wikipedia wikivoyage unesco_whc inp ontt blogs")
    ap.add_argument("--langs", default="fr,ar,en", help="langues (défaut fr,ar,en)")
    ap.add_argument("--limit", type=int, default=None, help="limite par source (test rapide)")
    ap.add_argument("--keep-diacritics", action="store_true", help="conserver les harakat arabes")
    ap.add_argument("--dedup-threshold", type=float, default=0.8)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    setup_logging(a.verbose)

    steps = {"collect", "process", "report"} if "all" in a.steps else set(a.steps)
    langs = [l.strip() for l in a.langs.split(",") if l.strip()]
    cfg = load_yaml("sources.yaml")

    if "collect" in steps:
        from hkeyet.collect_mediawiki import collect_wikipedia, collect_wikivoyage
        from hkeyet.collect_manual import collect_manual
        from hkeyet.collect_web import collect_web

        h = cfg["http"]
        if "votre.email@exemple.tn" in h["user_agent"]:
            log.warning("Pensez à mettre un vrai contact dans config/sources.yaml > http.user_agent (règle Wikimedia).")
        sess = PoliteSession(h["user_agent"], h["delay_seconds"], h["timeout"], h["max_retries"])
        only = set(a.only) if a.only else None
        if not only or "equipe" in only:
            collect_manual(cfg)
        if not only or "wikipedia" in only:
            collect_wikipedia(cfg, sess, langs, a.limit)
        if not only or "wikivoyage" in only:
            collect_wikivoyage(cfg, sess, langs, a.limit)
        web_names = [s["name"] for s in cfg.get("web", [])]
        web_only = [n for n in web_names if not only or n in only]
        if web_only:
            collect_web(cfg, sess, web_only, a.limit)

    stats = None
    if "process" in steps:
        from hkeyet.process import run_process

        stats = run_process(strip_diacritics=not a.keep_diacritics, dedup_threshold=a.dedup_threshold)
        (DATA_DIR / "process_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    if "report" in steps:
        from hkeyet.report import run_report

        if stats is None and (DATA_DIR / "process_stats.json").exists():
            stats = json.loads((DATA_DIR / "process_stats.json").read_text())
        run_report(stats)


if __name__ == "__main__":
    main()
