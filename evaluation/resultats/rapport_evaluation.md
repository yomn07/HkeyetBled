# Hkeyet Bled RAG — Rapport d'évaluation (Lot 5)

*Assistant d'exploration du patrimoine et des traditions tunisiennes — évaluation du retrieval et de la génération sur un jeu de test multilingue (français, anglais, arabe) couvrant les 24 gouvernorats.*

---

## 1. Objectif

Mesurer, sur des questions réalistes, si le système :

1. **retrouve** les bons passages dans le corpus (retrieval) ;
2. **répond** en s'appuyant sur ces passages, avec des citations, dans les trois modes de l'interface (*Répondre*, *Raconter*, *Itinéraire*) ;
3. **refuse** de répondre quand le corpus ne contient pas l'information.

## 2. Configuration évaluée

| Élément | Valeur |
|---|---|
| Corpus | 8 474 chunks, 1 163 documents (fr 4 883 chunks, en 2 107, ar 1 484), 24 gouvernorats + contenu « National » |
| Embeddings / recherche | e5 multilingue, recherche hybride BM25 + dense (configuration par défaut du Lot 3) — *à confirmer* |
| Reranker | non utilisé (défaut) — *à confirmer* |
| LLM de génération | *[à compléter : modèle et fournisseur utilisés]* |
| Garde-fous de refus | périmètre (pays étrangers), seuil de similarité (cosinus 0,82 pour e5), tag `[NO_INFO]` du LLM |
| Filtre région | actif pour *Répondre* et *Raconter* (région de la question) ; **aucun** pour *Itinéraire* |

## 3. Jeu de test

Le fichier `evaluation/eval_set.jsonl` contient **107 questions**, générées par gabarits à partir du corpus (script `evaluation/build_eval_set.py`, graine fixe).

| Type | Nombre | Construction |
|---|---|---|
| Réponse (*answer*) | 71 (25 fr, 24 en, 22 ar) | 1 question par couple (gouvernorat, langue) quand le corpus a un document dans cette langue |
| Récit (*story*) | 12 (4 par langue) | « Raconte-moi l'histoire de… », régions variées |
| Itinéraire (*itinerary*) | 14 (5 fr, 5 en, 4 ar) | 7 macro-régions × 2 thèmes (archéologie, gastronomie, médinas) |
| Hors corpus | 10 (4 fr, 4 en, 2 ar) | questions auxquelles le système **doit refuser** |

Chaque question de type réponse ou récit porte les titres d'articles attendus (dans toutes les langues disponibles pour l'article) et un extrait de référence. Les questions d'itinéraire portent la liste des gouvernorats de la macro-région demandée.

## 4. Métriques

- **hit@1 / hit@5** : part des questions pour lesquelles l'article attendu est le 1er résultat / dans les 5 premiers.
- **MRR** : moyenne de 1/rang de l'article attendu (1,00 = toujours premier).
- **Précision régionale** (itinéraire) : part des passages ou étapes situés dans la macro-région demandée, ou marqués « National ».
- **Refus à tort** : questions du corpus auxquelles le système a refusé de répondre.
- **Source attendue** : l'article attendu figure parmi les sources fournies au LLM.
- **Couverture des citations** : part des phrases de la réponse rattachées à une source `[n]`.
- **Ancrage lexical** : part des mots distinctifs de la réponse présents dans les passages fournis. Mesure approximative, non calculée pour l'arabe : elle ne prouve pas la fidélité.
- **Refus corrects** (hors corpus) : part des questions hors corpus effectivement refusées.

## 5. Résultats — retrieval

### 5.1 Réponse et récit (filtre région actif)

| Mode | n | hit@1 | hit@5 | MRR |
|---|---|---|---|---|
| Réponse | 71 | 0,85 | 1,00 | 0,92 |
| Récit | 12 | 0,92 | 1,00 | 0,96 |

| Langue | n | hit@1 | hit@5 | MRR |
|---|---|---|---|---|
| Arabe | 26 | 0,96 | 1,00 | 0,98 |
| Anglais | 28 | 0,75 | 1,00 | 0,88 |
| Français | 29 | 0,86 | 1,00 | 0,92 |

