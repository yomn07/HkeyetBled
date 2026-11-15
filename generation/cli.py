"""Démo en ligne de commande du pipeline complet (Lot 3 -> Lot 4). Depuis la racine du dépôt :

    python -m generation.cli "Que goûter à Sfax ?" --region Sfax
    python -m generation.cli "Propose-moi un itinéraire archéologique" --mode itinerary
    python -m generation.cli "Raconte-moi la légende de Carthage"
    python -m generation.cli                       # mode interactif
    python -m generation.cli "Que visiter à Kairouan ?" --mock    # sans modèle d'embeddings
"""
import argparse
import json
import sys

from .llm import LLMError
from .pipeline import rag_answer


def show(r: dict, show_context: bool = False, show_raw: bool = False) -> None:
    best = r["best_relevance"]
    best = f"{best:.3f}" if isinstance(best, (int, float)) else "n/a"
    print(f"\n[mode={r['mode']} | langue={r['lang']} | passages={r['n_used']}/{r['n_retrieved']} "
          f"| meilleure pertinence={best}]")
    print(r["answer"])
    if show_raw and r.get("raw_answer") is not None:
        print(f"\n[réponse brute du LLM]\n{r['raw_answer']}")
    if r["refused"]:
        print(f"(refus : {r['reason']})")
    if r.get("grounding") is not None:
        print(f"(ancrage lexical : passages cités {r['grounding']} | contexte entier {r.get('grounding_context')})")
    for w in r["warnings"]:
        print(f"(avertissement : {w})")
    if r["sources"]:
        print("\nSources (* = citée dans la réponse) :")
        for s in r["sources"]:
            sec = f" — {s['section']}" if s["section"] else ""
            print(f" {'*' if s['cited'] else ' '}[{s['id']}] {s['title']}{sec} "
                  f"({s['region']}, {s['lang']}) pertinence {s['relevance'] if s['relevance'] is None else format(s['relevance'], '.3f')} | {s['license']}\n      {s['url']}")
            if show_context:
                print(f"      {s['text'][:300]}…")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("question", nargs="?")
    ap.add_argument("--mode", default="auto", choices=["auto", "answer", "story", "itinerary"])
    ap.add_argument("--lang", choices=["fr", "en", "ar"], help="langue de la réponse (défaut : celle de la question)")
    ap.add_argument("--region")
    ap.add_argument("--theme", help="code du thème, ex. gastronomie (voir generation/constants.py)")
    ap.add_argument("--mock", action="store_true", help="faux retriever (sans modèle ni index)")
    ap.add_argument("--show-context", action="store_true")
    ap.add_argument("--raw", action="store_true", help="affiche aussi la réponse brute du LLM (avant nettoyage des citations)")
    ap.add_argument("--json", action="store_true", help="affiche le dictionnaire brut")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.mock:
        from .mock_retriever import retrieve
        min_score = 0.3
    else:
        from .retriever_adapter import make_retriever
        retrieve = make_retriever()
        min_score = None  # seuil par modèle d'embeddings (config.py) ou RAG_MIN_SCORE
    filters = {k: v for k, v in (("region", args.region), ("theme", args.theme)) if v}

    def ask(q: str) -> None:
        try:
            r = rag_answer(q, retrieve, filters=filters, mode=args.mode, lang=args.lang, min_score=min_score)
        except LLMError as e:
            print(f"Erreur LLM : {e}")
            return
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            show(r, args.show_context, args.raw)

    if args.question:
        ask(args.question)
    else:
        print("Hkeyet Bled – tape une question (Ctrl+C pour quitter)")
        while True:
            try:
                q = input("\n> ").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if q:
                ask(q)


if __name__ == "__main__":
    main()
