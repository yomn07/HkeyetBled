"""
Hkeyet Bled RAG — Lot 2 : Indexation
====================================
Lit data/corpus.jsonl (Lot 1), découpe en chunks (300-500 tokens avec chevauchement),
calcule les embeddings, construit un index FAISS et le sauvegarde avec ses métadonnées.

Commandes :
  python build_index.py build   --model e5
  python build_index.py compare --models e5 bge-m3 minilm --questions questions_test.jsonl
  python build_index.py search  --model e5 "Où voir un amphithéâtre romain ?" --region Mahdia

Sortie (dans index/<model>/) :
  index.faiss   vecteurs (produit scalaire sur vecteurs normalisés = similarité cosinus)
  chunks.jsonl  une ligne par chunk : texte + métadonnées (même ordre que l'index)
  config.json   modèle, paramètres de chunking, temps d'indexation, taille de l'index
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# --------------------------------------------------------------------------- modèles
# e5 exige les préfixes "passage: " (documents) et "query: " (questions).
MODELS = {
    "e5": {"name": "intfloat/multilingual-e5-base", "passage": "passage: ", "query": "query: "},
    "bge-m3": {"name": "BAAI/bge-m3", "passage": "", "query": ""},
    "minilm": {"name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
               "passage": "", "query": ""},
}

# Métadonnées recopiées du document vers chacun de ses chunks (contrat avec Lots 3 et 4)
META_KEYS = ["title", "lang", "url", "source", "source_type", "license", "redistributable",
             "region", "region_ar", "region_macro", "regions", "theme", "themes", "group_id"]

# Chemins calculés à partir de l'emplacement du script, pas du dossier où on lance la commande.
# Structure attendue du dépôt :
#   HkeyetBled/
#     data preprocessing/data/corpus.jsonl   (Lot 1)
#     indexation/build_index.py              (Lot 2, ce script)
#     indexation/index/<modele>/             (créé par le script)
HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent / "data preprocessing" / "data" / "corpus.jsonl"
INDEX_ROOT = HERE / "index"


# --------------------------------------------------------------------------- lecture
def load_corpus(path=CORPUS):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


# --------------------------------------------------------------------------- chunking
def split_sections(text):
    """Coupe le texte aux lignes '## Titre' produites par le Lot 1."""
    sections, title, buf = [], "", []
    for line in text.split("\n"):
        if line.startswith("## "):
            if "\n".join(buf).strip():
                sections.append((title, "\n".join(buf).strip()))
            title, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if "\n".join(buf).strip():
        sections.append((title, "\n".join(buf).strip()))
    return sections


def merge_small_sections(sections, tokenizer, min_tokens):
    """Une section trop courte est collée à la suivante, pour éviter des chunks minuscules."""
    merged, pending_title, pending_text = [], None, ""
    for title, body in sections:
        if pending_text:
            body = f"{pending_text}\n{title}\n{body}" if title else f"{pending_text}\n{body}"
            title = pending_title
            pending_title, pending_text = None, ""
        if len(tokenizer.encode(body, add_special_tokens=False)) < min_tokens:
            pending_title, pending_text = title, body
        else:
            merged.append((title, body))
    if pending_text:  # reste à la fin : on le colle à la dernière section
        if merged:
            t, b = merged[-1]
            merged[-1] = (t, b + "\n" + pending_text)
        else:
            merged.append((pending_title, pending_text))
    return merged


def chunk_document(doc, tokenizer, max_tokens, overlap, min_tokens):
    chunks = []
    sections = merge_small_sections(split_sections(doc["text"]), tokenizer, min_tokens)
    step = max_tokens - overlap
    for sec_title, body in sections:
        ids = tokenizer.encode(body, add_special_tokens=False)
        start = 0
        while True:
            piece = tokenizer.decode(ids[start:start + max_tokens], skip_special_tokens=True).strip()
            if piece:
                chunks.append({"section": sec_title or "", "text": piece,
                               "n_tokens": len(ids[start:start + max_tokens])})
            if start + max_tokens >= len(ids):
                break
            start += step
    # métadonnées + identifiant stable
    for i, ch in enumerate(chunks):
        ch["chunk_id"] = f"{doc['id']}__{i:03d}"
        ch["doc_id"] = doc["id"]
        for k in META_KEYS:
            ch[k] = doc.get(k)
    return chunks


def embed_text(chunk):
    """Texte réellement envoyé au modèle : titre + section en tête, pour donner du contexte."""
    head = chunk["title"] + (f" — {chunk['section']}" if chunk["section"] else "")
    return f"{head}\n{chunk['text']}"


# --------------------------------------------------------------------------- construction
def load_model(key):
    import torch
    # Le modèle est d'abord chargé sur le CPU.
    model = SentenceTransformer(MODELS[key]["name"], device="cpu")
    model.max_seq_length = 512  # bge-m3 accepte 8192 par défaut : inutile et lent ici
    if torch.cuda.is_available():
        try:
            # Demi-précision (fp16) AVANT le transfert : le modèle prend 2 fois moins de mémoire GPU.
            # Indispensable sur un petit GPU (ex. MX550, 2 Go). Les vecteurs restent quasi identiques.
            model.half()
            model.to("cuda")
            name = torch.cuda.get_device_name(0)
            mem = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"      Calcul sur GPU : {name} ({mem:.1f} Go), demi-précision fp16")
            return model
        except torch.cuda.OutOfMemoryError:
            # GPU trop petit : on revient sur le CPU au lieu de planter.
            model.to("cpu")
            model.float()
            torch.cuda.empty_cache()
            print("      Mémoire GPU insuffisante : calcul sur CPU")
            return model
    print("      Calcul sur CPU")
    return model


def build(model_key, max_tokens=400, overlap=80, min_tokens=60, batch_size=32, limit=None):
    out = INDEX_ROOT / model_key
    out.mkdir(parents=True, exist_ok=True)
    cfg = MODELS[model_key]

    print(f"[1/4] Lecture de {CORPUS}")
    docs = load_corpus()
    if limit:
        docs = docs[:limit]

    print(f"[2/4] Chargement du modèle {cfg['name']}")
    model = load_model(model_key)
    tok = model.tokenizer

    t0 = time.perf_counter()
    print(f"[3/4] Chunking ({max_tokens} tokens, chevauchement {overlap})")
    chunks = [c for d in docs for c in chunk_document(d, tok, max_tokens, overlap, min_tokens)]
    t_chunk = time.perf_counter() - t0
    print(f"      {len(docs)} documents -> {len(chunks)} chunks")

    print("[4/4] Embeddings + index FAISS")
    t1 = time.perf_counter()
    texts = [cfg["passage"] + embed_text(c) for c in chunks]
    vecs = model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                        show_progress_bar=True, convert_to_numpy=True).astype("float32")
    t_embed = time.perf_counter() - t1

    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    faiss.write_index(index, str(out / "index.faiss"))

    with open(out / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    size_mb = os.path.getsize(out / "index.faiss") / 1e6
    meta_mb = os.path.getsize(out / "chunks.jsonl") / 1e6
    lengths = [c["n_tokens"] for c in chunks]
    config = {
        "model_key": model_key, "model_name": cfg["name"],
        "materiel": str(model.device) + (" (fp16)" if str(model.device).startswith("cuda") else ""),
        "batch_size": batch_size,
        "query_prefix": cfg["query"], "passage_prefix": cfg["passage"],
        "dim": int(vecs.shape[1]), "index_type": "IndexFlatIP (cosinus, vecteurs normalisés)",
        "chunking": {"max_tokens": max_tokens, "overlap": overlap, "min_tokens": min_tokens,
                     "coupe": "sections '## ' puis fenêtre glissante"},
        "n_docs": len(docs), "n_chunks": len(chunks),
        "tokens_par_chunk": {"moyenne": round(float(np.mean(lengths)), 1),
                             "min": int(min(lengths)), "max": int(max(lengths))},
        "temps_s": {"chunking": round(t_chunk, 1), "embeddings": round(t_embed, 1),
                    "total": round(t_chunk + t_embed, 1)},
        "taille_mo": {"index": round(size_mb, 2), "metadonnees": round(meta_mb, 2)},
        "corpus_sha256": file_sha256(CORPUS),
    }
    with open(out / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(json.dumps(config, ensure_ascii=False, indent=2))
    return config


# --------------------------------------------------------------------------- recherche
class Index:
    """Chargement simple d'un index, utilisable par le Lot 3 comme point de départ."""

    def __init__(self, model_key):
        d = INDEX_ROOT / model_key
        self.config = json.loads((d / "config.json").read_text(encoding="utf-8"))
        self.index = faiss.read_index(str(d / "index.faiss"))
        with open(d / "chunks.jsonl", encoding="utf-8") as f:
            self.chunks = [json.loads(l) for l in f]
        self.model = load_model(model_key)

    def search(self, query, k=5, region=None, theme=None, lang=None):
        q = self.model.encode([self.config["query_prefix"] + query],
                              normalize_embeddings=True).astype("float32")
        # on récupère plus de résultats puis on filtre par métadonnées
        fetch = k if not (region or theme or lang) else min(len(self.chunks), k * 20)
        scores, ids = self.index.search(q, fetch)
        results = []
        for s, i in zip(scores[0], ids[0]):
            if i < 0:
                continue
            c = self.chunks[i]
            if region and region != c.get("region") and region not in (c.get("regions") or []):
                continue
            if theme and theme != c.get("theme") and theme not in (c.get("themes") or []):
                continue
            if lang and lang != c.get("lang"):
                continue
            results.append({**c, "score": float(s)})
            if len(results) == k:
                break
        return results


