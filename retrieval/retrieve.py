"""
Hkeyet Bled RAG — Lot 3 : Retrieval
===================================
Rôle : à partir d'une question, renvoyer les chunks les plus utiles au Lot 4 (génération).

Trois façons de chercher, combinables :
  - dense  : recherche par le SENS (vecteurs du Lot 2, similarité cosinus) ;
  - bm25   : recherche par les MOTS exacts (noms propres : « Kerkouane », « couscous ») ;
  - hybrid : les deux, fusionnées par RRF (Reciprocal Rank Fusion). Mode par défaut.
Options : filtres région / thème / langue (avec repli automatique si trop peu de résultats),
          reranker (cross-encoder), limite de chunks par article (évite les doublons de traduction).

Utilisation depuis le Lot 4 :
    from retrieval.retrieve import retrieve, to_context
    passages = retrieve("Que goûter à Sfax ?", region="Sfax", k=5)
    contexte = to_context(passages)

Utilisation en ligne de commande (depuis la racine du dépôt) :
    python retrieval/retrieve.py "Où voir un amphithéâtre romain ?" --model e5
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
INDEX_ROOT = HERE.parent / "indexation" / "index"

# --------------------------------------------------------------------------- texte
AR_MARKS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u0640]")  # harakat, tatweel
AR_MAP = str.maketrans({"ى": "ي", "ة": "ه"})
TOKEN = re.compile(r"\w+", re.UNICODE)
STOP = set("""
le la les l un une des de du d et en au aux a à est sont que qui quoi quel quelle quels quelles ou où dans sur
par pour avec sans ce cet cette ces se sa son ses il elle ils on y ne pas plus the of and in on at to is are
what which who where how for with from by an as it its that this these there
في من على الى إلى عن مع هذا هذه التي الذي ما ماذا اين أين كيف هل
""".split())


def normalize(text):
    """Minuscules, sans accents latins, sans voyelles brèves arabes, alef/ya/ta marbuta unifiés."""
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = AR_MARKS.sub("", t)
    t = t.translate(AR_MAP)
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def tokenize(text):
    toks = []
    for w in TOKEN.findall(normalize(text)):
        if w.startswith("ال") and len(w) > 4:  # article arabe « al- »
            w = w[2:]
        if len(w) >= 2 and w not in STOP:
            toks.append(w)
    return toks


# --------------------------------------------------------------------------- fusion
def rrf_fuse(rankings, weights=None, k=60):
    """Reciprocal Rank Fusion : score(d) = somme des poids / (k + rang). Rangs commencent à 1."""
    weights = weights or [1.0] * len(rankings)
    fused = {}
    for ranking, w in zip(rankings, weights):
        for rank, idx in enumerate(ranking, start=1):
            fused[idx] = fused.get(idx, 0.0) + w / (k + rank)
    return sorted(fused, key=fused.get, reverse=True), fused


def top_indices(scores, n):
    """Indices des n meilleurs scores finis, du meilleur au moins bon."""
    n = min(n, int(np.isfinite(scores).sum()))
    if n <= 0:
        return []
    part = np.argpartition(-scores, n - 1)[:n]
    return [int(i) for i in part[np.argsort(-scores[part])]]


# --------------------------------------------------------------------------- Retriever
class Retriever:
    def __init__(self, chunks, vectors=None, encode=None, reranker_name="BAAI/bge-reranker-v2-m3"):
        """chunks : liste de dicts (ligne i de chunks.jsonl) ; vectors : matrice (n, dim) normalisée ;
        encode : fonction question -> vecteur normalisé. Sans vectors/encode, seul BM25 est disponible."""
        self.chunks = chunks
        self.vectors = vectors
        self.encode = encode
        self.reranker_name = reranker_name
        self._reranker = None
        self._bm25 = None
        # métadonnées normalisées une fois pour toutes (filtres rapides)
        self._regions = [self._region_set(c) for c in chunks]
        self._themes = [set([c.get("theme")] + list(c.get("themes") or [])) - {None} for c in chunks]

    # ---- construction
    @classmethod
    def from_chunks(cls, model_key="e5"):
        """BM25 seul : ne nécessite ni FAISS ni modèle."""
        return cls(load_chunks(INDEX_ROOT / model_key / "chunks.jsonl"))

    @classmethod
    def from_index(cls, model_key="e5"):
        """Recherche dense + BM25 : charge l'index du Lot 2 (FAISS) et le modèle d'embeddings."""
        import faiss
        from sentence_transformers import SentenceTransformer

        d = INDEX_ROOT / model_key
        config = json.loads((d / "config.json").read_text(encoding="utf-8"))
        index = faiss.read_index(str(d / "index.faiss"))
        vectors = index.reconstruct_n(0, index.ntotal).astype("float32")  # IndexFlatIP : exact
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
        model = SentenceTransformer(config["model_name"], device=device)
        prefix = config.get("query_prefix", "")

        def encode(q):
            return model.encode([prefix + q], normalize_embeddings=True)[0].astype("float32")

        return cls(load_chunks(d / "chunks.jsonl"), vectors, encode)

    # ---- filtres
    @staticmethod
    def _region_set(c):
        vals = [c.get("region"), c.get("region_ar")] + list(c.get("regions") or [])
        return {normalize(v) for v in vals if v}

    def _mask(self, region, theme, lang, include_national):
        n = len(self.chunks)
        mask = np.ones(n, dtype=bool)
        if region:
            r = normalize(region)
            ok = [(r in rs) or (include_national and "national" in rs) for rs in self._regions]
            mask &= np.array(ok)
        if theme:
            mask &= np.array([theme in ts for ts in self._themes])
        if lang:
            mask &= np.array([c.get("lang") == lang for c in self.chunks])
        return mask

    # ---- scores
    def _dense_scores(self, question, mask):
        if self.vectors is None or self.encode is None:
            raise RuntimeError("Recherche dense indisponible : utilisez Retriever.from_index().")
        s = self.vectors @ self.encode(question)
        s = s.astype("float64")
        s[~mask] = -np.inf
        return s

    def _bm25_scores(self, question, mask):
        if self._bm25 is None:
            from rank_bm25 import BM25Okapi
            docs = [tokenize(f"{c.get('title','')} {c.get('title','')} {c.get('section','')} {c['text']}")
                    for c in self.chunks]  # le titre compte double : il nomme le sujet
            self._bm25 = BM25Okapi(docs)
        q = tokenize(question)
        s = np.array(self._bm25.get_scores(q), dtype="float64") if q else np.zeros(len(self.chunks))
        s[s <= 0] = -np.inf  # aucun mot en commun : pas un résultat BM25
        s[~mask] = -np.inf
        return s

    def _rerank(self, question, idxs):
        if self._reranker is None:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder(self.reranker_name, max_length=512)
        pairs = [(question, f"{self.chunks[i].get('title','')}. {self.chunks[i]['text']}") for i in idxs]
        scores = self._reranker.predict(pairs)
        order = np.argsort(-np.asarray(scores))
        return [idxs[j] for j in order], {idxs[j]: float(scores[j]) for j in range(len(idxs))}

    # ---- recherche
    def _search_once(self, question, k, mask, mode, rerank, pool, max_per_group, w_dense, w_bm25):
        info = {}
        if mode == "dense":
            ds = self._dense_scores(question, mask)
            ranked = top_indices(ds, pool)
            fused = {i: float(ds[i]) for i in ranked}
            info["dense"] = ds
        elif mode == "bm25":
            bs = self._bm25_scores(question, mask)
            ranked = top_indices(bs, pool)
            fused = {i: float(bs[i]) for i in ranked}
            info["bm25"] = bs
        elif mode == "hybrid":
            ds, bs = self._dense_scores(question, mask), self._bm25_scores(question, mask)
            ranked, fused = rrf_fuse([top_indices(ds, pool), top_indices(bs, pool)], [w_dense, w_bm25])
            ranked = ranked[:pool]
            info["dense"], info["bm25"] = ds, bs
        else:
            raise ValueError("mode doit être 'dense', 'bm25' ou 'hybrid'")
        if rerank and ranked:
            ranked, fused = self._rerank(question, ranked)
        # au plus max_per_group chunks par article (traductions comprises : même group_id)
        out, count = [], {}
        for i in ranked:
            g = self.chunks[i].get("group_id") or self.chunks[i].get("doc_id")
            if count.get(g, 0) >= max_per_group:
                continue
            count[g] = count.get(g, 0) + 1
            r = dict(self.chunks[i])
            r.update(score=round(float(fused[i]), 6), mode=mode + ("+rerank" if rerank else ""))
            if "dense" in info and np.isfinite(info["dense"][i]):
                r["dense_score"] = round(float(info["dense"][i]), 4)
            if "bm25" in info and np.isfinite(info["bm25"][i]):
                r["bm25_score"] = round(float(info["bm25"][i]), 4)
            out.append(r)
            if len(out) == k:
                break
        return out

    def search(self, question, k=5, region=None, theme=None, lang=None, mode="hybrid", rerank=False,
               pool=30, max_per_group=2, include_national=True, fallback=True,
               w_dense=1.0, w_bm25=1.0):
        """Renvoie une liste de k chunks (dicts du Lot 2 + score, mode, filtre, repli).
        Si les filtres laissent moins de k résultats, on les assouplit (langue, puis thème, puis région)."""
        steps = [(region, theme, lang)]
        if fallback:
            steps += [(region, theme, None), (region, None, None), (None, None, None)]
        seen, results, used = set(), [], None
        for step_no, (rg, th, lg) in enumerate(dict.fromkeys(steps)):
            if results and len(results) >= k:
                break
            mask = self._mask(rg, th, lg, include_national)
            res = self._search_once(question, k, mask, mode, rerank, pool, max_per_group, w_dense, w_bm25)
            for r in res:
                if r["chunk_id"] not in seen and len(results) < k:
                    seen.add(r["chunk_id"])
                    r["filtre"] = {"region": rg, "theme": th, "lang": lg}
                    r["repli"] = (rg, th, lg) != (region, theme, lang)
                    results.append(r)
        for rank, r in enumerate(results, start=1):
            r["rank"] = rank
        return results


# --------------------------------------------------------------------------- utilitaires
def load_chunks(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


_CACHE = {}


def retrieve(question, k=5, region=None, theme=None, lang=None, model="e5", mode="hybrid", rerank=False, **kw):
    """Point d'entrée pour le Lot 4. Le Retriever est chargé une seule fois par modèle."""
    key = (model, mode == "bm25")
    if key not in _CACHE:
        _CACHE[key] = Retriever.from_chunks(model) if mode == "bm25" else Retriever.from_index(model)
    return _CACHE[key].search(question, k=k, region=region, theme=theme, lang=lang, mode=mode,
                              rerank=rerank, **kw)


