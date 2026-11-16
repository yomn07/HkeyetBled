# Lot 5 — Évaluation multilingue
Jeu de test `eval_set.jsonl` : 107 questions en français, anglais et arabe, couvrant les 24 gouvernorats + National.
| Type | n | Ce qu'on mesure |
|---|---|---|
| answer | 71 (25 fr, 24 en, 22 ar) | le bon article est-il retrouvé (hit@k, MRR) ; refus à tort ; citations ; ancrage |
| story | 12 (4 par langue) | idem, en mode « Raconter » (le récit est refusé si aucun passage ne parle du sujet) |
| itinerary | 14 (7 macro-régions x 2 thèmes) | nombre d'étapes distinctes, précision régionale, doublons de lieu, citations |
| hors_corpus | 10 | le système doit REFUSER |
```
python evaluation/build_eval_set.py                 # régénère eval_set.jsonl
python -m evaluation.run_eval                       # retrieval seul (sans LLM)
python -m evaluation.run_eval --no-filter           # sans filtre région : test plus exigeant
python -m evaluation.run_eval --generate            # génération par mode + comparaison sans RAG
python -m evaluation.run_eval --generate --ragas    # + RAGAS (OPENAI_API_KEY requis)
```
Résultats dans `evaluation/resultats/` : `retrieval_multilingue.md`, `generation_resume.md`, `generation_avec_sans_rag.json`.
Limites : questions générées par gabarits (nom du lieu dans la question => test facile) ; moins de documents en arabe et en anglais
qu'en français, et certains gouvernorats (Ariana, Manouba, Sidi Bouzid) n'ont aucun document en arabe ; relire et compléter à la main.