# --------------------------------------------------------------------------- comparaison
DEFAULT_QUESTIONS = [  # à remplacer par vos propres questions (fichier --questions)
    {"question": "Où voir un amphithéâtre romain en Tunisie ?", "expected": "El Jem"},
    {"question": "أين يوجد مسرح روماني في تونس؟", "expected": "El Jem"},
    {"question": "Roman amphitheatre in Tunisia", "expected": "El Jem"},
]


def load_questions(path):
    if not path:
        return DEFAULT_QUESTIONS
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


RESULTS = HERE / "resultats"  # hors de index/ : ce dossier, lui, va dans Git


def title_matches(title, expected):
    """expected peut être un texte ou une liste de variantes (FR / AR / EN)."""
    variants = expected if isinstance(expected, list) else [expected]
    t = (title or "").lower()
    return any(v.lower() in t for v in variants)


def md_table(rows):
    header = list(rows[0].keys())
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(r[h]) for h in header) + " |" for r in rows]
    return "\n".join(lines)


def compare(model_keys, questions_path, k=5, **build_kwargs):
    questions = load_questions(questions_path)
    RESULTS.mkdir(exist_ok=True)
    rows, by_lang, details = [], [], []
    for key in model_keys:
        if not (INDEX_ROOT / key / "config.json").exists():
            build(key, **build_kwargs)
        idx = Index(key)
        stats = {}  # langue -> [n, hits, somme des 1/rang]
        t0 = time.perf_counter()
        for q in questions:
            res = idx.search(q["question"], k=k)
            rank = next((r + 1 for r, c in enumerate(res) if title_matches(c["title"], q["expected"])), None)
            for lg in ("toutes", q.get("lang", "?")):
                s = stats.setdefault(lg, [0, 0, 0.0])
                s[0] += 1
                s[1] += rank is not None
                s[2] += 1 / rank if rank else 0
            details.append({"modele": key, "lang": q.get("lang", "?"), "question": q["question"],
                            "rang": rank or f">{k}", "top1": res[0]["title"] if res else ""})
        t_q = (time.perf_counter() - t0) / len(questions) * 1000
        c = idx.config
        n, h, rr = stats["toutes"]
        rows.append({"modele": key, "dim": c["dim"], "chunks": c["n_chunks"],
                     "materiel": c.get("materiel", "?"),
                     "temps_index_s": c["temps_s"]["total"], "taille_index_mo": c["taille_mo"]["index"],
                     f"hit@{k}": round(h / n, 3), "MRR": round(rr / n, 3),
                     "ms_par_requete": round(t_q, 1)})
        for lg, (n, h, rr) in sorted(stats.items()):
            if lg != "toutes":
                by_lang.append({"modele": key, "langue": lg, "questions": n,
                                f"hit@{k}": round(h / n, 3), "MRR": round(rr / n, 3)})

    report = (f"## Comparaison globale ({len(questions)} questions)\n\n{md_table(rows)}\n\n"
              f"## Par langue de la question\n\n{md_table(by_lang)}\n")
    print(report)
    (RESULTS / "comparaison_embeddings.md").write_text(report, encoding="utf-8")
    with open(RESULTS / "comparaison_details.csv", "w", encoding="utf-8-sig") as f:
        f.write("modele;lang;question;rang;top1\n")
        for d in details:
            f.write(";".join(str(d[x]).replace(";", ",") for x in d) + "\n")
    print(f"Résultats écrits dans {RESULTS}")
    return rows