def to_context(results, max_chars=1500):
    """Met les passages en forme pour le prompt du Lot 4 : numérotés, avec source et licence."""
    blocs = []
    for r in results:
        titre = r.get("title", "")
        sec = f" — {r['section']}" if r.get("section") else ""
        reg = f" ({r['region']})" if r.get("region") and r["region"] != "National" else ""
        blocs.append(f"[{r['rank']}] {titre}{sec}{reg}\nSource : {r.get('url','')} ({r.get('license','')})\n"
                     f"{r['text'][:max_chars]}")
    return "\n\n".join(blocs)


def main():
    ap = argparse.ArgumentParser(description="Lot 3 — recherche dans l'index")
    ap.add_argument("question")
    ap.add_argument("--model", default="e5", choices=["e5", "bge-m3", "minilm"])
    ap.add_argument("--mode", default="hybrid", choices=["dense", "bm25", "hybrid"])
    ap.add_argument("--rerank", action="store_true")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--region")
    ap.add_argument("--theme")
    ap.add_argument("--lang")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    res = retrieve(a.question, k=a.k, region=a.region, theme=a.theme, lang=a.lang, model=a.model,
                   mode=a.mode, rerank=a.rerank)
    for r in res:
        flag = "  [repli]" if r["repli"] else ""
        print(f"{r['rank']}. {r['title']} | {r.get('section','')} | {r.get('region','')} | "
              f"{r['lang']} | score={r['score']}{flag}")
        print(f"   {r['text'][:160].strip()}…")


if __name__ == "__main__":
    main()
