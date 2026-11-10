"""Génère la fiche de corpus (docs/fiche_corpus.md), les tableaux de couverture,
un graphique thème x macro-région et un échantillon à vérifier à la main."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date

import pandas as pd

from .annotate import NATIONAL, Annotator
from .common import DATA_DIR, DOCS_DIR, load_yaml, log, read_jsonl

MIN_DOCS_PER_THEME = 15
MIN_DOCS_REGION_THEME = 2  # par gouvernorat, pour les thèmes « régionaux »
FOCUS_THEMES = ["artisanat", "gastronomie", "coutumes_fetes"]
MACRO_ORDER = ["Grand Tunis", "Nord-Est", "Nord-Ouest", "Centre-Est", "Centre-Ouest", "Sud-Est", "Sud-Ouest", NATIONAL]

SCHEMA = [
    ("id", "str", "Identifiant unique : source_langue_slug_hash"),
    ("title", "str", "Titre de la page / de l'article"),
    ("lang", "str", "Langue : fr, ar, en"),
    ("text", "str", "Texte nettoyé ; les titres de section commencent par `## `, les items de liste par `- `"),
    ("url", "str", "URL d'origine (à afficher comme source citée)"),
    ("source", "str", "wikipedia, wikivoyage, unesco_whc, inp, ontt, blogs, equipe"),
    ("source_type", "str", "encyclopedie, guide_voyage, officiel, blog, equipe"),
    ("license", "str", "Licence / conditions d'utilisation"),
    ("redistributable", "bool", "Le texte peut-il être partagé publiquement ?"),
    ("region", "str", "Gouvernorat principal (24 valeurs) ou `National`"),
    ("region_ar", "str", "Nom arabe du gouvernorat"),
    ("region_macro", "str", "Grand Tunis, Nord-Est, Nord-Ouest, Centre-Est, Centre-Ouest, Sud-Est, Sud-Ouest, National"),
    ("regions", "list[str]", "Tous les gouvernorats significativement cités"),
    ("theme", "str", "Thème principal"),
    ("themes", "list[str]", "1 à 3 thèmes"),
    ("group_id", "str", "Identique pour les versions FR/AR/EN d'un même article"),
    ("categories", "list[str]", "Catégories Wikipédia (si disponibles)"),
    ("n_words / n_chars", "int", "Longueur du texte"),
    ("revid", "int", "Révision Wikipédia figée (reproductibilité)"),
    ("retrieved_at", "str", "Date/heure de collecte (UTC)"),
    ("annotation", "str", "`auto` ou `manuelle` (corrigée via config/overrides.csv)"),
]


def _md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.values) + " |")
    return "\n".join(lines)


def run_report(process_stats: dict | None = None) -> None:
    docs = read_jsonl(DATA_DIR / "corpus.jsonl")
    if not docs:
        raise SystemExit("data/corpus.jsonl est vide : lancez d'abord `python run_pipeline.py process`.")
    rejected = read_jsonl(DATA_DIR / "rejected.jsonl")
    ann = Annotator()
    regions_cfg = load_yaml("regions.yaml")
    DOCS_DIR.mkdir(exist_ok=True)

    df = pd.DataFrame(docs)
    df["tokens_est"] = (df["n_words"] * 1.35).round().astype(int)  # ~1.3-1.4 tokens/mot (FR/AR, tokenizer multilingue)
    tot_words = int(df["n_words"].sum())

    # --- sources
    src = (df.groupby(["source", "source_type", "license", "redistributable"])
             .agg(documents=("id", "count"), mots=("n_words", "sum")).reset_index()
             .sort_values("documents", ascending=False))
    src["redistributable"] = src["redistributable"].map({True: "oui", False: "non (liens seulement)"})
    # --- langues
    lang = df.groupby("lang").agg(documents=("id", "count"), mots=("n_words", "sum")).reset_index()
    # --- thèmes
    th = df.groupby("theme").agg(documents=("id", "count"), mots=("n_words", "sum"),
                                 fr=("lang", lambda s: (s == "fr").sum()), ar=("lang", lambda s: (s == "ar").sum()),
                                 en=("lang", lambda s: (s == "en").sum())).reset_index()
    th.insert(1, "libellé", th["theme"].map(ann.theme_label))
    th["statut"] = th["documents"].map(lambda n: "OK" if n >= MIN_DOCS_PER_THEME else "⚠ à renforcer")
    th = th.sort_values("documents", ascending=False)
    # --- régions (24 + National)
    rc = Counter(df["region"])
    multi = Counter(g for rs in df["regions"] for g in rs)
    reg_rows = [{"gouvernorat": g, "arabe": v["ar"], "macro-région": v["macro"],
                 "docs (principal)": rc.get(g, 0), "docs (cité)": multi.get(g, 0),
                 "statut": "OK" if rc.get(g, 0) >= 3 else ("⚠ faible" if multi.get(g, 0) else "✗ absent")}
                for g, v in regions_cfg.items()]
    reg_rows.append({"gouvernorat": NATIONAL, "arabe": "وطني", "macro-région": NATIONAL,
                     "docs (principal)": rc.get(NATIONAL, 0), "docs (cité)": "-", "statut": "-"})
    reg = pd.DataFrame(reg_rows)
    # --- matrice thème x macro
    mat = pd.crosstab(df["theme"].map(ann.theme_label), df["region_macro"])
    mat = mat.reindex(columns=[c for c in MACRO_ORDER if c in mat.columns], fill_value=0)
    mat.to_csv(DOCS_DIR / "couverture_theme_x_region.csv", encoding="utf-8")
    reg.to_csv(DOCS_DIR / "couverture_gouvernorats.csv", index=False, encoding="utf-8")

    # --- gouvernorat x thème (document compté s'il cite le gouvernorat, principal ou secondaire)
    focus = [t for t in FOCUS_THEMES if t in ann.themes]
    gt = pd.DataFrame(0, index=list(regions_cfg), columns=list(ann.themes))
    for d in docs:
        for g in set([d["region"]] + list(d.get("regions") or [])):
            if g in gt.index:
                for t in d.get("themes") or [d["theme"]]:
                    if t in gt.columns:
                        gt.loc[g, t] += 1
    gt.to_csv(DOCS_DIR / "couverture_gouvernorat_x_theme.csv", encoding="utf-8")
    gt_md = gt[focus + [c for c in gt.columns if c not in focus]].copy()
    gt_md["à renforcer"] = [", ".join(ann.theme_label(t) for t in focus if gt.loc[g, t] < MIN_DOCS_REGION_THEME) or "-"
                            for g in gt.index]
    gt_md = gt_md.reset_index().rename(columns={"index": "gouvernorat"})
    weak_cells = int((gt[focus] < MIN_DOCS_REGION_THEME).sum().sum())

    chart = None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 5))
        im = ax.imshow(mat.values, cmap="YlOrBr")
        ax.set_xticks(range(len(mat.columns)), mat.columns, rotation=30, ha="right")
        ax.set_yticks(range(len(mat.index)), mat.index)
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                v = mat.values[i, j]
                ax.text(j, i, v, ha="center", va="center", color="white" if v > mat.values.max() * 0.6 else "black", fontsize=9)
        ax.set_title("Hkeyet Bled – documents par thème et macro-région")
        fig.colorbar(im, ax=ax, shrink=0.8)
        fig.tight_layout()
        fig.savefig(DOCS_DIR / "couverture.png", dpi=150)
        plt.close(fig)
        chart = "couverture.png"
    except ImportError:
        log.info("matplotlib absent : pas de graphique")

    # --- longueurs
    desc = df["n_words"].describe(percentiles=[0.5, 0.9]).round(0)
    est_chunks = int((df["tokens_est"] / 400).clip(lower=1).round().sum())
    # --- rejets
    rej = Counter(r["reason"].split(" de ")[0].split(" (")[0] for r in rejected)
    # --- échantillon pour validation manuelle (stratifié par thème)
    per_theme = max(2, 50 // max(1, df["theme"].nunique()))
    sample = pd.concat([g.sample(min(len(g), per_theme), random_state=42) for _, g in df.groupby("theme")]).head(50)
    sample = sample.assign(extrait=sample["text"].str.slice(0, 300).str.replace("\n", " "),
                           region_correcte="", theme_correct="", commentaire="")
    sample[["id", "title", "lang", "url", "region", "theme", "themes", "extrait",
            "region_correcte", "theme_correct", "commentaire"]].to_csv(
        DOCS_DIR / "echantillon_validation.csv", index=False, encoding="utf-8-sig")

    example = {k: (v[:400] + "…" if k == "text" and isinstance(v, str) and len(v) > 400 else v)
               for k, v in docs[0].items()}
    gaps_th = th.loc[th["documents"] < MIN_DOCS_PER_THEME, "libellé"].tolist()
    gaps_reg = reg.loc[reg["statut"].isin(["✗ absent", "⚠ faible"]), "gouvernorat"].tolist()
    ps = process_stats or {}

    md = f"""# Fiche de corpus — Hkeyet Bled RAG