# --------------------------------------------------------------------------- CLI
def main():
    p = argparse.ArgumentParser(description="Hkeyet Bled — Lot 2 indexation")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_chunk_args(sp):
        sp.add_argument("--max-tokens", type=int, default=400)
        sp.add_argument("--overlap", type=int, default=80)
        sp.add_argument("--min-tokens", type=int, default=60)
        sp.add_argument("--batch-size", type=int, default=32)
        sp.add_argument("--limit", type=int, default=None, help="n'indexer que N documents (test)")

    b = sub.add_parser("build"); b.add_argument("--model", choices=MODELS, default="e5"); add_chunk_args(b)
    c = sub.add_parser("compare"); c.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    c.add_argument("--questions", default=None); c.add_argument("--k", type=int, default=5); add_chunk_args(c)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--model", choices=MODELS, default="e5")
    s.add_argument("--k", type=int, default=5)
    s.add_argument("--region"); s.add_argument("--theme"); s.add_argument("--lang")

    a = p.parse_args()
    kw = lambda: dict(max_tokens=a.max_tokens, overlap=a.overlap, min_tokens=a.min_tokens,
                      batch_size=a.batch_size, limit=a.limit)
    if a.cmd == "build":
        build(a.model, **kw())
    elif a.cmd == "compare":
        compare(a.models, a.questions, k=a.k, **kw())
    else:
        for r in Index(a.model).search(a.query, a.k, a.region, a.theme, a.lang):
            print(f"{r['score']:.3f} | {r['title']} — {r['section']} | {r['region']} | {r['theme']} | {r['lang']}")
            print("      ", r["text"][:200].replace("\n", " "), "…")


if __name__ == "__main__":
    main()