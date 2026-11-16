"""Lot 5 — évaluation multilingue (fr/en/ar) des 4 types de questions de evaluation/eval_set.jsonl.
  python -m evaluation.run_eval                      # retrieval seul (sans LLM) : réponse/récit -> hit@k, MRR ; itinéraire -> précision régionale
  python -m evaluation.run_eval --no-filter          # idem sans filtre région (test plus exigeant)
  python -m evaluation.run_eval --generate           # + génération par mode, refus, citations, ancrage (LLM du Lot 4) + comparaison sans RAG
  python -m evaluation.run_eval --generate --ragas   # + RAGAS (OPENAI_API_KEY requis)
Écrit evaluation/resultats/*.md|json."""
import argparse, json, statistics as st, collections, unicodedata
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; OUT = ROOT/"evaluation/resultats"; OUT.mkdir(exist_ok=True, parents=True)
norm = lambda s: "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")
mean = lambda v: st.mean(v) if v else float("nan")

def rank_of(q, passages):
    exp = [norm(e) for e in q["expected"]]
    for i, p in enumerate(passages, 1):
        if any(e in norm(p.get("title")) for e in exp): return i
    return None

def reg_prec(q, ps): return mean([p.get("region") in q["expected_regions"] for p in ps])

def md_table(rows, key, cols):
    g = collections.defaultdict(list)
    for r in rows: g[r[key]].append(r)
    lines = [f"| {key} | n | " + " | ".join(c for c, _ in cols) + " |", "|---|---|" + "---|" * len(cols)]
    for k, v in sorted(g.items(), key=lambda x: str(x[0])):
        lines.append(f"| {k} | {len(v)} | " + " | ".join(f"{f(v):.2f}" for _, f in cols) + " |")
    return "\n".join(lines)

RET = [("hit@1", lambda v: mean([r["rank"] == 1 for r in v])), ("hit@5", lambda v: mean([bool(r["rank"]) for r in v])),
       ("MRR", lambda v: mean([1 / r["rank"] if r["rank"] else 0 for r in v]))]