*Lot 1 · Corpus et collecte — généré automatiquement le {date.today().isoformat()} par `run_pipeline.py report`*

## 1. Identité du corpus

| Élément | Valeur |
|---|---|
| Nom | Hkeyet Bled – corpus patrimoine et traditions tunisiennes |
| Objectif | Base documentaire d'un assistant RAG répondant aux questions sur le patrimoine, l'artisanat, la gastronomie et les coutumes tunisiennes, et proposant récits et itinéraires culturels |
| Public visé | Touristes, étudiants, guides |
| Langues | {", ".join(f"{r.lang} ({r.documents})" for r in lang.itertuples())} |
| Documents | **{len(df)}** |
| Volume | {tot_words:,} mots ≈ {int(df["tokens_est"].sum()):,} tokens |
| Fichier principal | `data/corpus.jsonl` (1 document par ligne, UTF-8) |
| Version partageable | `data/corpus_public.jsonl` (texte retiré pour les sources non redistribuables, lien conservé) |

## 2. Sources et licences

{_md_table(src.rename(columns={"source_type": "type", "license": "licence", "redistributable": "redistribuable"}))}

Règles appliquées : API officielle MediaWiki pour Wikipédia/Wikivoyage (User-Agent identifié, 1 requête/s), `robots.txt` vérifié avant chaque page web, aucune page derrière authentification, citation systématique de l'URL d'origine dans chaque document. Les textes Wikipédia/Wikivoyage (CC BY-SA 4.0) sont redistribuables avec attribution ; les pages UNESCO, INP, ONTT et blogs ne sont utilisées que pour l'index local à des fins pédagogiques et ne sont partagées que sous forme de liens.

