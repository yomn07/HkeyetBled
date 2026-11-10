"""Annotation automatique : région (gouvernorat + macro-région) et thème(s).

Méthode transparente (explicable à la soutenance) :
- Région : gazetteer des 24 gouvernorats (villes, sites, FR/AR). Score = 8 x occurrences
  dans le titre + 2 x dans les catégories + occurrences dans le texte (plafonnées).
  Si aucun gouvernorat ne domine -> "National".
- Thème : lexique FR/EN/AR par thème. Score = 8 x titre + 2 x catégories
  + densité (occurrences pour 1000 mots) + bonus si la source fournit un indice de thème.
- Corrections manuelles possibles dans config/overrides.csv (id,region,theme).
"""
from __future__ import annotations

import csv
import re
from collections import Counter

from .common import (CONFIG_DIR, arabic_pattern, latin_pattern, load_yaml,
                     normalize_arabic_for_search, normalize_latin)

NATIONAL = "National"
_TUNISIA = re.compile(r"\btunisi|\btunes\b", re.I)
_TUNISIA_AR = re.compile(arabic_pattern("تونس"))


def _compile(latin: list[str], arabic: list[str], whole_words: bool = False):
    if whole_words:  # noms de lieux : "Tunis" ne doit pas matcher "tunisienne"
        latin = [k.strip() + " " for k in latin]
    lat = re.compile("|".join(latin_pattern(k) for k in latin)) if latin else None
    ara = re.compile("|".join(arabic_pattern(k) for k in arabic)) if arabic else None
    return lat, ara


def _count(rx_pair, lat_text: str, ar_text: str) -> int:
    lat, ara = rx_pair
    n = 0
    if lat is not None and lat_text:
        n += len(lat.findall(lat_text))
    if ara is not None and ar_text:
        n += len(ara.findall(ar_text))
    return n


class Annotator:
    def __init__(self):
        self.regions = load_yaml("regions.yaml")
        self.themes = load_yaml("themes.yaml")
        self.region_rx = {
            g: _compile([g] + v.get("aliases_fr", []), [v["ar"]] + v.get("aliases_ar", []), whole_words=True)
            for g, v in self.regions.items()
        }
        self.theme_rx = {t: _compile(v.get("latin", []), v.get("arabic", [])) for t, v in self.themes.items()}
        self.overrides = self._load_overrides()

    @staticmethod
    def _load_overrides() -> dict[str, dict]:
        p = CONFIG_DIR / "overrides.csv"
        if not p.exists():
            return {}
        with open(p, encoding="utf-8") as f:
            return {r["id"]: r for r in csv.DictReader(f) if r.get("id") and not r["id"].startswith("#")}

    @staticmethod
    def _views(s: str) -> tuple[str, str]:
        return normalize_latin(s), normalize_arabic_for_search(s)

    def is_relevant(self, doc: dict, region_scores: Counter) -> bool:
        head = doc["title"] + "\n" + doc["text"][:20000]
        return bool(_TUNISIA.search(normalize_latin(head)) or
                    _TUNISIA_AR.search(normalize_arabic_for_search(head)) or
                    sum(region_scores.values()) >= 2)

    def annotate(self, doc: dict) -> dict:
        title_l, title_a = self._views(doc["title"])
        cats = " | ".join(doc.get("categories") or [])
        cat_l, cat_a = self._views(cats)
        text_l, text_a = self._views(doc["text"])
        n_words = max(len(doc["text"].split()), 1)

        # ---- région
        rs: Counter = Counter()
        title_hits = []
        for g, rx in self.region_rx.items():
            t = _count(rx, title_l, title_a)
            s = 8 * t + 2 * _count(rx, cat_l, cat_a) + min(_count(rx, text_l, text_a), 30)
            if s:
                rs[g] = s
            if t:
                title_hits.append(g)
        title_hit = max(title_hits, key=lambda g: rs[g]) if title_hits else None
        total = sum(rs.values())
        top, top_s = (rs.most_common(1)[0] if rs else (None, 0))
        if title_hit:
            region = title_hit
        elif top and top_s >= 3 and top_s / total >= 0.35:
            region = top
        else:
            region = NATIONAL
        regions = [g for g, s in rs.most_common(5) if s >= max(2, 0.25 * top_s)]

        # ---- thème
        ts: dict[str, float] = {}
        for th, rx in self.theme_rx.items():
            dens = 1000 * _count(rx, text_l, text_a) / max(n_words, 300)
            ts[th] = 8 * _count(rx, title_l, title_a) + 2 * _count(rx, cat_l, cat_a) + dens
        if doc.get("theme_hint") in ts:
            ts[doc["theme_hint"]] += max(10.0, 0.5 * max(ts.values()))
        ranked = sorted(ts.items(), key=lambda kv: -kv[1])
        theme = ranked[0][0] if ranked[0][1] > 0 else "autre"
        themes = [t for t, s in ranked[:3] if s > 0 and s >= 0.5 * ranked[0][1]]

        out = {
            **doc,
            "region": region,
            "region_ar": self.regions[region]["ar"] if region in self.regions else "وطني",
            "region_macro": self.regions[region]["macro"] if region in self.regions else NATIONAL,
            "regions": regions,
            "theme": theme,
            "themes": themes or [theme],
            "annotation": "auto",
            "_relevant": self.is_relevant(doc, rs),
        }
        ov = self.overrides.get(doc["id"])
        if ov:
            if ov.get("region"):
                r = ov["region"]
                out.update(region=r, region_ar=self.regions.get(r, {}).get("ar", "وطني"),
                           region_macro=self.regions.get(r, {}).get("macro", NATIONAL))
            if ov.get("theme"):
                out["theme"] = ov["theme"]
                if ov["theme"] not in out["themes"]:
                    out["themes"] = [ov["theme"]] + out["themes"][:2]
            out["annotation"] = "manuelle"
            out["_relevant"] = True
        return out

    def theme_label(self, t: str) -> str:
        return self.themes.get(t, {}).get("label", t)