def filters(q):
    return {"region": q["region"]} if q["mode"] in ("answer", "story") and q["region"] not in (None, "National") else {}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--generate", action="store_true"); ap.add_argument("--ragas", action="store_true")
    ap.add_argument("--k", type=int, default=5); ap.add_argument("--no-filter", action="store_true"); a = ap.parse_args()
    from generation.retriever_adapter import make_retriever
    retrieve = make_retriever()
    qs = [json.loads(l) for l in open(ROOT/"evaluation/eval_set.jsonl", encoding="utf-8")]
    ans = []; iti = []
    for q in qs:
        f = {} if a.no_filter else filters(q)
        if q["mode"] in ("answer", "story"): ans.append({**q, "rank": rank_of(q, retrieve(q["question"], f, a.k))})
        elif q["mode"] == "itinerary": iti.append({**q, "rp": reg_prec(q, retrieve(q["question"], {}, 8))})
    md = ["# Évaluation Lot 5 — retrieval multilingue", f"Filtre région {'désactivé' if a.no_filter else 'actif'} (réponse/récit). Itinéraire : sans filtre, top-8.", "",
          "## Réponse et récit : le bon article est-il retrouvé ?", "", md_table(ans, "mode", RET), "", md_table(ans, "lang", RET), "",
          md_table([r for r in ans if r["mode"] == "answer"], "region", RET), "",
          "## Itinéraire : part des passages situés dans la macro-région demandée (ou « National »)", "",
          md_table(iti, "lang", [("précision régionale", lambda v: mean([r["rp"] for r in v]))]), "",
          md_table(iti, "region", [("précision régionale", lambda v: mean([r["rp"] for r in v]))])]
    (OUT/"retrieval_multilingue.md").write_text("\n".join(md), encoding="utf-8"); print("\n".join(md[:8]))
    if not a.generate: return
    from generation import rag_answer
    from generation.llm import call_llm
    res = []
    for q in qs:
        r = rag_answer(q["question"], retrieve, filters=filters(q), mode="answer" if q["mode"] == "hors_corpus" else q["mode"])
        srcs = r["sources"]; used = [s for s in srcs if s["cited"]] or srcs
        row = {"id": q["id"], "mode": q["mode"], "lang": q["lang"], "region": q["region"], "question": q["question"], "rag": r["answer"], "refused": r["refused"],
               "reason": r["reason"], "warnings": r["warnings"], "contexts": [s["text"] for s in srcs], "reference": q.get("reference", ""),
               "grounding": r.get("grounding_context"), "cov": r.get("citation_coverage"), "reponse_ok": None, "sans_rag": ""}
        if q["mode"] in ("answer", "story"):
            row["source_hit"] = any(any(norm(e) in norm(s["title"]) for e in q["expected"]) for s in srcs)
        if q["mode"] == "itinerary":
            row["etapes"] = len({s["title"] for s in used}) if not r["refused"] else 0
            row["rp"] = mean([s["region"] in q["expected_regions"] for s in used]) if not r["refused"] else None
            row["doublons"] = len(used) - len({s["title"] for s in used}) if not r["refused"] else None
        if q["mode"] != "hors_corpus": row["sans_rag"] = call_llm("Réponds brièvement à la question sur la Tunisie, dans la langue de la question.", q["question"]).strip()
        res.append(row)
    (OUT/"generation_avec_sans_rag.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    g = lambda v, k: mean([x[k] for x in v if x.get(k) is not None])
    s = ["# Évaluation Lot 5 — génération", ""]
    for m in ("answer", "story"):
        v = [r for r in res if r["mode"] == m]; ok = [r for r in v if not r["refused"]]
        s += [f"## Mode {m} ({len(v)} questions)", f"- refus à tort : {len(v)-len(ok)}/{len(v)} · source attendue parmi les sources : {g(ok,'source_hit'):.2f} · "
              f"couverture de citations : {g(ok,'cov'):.2f} · ancrage lexical : {g(ok,'grounding'):.2f}",
              "", md_table(v, "lang", [("refus", lambda x: mean([r["refused"] for r in x])), ("source attendue", lambda x: g([r for r in x if not r["refused"]], "source_hit")),
                                        ("citations", lambda x: g([r for r in x if not r["refused"]], "cov"))]), ""]
    v = [r for r in res if r["mode"] == "itinerary"]; ok = [r for r in v if not r["refused"]]
    s += [f"## Mode itinéraire ({len(v)} questions)", f"- refus : {len(v)-len(ok)}/{len(v)} · étapes distinctes en moyenne : {g(ok,'etapes'):.1f} · précision régionale des étapes : {g(ok,'rp'):.2f} · "
          f"doublons de lieu : {g(ok,'doublons'):.2f} · couverture de citations : {g(ok,'cov'):.2f}", ""]
    v = [r for r in res if r["mode"] == "hors_corpus"]
    s += [f"## Hors corpus ({len(v)} questions, refus attendu)", f"- refus corrects : {sum(r['refused'] for r in v)}/{len(v)}",
          "- NON refusées : " + (" | ".join(r["question"] for r in v if not r["refused"]) or "aucune"), ""]
    (OUT/"generation_resume.md").write_text("\n".join(s), encoding="utf-8"); print("\n".join(s))
    if a.ragas:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy
        ok = [r for r in res if r["mode"] in ("answer", "story") and not r["refused"]]
        for name, key in (("avec_rag", "rag"), ("sans_rag", "sans_rag")):
            ds = Dataset.from_list([{"question": r["question"], "answer": r[key], "contexts": r["contexts"] if key == "rag" else [r["reference"]],
                                     "ground_truth": r["reference"]} for r in ok])
            sc = evaluate(ds, metrics=[faithfulness, answer_relevancy]); print(name, sc); s.append(f"RAGAS {name} : {sc}")
        (OUT/"generation_resume.md").write_text("\n".join(s), encoding="utf-8")
if __name__ == "__main__": main()