## 3. Couverture par thème

{_md_table(th.rename(columns={"theme": "code"}))}

Seuil de couverture : {MIN_DOCS_PER_THEME} documents par thème. {"Thèmes à renforcer : **" + ", ".join(gaps_th) + "**." if gaps_th else "Tous les thèmes atteignent le seuil."}

## 4. Couverture géographique (24 gouvernorats)

{_md_table(reg)}

*docs (principal)* = documents dont c'est la région principale ; *docs (cité)* = documents qui citent significativement le gouvernorat.
{"Gouvernorats faibles ou absents : **" + ", ".join(gaps_reg) + "**." if gaps_reg else "Tous les gouvernorats sont couverts."}

### 4 bis. Artisanat, gastronomie et coutumes par gouvernorat

Nombre de documents citant le gouvernorat pour chaque thème (un document peut compter pour plusieurs gouvernorats et jusqu'à 3 thèmes). Seuil : {MIN_DOCS_REGION_THEME} documents par gouvernorat pour l'artisanat, la gastronomie et les coutumes. Cases sous le seuil : **{weak_cells} / {len(gt) * len(focus)}**.

{_md_table(gt_md)}

## 5. Matrice thème × macro-région

{_md_table(mat.reset_index().rename(columns={"theme": "thème"}))}

{f"![Couverture]({chart})" if chart else ""}

## 6. Longueur des documents

| Statistique | Mots |
|---|---|
| min | {int(desc["min"])} |
| médiane | {int(desc["50%"])} |
| moyenne | {int(desc["mean"])} |
| 90e centile | {int(desc["90%"])} |
| max | {int(desc["max"])} |

Estimation pour le Lot 2 : ≈ **{est_chunks} chunks** de 400 tokens (sans chevauchement).

## 7. Chaîne de traitement

1. **Collecte** – Wikipédia FR (pivot, {sum(len(v) for v in load_yaml("sources.yaml")["wikipedia"]["seeds"].values())} articles amorces + catégories), versions AR/EN via les liens interlangues ; Wikivoyage FR/EN ; UNESCO, INP, ONTT (PDF), blogs.
2. **Nettoyage HTML** – suppression infobox, tableaux, bandeaux, navbox, légendes, appels de notes `[1]`, sections « Références / Liens externes / مراجع / وصلات خارجية » ; extraction du contenu principal des pages web (trafilatura / BeautifulSoup).
3. **Encodage** – réparation du mojibake (ftfy), normalisation Unicode NFKC (formes de présentation arabes → lettres standard), suppression des caractères invisibles (ZWJ, marques bidi, BOM), du tatweel {"et des harakat" if ps.get("strip_diacritics", True) else "(harakat conservés)"}.
4. **Filtrage** – documents < 80 mots (60 en arabe) écartés ; lignes répétées sur ≥ 3 pages d'un même site (menus, pieds de page) supprimées ({ps.get("n_boilerplate_lines", "n/d")} lignes).
5. **Déduplication** – doublons exacts (hash), quasi-doublons MinHash/LSH (Jaccard ≥ {ps.get("dedup_threshold", 0.8)}, même langue) et copies partielles (≥ 80 % du contenu déjà présent ailleurs), paragraphes longs répétés entre documents. Les traductions d'un même article sont conservées et reliées par `group_id`.
6. **Annotation** – région (gazetteer de 24 gouvernorats, FR/AR) et thème (lexique FR/EN/AR) ; corrections manuelles via `config/overrides.csv`.

Documents écartés ({len(rejected)}) : {", ".join(f"{k} : {v}" for k, v in rej.most_common()) or "aucun"} — détail dans `data/rejected.jsonl`.

## 8. Schéma d'un document (contrat avec le Lot 2)

{_md_table(pd.DataFrame(SCHEMA, columns=["champ", "type", "description"]))}

Exemple (texte tronqué) :

```json
{json.dumps(example, ensure_ascii=False, indent=2)}
```

## 9. Validation de l'annotation

Un échantillon stratifié de {len(sample)} documents est exporté dans `docs/echantillon_validation.csv`. Remplir les colonnes `region_correcte` / `theme_correct` (oui/non), puis reporter ici :

| Mesure | Valeur |
|---|---|
| Précision région (échantillon) | … % |
| Précision thème (échantillon) | … % |

Les erreurs relevées sont corrigées dans `config/overrides.csv` puis `python run_pipeline.py process report`.

## 10. Limites et biais connus

- Sur-représentation de Wikipédia et des grandes villes touristiques (Tunis, Sousse, Djerba, Kairouan) ; patrimoine immatériel rural moins documenté en ligne.
- Annotation automatique par mots-clés : un document « national » peut citer beaucoup de villes ; un article historique sur la « Régence de Tunis » est rattaché à Tunis.
- Le dialecte tunisien (darija) est peu documenté en ligne : il est couvert surtout par les fiches rédigées et vérifiées par l'équipe (`config/manual/`), les autres sources étant en arabe standard, français et anglais.
- Les pages web institutionnelles évoluent : les URL et la date de collecte sont conservées pour la traçabilité ; les révisions Wikipédia (`revid`) figent la version utilisée.
"""
    (DOCS_DIR / "fiche_corpus.md").write_text(md, encoding="utf-8")
    (DOCS_DIR / "stats.json").write_text(json.dumps({
        "n_docs": len(df), "n_words": tot_words, "by_lang": lang.set_index("lang")["documents"].to_dict(),
        "by_theme": th.set_index("theme")["documents"].to_dict(), "by_region": dict(rc),
        "by_source": src.groupby("source")["documents"].sum().to_dict(), "rejected": dict(rej), **ps,
    }, ensure_ascii=False, indent=2, default=int), encoding="utf-8")
    log.info("Fiche de corpus -> docs/fiche_corpus.md")