**Lecture.** Le bon article est toujours dans les 5 premiers (hit@5 = 1,00) et premier dans 85 % des cas pour les réponses. L'anglais est la langue la plus faible (hit@1 = 0,75), l'arabe la meilleure (0,96).

### 5.2 Par gouvernorat (mode réponse)

La plupart des gouvernorats obtiennent hit@1 = 1,00. Les cas en dessous :

| Gouvernorat | n | hit@1 | MRR |
|---|---|---|---|
| **Kairouan** | 3 | **0,33** | 0,58 |
| Sidi Bouzid | 2 | 0,50 | 0,75 |
| Jendouba, Kebili, Medenine, Nabeul, National, Siliana, Tataouine, Tozeur | 3 chacun | 0,67 | 0,83 |

Tous les gouvernorats ont hit@5 = 1,00. Avec 2 à 3 questions par gouvernorat, une seule erreur fait chuter la case de 0,33 : ces valeurs sont indicatives.

### 5.3 Itinéraire (sans filtre, top 8)

| Langue | n | Précision régionale |
|---|---|---|
| Arabe | 4 | 0,53 |
| Anglais | 5 | 0,35 |
| Français | 5 | 0,15 |

| Macro-région | n | Précision régionale |
|---|---|---|
| Sud-Est | 2 | 0,62 |
| Grand Tunis | 2 | 0,56 |
| Centre-Est | 2 | 0,50 |
| Nord-Ouest | 2 | 0,25 |
| Sud-Ouest | 2 | 0,25 |
| Centre-Ouest | 2 | 0,12 |
| Nord-Est | 2 | 0,00 |

**Lecture.** Pour un itinéraire, une grande partie des passages récupérés se trouve hors de la macro-région demandée. Le retriever du Lot 3 ne sait filtrer que sur **un** gouvernorat, et les noms de macro-régions (« Nord-Est », « Sahel ») n'apparaissent pas dans les textes : la recherche se fait donc sur toute la Tunisie. Les écarts entre langues ne sont pas interprétables (4 ou 5 questions par langue, régions et thèmes différents).

## 6. Résultats — génération

### 6.1 Réponse (71 questions)

| Langue | n | Refus à tort | Source attendue | Citations |
|---|---|---|---|---|
| Arabe | 22 | 0,05 | 1,00 | 0,99 |
| Anglais | 24 | 0,00 | 1,00 | 0,99 |
| Français | 25 | 0,04 | 1,00 | 0,99 |
| **Total** | 71 | **2/71** | **1,00** | **0,99** |

Ancrage lexical moyen : **0,66**. Alertes émises par le pipeline : `weak_grounding` sur 4 réponses, `citation_retry` sur 5 (une relance automatique a été nécessaire pour obtenir des citations).

Les deux refus à tort :
- `q017` (français) : la question générée est absurde (« traditions artistiques liées à *Tentatives infructueuses de participation au Concours Eurovision de la chanson* ») — défaut du générateur de questions, pas du système.
- `q057` (arabe, architecture de Kasserine) : refus du LLM (`llm_no_info`), probablement parce que les passages ne contenaient pas l'information demandée *(non vérifié)*.

### 6.2 Récit (12 questions)

Aucun refus, source attendue 1,00, couverture de citations 0,92, ancrage lexical 0,81. Quatre récits ont écarté des passages hors sujet (`passages_hors_sujet_ecartes`) : le garde-fou du récit fonctionne. Une relance de citations a été nécessaire pour quatre d'entre eux.

### 6.3 Itinéraire (14 questions)

| Indicateur | Valeur |
|---|---|
| Refus | 0/14 |
| Étapes distinctes par itinéraire (moyenne) | 3,9 |
| Doublons de lieu | 0,00 |
| Précision régionale des étapes | **0,39** |
| Couverture des citations | 0,89 |

**Lecture.** Les itinéraires sont structurés, sans lieu répété et bien cités, mais **géographiquement peu cohérents** : par exemple, l'itinéraire demandé pour le Sahel (Centre-Est) inclut Dougga (Béja) et Djerba, et celui du Centre-Ouest propose Tozeur et Sfax. La cause est le retrieval (section 5.3), pas le LLM.

### 6.3 Hors corpus (10 questions)

