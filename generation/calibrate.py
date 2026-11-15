"""Calibre le seuil de refus RAG_MIN_SCORE sur TES données (à lancer depuis la racine du dépôt).

    python -m generation.calibrate --model e5
    python -m generation.calibrate --model bge-m3

Principe : on mesure le meilleur cosinus (dense_score) renvoyé par le Lot 3
  - pour les questions de test du Lot 2 + EXTRA_IN_CORPUS (le corpus SAIT répondre) ;
  - pour OFF_TOPIC (le corpus NE SAIT PAS répondre).
Le seuil idéal sépare les deux groupes. Résultat écrit dans generation/resultats/.

Pour affiner : ajoute tes propres questions dans EXTRA_IN_CORPUS et OFF_TOPIC, puis relance.
Si tu ne modifies pas ces listes, tu obtiens exactement les mêmes chiffres.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

from .pipeline import best_relevance
from .retriever_adapter import make_retriever

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "indexation" / "questions_test.jsonl"

# Questions dont le corpus contient la réponse (sites vus dans les tests : El Jem, Kerkouane,
# Carthage, Dougga, Sfax). Ajoute des questions en arabe, en anglais et FLOUES : ce sont celles
# qui risquent d'être refusées à tort.
EXTRA_IN_CORPUS = [
    "ما هي المدينة البونيقية المكتشفة في الوطن القبلي؟",
    "أين يوجد المدرج الروماني في الجم؟",
    "ما هي أشهر الأطباق التقليدية في صفاقس؟",
    "ما هي أهم معالم موقع دقة الأثري؟",
    "ما هي أشهر آثار قرطاج؟",
    "What is the largest Roman amphitheatre in Tunisia?",
    "What can I eat in Sfax?",
    "What are the main ruins to see in Carthage?",
    "Je cherche un site romain bien conservé dans le nord-ouest",
    "Quels plats typiques goûter dans la ville de Sfax ?",
]

# Questions hors corpus. Les dernières sont volontairement PROCHES du sujet (cuisine, pays voisins) :
# c'est le vrai test du seuil. Ajoute des questions en dialecte tunisien si tu en as.
OFF_TOPIC = [
    "Quelle est la capitale du Japon ?",
    "Comment fonctionne un moteur de voiture ?",
    "Combien de planètes y a-t-il dans le système solaire ?",
    "Quel est le meilleur smartphone en 2026 ?",
    "How do I train a neural network in PyTorch?",
    "Who won the 2018 football World Cup?",
    "What is the tallest building in Dubai?",
    "كيف أصلح مكيف الهواء في المنزل؟",
    "ما هي عاصمة اليابان؟",
    "كم عدد الكواكب في المجموعة الشمسية؟",
    "ما هو سعر تذكرة الطائرة إلى باريس؟",
    "كيف أتعلم البرمجة بلغة بايثون؟",
    "شنوة أحسن تلفون في 2026؟",
    "Quelle est la recette de la pizza napolitaine ?",
    "Quelle est la capitale de l'Algérie ?",
    "Quel est le climat au Maroc en été ?",
]


def pct(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(p * len(vals)))]


def build_report(model, mode, in_q, in_scores, off_q, off_scores):
    """Construit le rapport Markdown. Retourne (texte, seuil suggéré)."""
    in_min, in_p10, off_max = min(in_scores), pct(in_scores, 0.10), max(off_scores)
    separated = off_max < in_min

    if separated:
        suggestion = round((in_min + off_max) / 2, 3)
    else:
        # Chevauchement : on privilégie "aucun faux refus" (un refus est une impasse pour
        # l'utilisateur), les hors-sujet qui passent seront refusés par le LLM ([NO_INFO]).
        suggestion = round(in_min - 0.005, 3)

    lines = [
        f"# Calibration du seuil de refus ({model}, mode {mode})\n",
        "| Groupe | n | min | 10e centile | médiane | max |", "|---|---|---|---|---|---|",
        f"| Questions du corpus | {len(in_scores)} | {in_min:.3f} | {in_p10:.3f} | {statistics.median(in_scores):.3f} | {max(in_scores):.3f} |",
        f"| Questions hors sujet | {len(off_scores)} | {min(off_scores):.3f} | {pct(off_scores, 0.10):.3f} | {statistics.median(off_scores):.3f} | {off_max:.3f} |",
        "",
    ]
    passing = [q for q, s in zip(off_q, off_scores) if s >= suggestion]
    if separated:
        lines.append(f"Les deux groupes sont séparés (écart {in_min - off_max:.3f}). "
                     f"**RAG_MIN_SCORE suggéré : {suggestion}** (milieu entre le max hors sujet et le min du corpus).")
    else:
        lines.append(f"Les groupes se chevauchent (max hors sujet {off_max:.3f} ≥ min corpus {in_min:.3f}). "
                     f"**RAG_MIN_SCORE suggéré : {suggestion}** = « aucun faux refus » sur les {len(in_scores)} questions du corpus. "
                     f"Avec ce seuil, {len(passing)} question(s) hors sujet sur {len(off_scores)} passent la recherche "
                     "et doivent être refusées par le LLM ([NO_INFO]) : à tester avec le vrai LLM.")
        if passing:
            lines += ["", "Hors-sujet qui passent le seuil : " + " ; ".join(passing)]

    lines += ["", "## Compromis selon le seuil", "",
              "| Seuil | questions du corpus refusées à tort | hors-sujet qui passent |", "|---|---|---|"]
    lo = int(min(min(in_scores), min(off_scores)) * 100)
    hi = int(max(max(in_scores), max(off_scores)) * 100) + 2
    for k in range(lo, hi, 1):
        th = k / 100
        fr = sum(s < th for s in in_scores)
        fa = sum(s >= th for s in off_scores)
        mark = " ← suggéré" if abs(th - suggestion) < 0.0051 else ""
        lines.append(f"| {th:.2f} | {fr}/{len(in_scores)} ({fr / len(in_scores):.0%}) | {fa}/{len(off_scores)} ({fa / len(off_scores):.0%}){mark} |")

    worst_in = sorted(zip(in_q, in_scores), key=lambda x: x[1])[:8]
    lines += ["", "## Questions du corpus les plus basses (risque de faux refus)", "",
              "| Question | meilleur cosinus |", "|---|---|"]
    lines += [f"| {q} | {s:.3f} |" for q, s in worst_in]
    lines += ["", "## Questions hors sujet, de la plus haute à la plus basse (risque de fausse réponse)", "",
              "| Question | meilleur cosinus |", "|---|---|"]
    lines += [f"| {q} | {s:.3f} |" for q, s in sorted(zip(off_q, off_scores), key=lambda x: -x[1])]
    return "\n".join(lines), suggestion


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="e5", choices=["e5", "bge-m3", "minilm"])
    ap.add_argument("--mode", default="hybrid", choices=["hybrid", "dense"])
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    retrieve = make_retriever(model=args.model, mode=args.mode, rerank=False)
    in_q = [json.loads(l)["question"] for l in open(QUESTIONS, encoding="utf-8") if l.strip()]
    in_q += [q for q in EXTRA_IN_CORPUS if q not in in_q]

    def best(q):
        return best_relevance(retrieve(q, {}, 5))

    in_scores = [best(q) for q in in_q]
    off_scores = [best(q) for q in OFF_TOPIC]
    text, suggestion = build_report(args.model, args.mode, in_q, in_scores, OFF_TOPIC, off_scores)
    print(text)
    out = ROOT / "generation" / "resultats" / f"calibration_seuil_{args.model}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"\nÉcrit : {out}\nPuis : $env:RAG_MIN_SCORE=\"{suggestion}\"   (PowerShell)")


if __name__ == "__main__":
    main()
