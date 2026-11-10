"""Déduplication en 3 niveaux (sans dépendance externe) :
1. doublons exacts (hash du texte normalisé) ;
2. quasi-doublons (MinHash + LSH sur des 5-grammes de mots, même langue) : Jaccard >= seuil,
   ou copie partielle (>= 80 % des 5-grammes d'un document présents dans un autre) ;
3. paragraphes longs déjà présents dans un document conservé (copier-coller entre sites).
On garde le document de la source la plus fiable, puis le plus long.
Les traductions FR/AR/EN d'un même article ne sont PAS des doublons (langues différentes).
"""
from __future__ import annotations

import hashlib
import random
import re
from collections import defaultdict

from .common import normalize_arabic_for_search, normalize_latin

SOURCE_PRIORITY = {"equipe": 0, "officiel": 0, "encyclopedie": 1, "guide_voyage": 2, "blog": 3}
_MAXH = (1 << 32) - 1


def _canon(text: str) -> str:
    t = normalize_arabic_for_search(normalize_latin(text))
    return re.sub(r"[\W_]+", " ", t).strip()


def _shingles(text: str, k: int = 5) -> set[int]:
    w = _canon(text).split()
    grams = [" ".join(w)] if len(w) < k else [" ".join(w[i:i + k]) for i in range(len(w) - k + 1)]
    return {int(hashlib.md5(g.encode()).hexdigest()[:8], 16) for g in grams}


class MinHasher:
    def __init__(self, num_perm: int = 64, seed: int = 13):
        rnd = random.Random(seed)
        self.p = 4294967311  # prime > 2^32
        self.ab = [(rnd.randrange(1, self.p), rnd.randrange(0, self.p)) for _ in range(num_perm)]

    def signature(self, sh: set[int]) -> tuple[int, ...]:
        return tuple(min(((a * x + b) % self.p) & _MAXH for x in sh) for a, b in self.ab)


def _rank(d: dict) -> tuple:
    return (SOURCE_PRIORITY.get(d.get("source_type"), 9), -len(d["text"]))


def deduplicate(docs: list[dict], threshold: float = 0.8, bands: int = 32, containment: float = 0.8) -> tuple[list[dict], list[dict]]:
    """Return (kept, removed) ; removed items get 'duplicate_of' and 'dup_reason'."""
    docs = sorted(docs, key=_rank)  # le meilleur candidat d'abord
    removed: list[dict] = []

    # 1) exact
    seen: dict[str, str] = {}
    stage1 = []
    for d in docs:
        h = hashlib.sha1(_canon(d["text"]).encode()).hexdigest()
        if h in seen:
            removed.append({**d, "duplicate_of": seen[h], "dup_reason": "exact"})
        else:
            seen[h] = d["id"]
            stage1.append(d)

    # 2) near-duplicates
    mh = MinHasher(num_perm=64)
    rows = 64 // bands
    buckets: dict[tuple, list[int]] = defaultdict(list)
    shingles, kept = [], []
    for d in stage1:
        sh = _shingles(d["text"])
        sig = mh.signature(sh)
        cands = set()
        for b in range(bands):
            key = (d["lang"], b, sig[b * rows:(b + 1) * rows])
            cands.update(buckets.get(key, []))
        dup_of = None
        for j in cands:
            inter = len(sh & shingles[j])
            jac = inter / max(1, len(sh | shingles[j]))
            cont = inter / max(1, len(sh))  # part de CE document déjà présente ailleurs
            if jac >= threshold or cont >= containment:
                dup_of = kept[j]["id"]
                reason = f"near (Jaccard={jac:.2f})" if jac >= threshold else f"copie partielle ({cont:.0%} contenu)"
                break
        if dup_of:
            removed.append({**d, "duplicate_of": dup_of, "dup_reason": reason})
            continue
        idx = len(kept)
        kept.append(d)
        shingles.append(sh)
        for b in range(bands):
            buckets[(d["lang"], b, sig[b * rows:(b + 1) * rows])].append(idx)

    # 3) long paragraphs already seen elsewhere
    seen_par: set[str] = set()
    n_par = 0
    for d in kept:
        out = []
        for line in d["text"].split("\n"):
            key = _canon(line)
            if len(key) >= 120 and not line.startswith("## "):
                if key in seen_par:
                    n_par += 1
                    continue
                seen_par.add(key)
            out.append(line)
        d["text"] = "\n".join(out)
    deduplicate.paragraphs_removed = n_par  # type: ignore[attr-defined]
    return kept, removed