**10/10 refusées.** Cinq refus viennent du garde-fou de périmètre (question citant un autre pays : Maroc, Algérie, Japon, France, Italie), cinq du LLM (`llm_no_info`), y compris pour des questions sans pays cité (pizza napolitaine, réparation d'un moteur, langage de programmation, Coupe du monde, tour Eiffel).

## 7. Comparaison avec et sans RAG

Le LLM a aussi été interrogé **sans** contexte sur les questions du corpus (réponses enregistrées dans `generation_avec_sans_rag.json`). Exemple illustratif, question « Que sait-on de l'architecture et du patrimoine bâti de Raoued ? » :

- **Avec RAG** : la réponse reste prudente et signale que le contexte ne détaille pas le patrimoine bâti.
- **Sans RAG** : le modèle décrit des monuments détaillés (par exemple un château du 17e siècle) que nous n'avons pas vérifiés et qui ressemblent à des inventions.

Cette comparaison est **qualitative** et repose sur des exemples : aucune mesure automatique (RAGAS) n'a été produite dans ce rapport.

## 8. Limites de l'évaluation

1. **Questions générées par gabarits** : le nom du lieu figure dans la question, ce qui facilite le retrieval (surtout en BM25). Les scores sont plus élevés que sur des questions descriptives sans nom de lieu (le Lot 3 mesurait hit@5 = 0,93 sur 28 questions descriptives).
2. **Filtre région actif** : il réduit fortement le nombre de concurrents. Un test sans filtre (`--no-filter`) est plus exigeant.
3. **Petits effectifs** : 2 à 3 questions par gouvernorat, 12 questions de récit, 14 d'itinéraire. Les écarts entre cases ne sont pas statistiquement établis.
4. **Déséquilibre des langues dans le corpus** : moins de documents en arabe et en anglais qu'en français ; Ariana, Manouba et Sidi Bouzid n'ont aucun (ou presque) document arabe.
5. **Ancrage lexical** : mesure approximative, non calculée pour l'arabe, qui ne remplace pas une vérification de la fidélité.
6. **Itinéraire** : la précision régionale mesure la cohérence géographique, pas la qualité ni la faisabilité du parcours (ordre des étapes, distances).
7. **Qualité des réponses non mesurée par un humain** : pas de relecture systématique.

## 9. Pistes d'amélioration

| Priorité | Action | Effet attendu |
|---|---|---|
| 1 | Filtrer l'itinéraire sur le champ `region_macro` des chunks, ou chercher par gouvernorat de la macro-région puis fusionner | Relever la précision régionale (0,39 actuellement) |
| 2 | Relire les réponses signalées `weak_grounding` et les 2 refus | Détecter d'éventuelles réponses issues des connaissances du LLM |
| 3 | Remplacer `q017` et une dizaine de questions par des questions écrites à la main, sans nom de lieu | Test plus représentatif |
| 4 | Lancer `python -m evaluation.run_eval --no-filter` et reporter le résultat | Chiffre de retrieval sans filtre |
| 5 | Mesurer fidélité et pertinence avec RAGAS (avec/sans RAG) | Comparaison quantitative |
| 6 | Examiner les erreurs de Kairouan et de l'anglais (hit@1 plus bas) | Comprendre si le classement ou le corpus est en cause |

## 10. Reproduction

```bash
python evaluation/build_eval_set.py                 # régénère eval_set.jsonl (107 questions)
python -m evaluation.run_eval                       # retrieval seul
python -m evaluation.run_eval --no-filter           # sans filtre région
python -m evaluation.run_eval --generate            # génération par mode + comparaison sans RAG
python -m evaluation.run_eval --generate --ragas    # + RAGAS (OPENAI_API_KEY requis)
```

Fichiers produits : `evaluation/resultats/retrieval_multilingue.md`, `generation_resume.md`, `generation_avec_sans_rag.json`.

## 11. Conclusion

Avec un filtre région, le système retrouve le bon article dans les 5 premiers résultats pour toutes les questions du jeu de test et cite ses sources dans presque toutes les phrases ; il refuse correctement les 10 questions hors corpus. Le point faible identifié est l'**itinéraire** : les étapes sont citées et sans doublon, mais seulement 39 % d'entre elles se situent dans la macro-région demandée, à cause d'un retrieval qui ne filtre que sur un seul gouvernorat. Ces résultats restent à nuancer par la facilité du jeu de test et la taille des échantillons.
