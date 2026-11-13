"""
Hkeyet Bled RAG — Lot 3 : évaluation du retrieval
=================================================
Compare les configurations sur indexation/questions_test.jsonl (28 questions FR/AR/EN).

Métriques (un résultat est « bon » si le titre de l'article contient une variante attendue) :
  hit@1  : le bon article est en 1re position
  hit@5  : le bon article est dans les 5 premiers
  MRR    : moyenne de 1/rang du premier bon résultat (1 = toujours premier, 0 = jamais trouvé)

Exemples (depuis la racine du dépôt) :
  python retrieval/evaluate.py --models e5 --modes bm25                  # sans GPU ni modèle
  python retrieval/evaluate.py --models e5 bge-m3 --modes bm25 dense hybrid hybrid_rerank
  python retrieval/evaluate.py --models e5 --modes hybrid --theme-filter  # effet du filtre thème
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieve import Retriever  # noqa: E402

HERE = Path(__file__).resolve().parent
QUESTIONS = HERE.parent / "indexation" / "questions_test.jsonl"
OUT = HERE / "resultats"
K_MAX = 10


def title_matches(title, expected):
    variants = expected if isinstance(expected, list) else [expected]
    t = (title or "").lower()
    return any(v.lower() in t for v in variants)


def load_questions(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def first_rank(results, expected):
    for r in results:
        if title_matches(r.get("title"), expected):
            return r["rank"]
    return None


def evaluate(retriever, questions, mode, rerank, theme_filter):
    rows, t0 = [], time.time()
    for q in questions:
        res = retriever.search(q["question"], k=K_MAX, mode=mode, rerank=rerank,
                               theme=q.get("theme") if theme_filter else None, fallback=True)
        rows.append({"lang": q["lang"], "question": q["question"], "rank": first_rank(res, q["expected"]),
                     "top1": res[0]["title"] if res else ""})
    ms = (time.time() - t0) * 1000 / len(questions)
    return rows, ms


def summarize(rows):
    n = len(rows)
    ranks = [r["rank"] for r in rows]
    return {"n": n,
            "hit@1": round(sum(1 for r in ranks if r == 1) / n, 3),
            "hit@5": round(sum(1 for r in ranks if r and r <= 5) / n, 3),
            "MRR": round(sum(1 / r for r in ranks if r) / n, 3)}


def md_table(rows):
    header = list(rows[0].keys())
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(r[h]) for h in header) + " |" for r in rows]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["e5"])
    ap.add_argument("--modes", nargs="+", default=["bm25", "dense", "hybrid"],
                    choices=["bm25", "dense", "hybrid", "hybrid_rerank"])
    ap.add_argument("--questions", default=str(QUESTIONS))
    ap.add_argument("--theme-filter", action="store_true", help="ajoute aussi une ligne avec filtre thème")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    questions = load_questions(a.questions)
    summary, per_lang, details = [], [], []
    for model in a.models:
        needs_dense = any(m != "bm25" for m in a.modes)
        retr = Retriever.from_index(model) if needs_dense else Retriever.from_chunks(model)
        for mode in a.modes:
            base, rerank = mode.replace("_rerank", ""), mode.endswith("_rerank")
            if base == "bm25" and model != a.models[0]:
                continue  # BM25 ne dépend pas du modèle d'embeddings
            for tf in ([False, True] if a.theme_filter else [False]):
                rows, ms = evaluate(retr, questions, base, rerank, tf)
                label = mode + ("+filtre_theme" if tf else "")
                name = "—" if base == "bm25" else model
                summary.append({"modèle": name, "config": label, **summarize(rows), "ms/question": round(ms)})
                for lg in sorted({r["lang"] for r in rows}):
                    per_lang.append({"modèle": name, "config": label, "langue": lg,
                                     **summarize([r for r in rows if r["lang"] == lg])})
                details += [{"modèle": name, "config": label, **r} for r in rows]

    OUT.mkdir(exist_ok=True)
    md = ["# Lot 3 — Comparaison des configurations de retrieval\n",
          f"{len(questions)} questions de test (FR/AR/EN). hit@k = bon article dans les k premiers ; "
          "MRR = moyenne de 1/rang.\n", "## Résultats globaux\n", md_table(summary),
          "\n\n## Par langue\n", md_table(per_lang)]
    (OUT / "comparaison_retrieval.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    with open(OUT / "details_par_question.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(details[0].keys()))
        w.writeheader()
        w.writerows(details)
    print("\n".join(md))
    print(f"\nÉcrit : {OUT / 'comparaison_retrieval.md'} et details_par_question.csv")


if __name__ == "__main__":
    main()
