"""Fiches rédigées par l'équipe (config/manual/*.md) -> data/raw/manual.jsonl.

Format d'une fiche : un en-tête YAML entre deux lignes '---', puis le texte en Markdown.
    ---
    title: Expressions tunisiennes courantes
    lang: fr
    theme: langue_savoir_vivre      # optionnel (indice de thème)
    authors: [Membre 1]
    verified: true                  # mettre true après relecture par l'équipe
    ---
    ## Salutations
    ...
Seules les fiches `verified: true` entrent dans le corpus (évite d'indexer un brouillon).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import yaml

from .common import CONFIG_DIR, RAW_DIR, log


def collect_manual(cfg: dict) -> None:
    meta = cfg.get("manual") or {}
    folder = CONFIG_DIR / "manual"
    out = RAW_DIR / "manual.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    recs, skipped = [], []
    for f in sorted(folder.glob("*.md")) if folder.exists() else []:
        raw = f.read_text(encoding="utf-8")
        head, body = {}, raw
        if raw.startswith("---"):
            _, fm, body = raw.split("---", 2)
            head = yaml.safe_load(fm) or {}
        if not head.get("verified"):
            skipped.append(f.name)
            continue
        recs.append({
            "source": "equipe",
            "source_type": meta.get("source_type", "equipe"),
            "lang": head.get("lang"),
            "title": head.get("title", f.stem),
            "url": f"config/manual/{f.name}",
            "content_type": "text",
            "content": body.strip(),
            "license": meta.get("license", "rédigé par l'équipe"),
            "redistributable": meta.get("redistributable", True),
            "theme_hint": head.get("theme"),
            "group_key": f"manual:{f.stem}",
            "categories": [],
            "authors": head.get("authors", []),
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    # rewritten each time: the files are the source of truth
    with open(out, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    log.info("Fiches équipe : %d intégrées, %d non vérifiées ignorées %s", len(recs), len(skipped), skipped or "")
