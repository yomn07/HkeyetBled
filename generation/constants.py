"""Valeurs de référence issues du Lot 1 (fiche de corpus) : thèmes et régions.

Utile pour les filtres de l'interface (Lot 5). Les codes de thèmes sont ceux de
`data preprocessing/config/themes.yaml` ; les régions sont celles de `chunks.jsonl`
(le Lot 3 ignore accents et casse, donc "Médenine" et "Medenine" sont équivalents).
"""

THEMES = {
    "architecture_medinas": "Médinas, monuments et architecture",
    "patrimoine_archeologique": "Sites archéologiques et Antiquité",
    "gastronomie": "Gastronomie et produits du terroir",
    "nature_paysages": "Nature, oasis et paysages",
    "histoire": "Histoire et civilisations",
    "coutumes_fetes": "Coutumes, fêtes et traditions",
    "musique_arts": "Musique, danse et arts",
    "artisanat": "Artisanat et savoir-faire",
    "langue_savoir_vivre": "Langue, expressions et savoir-vivre",
}

REGIONS = [
    "Tunis", "Ariana", "Ben Arous", "Manouba", "Nabeul", "Zaghouan", "Bizerte",
    "Beja", "Jendouba", "Le Kef", "Siliana", "Sousse", "Monastir", "Mahdia", "Sfax",
    "Kairouan", "Kasserine", "Sidi Bouzid", "Gabes", "Medenine", "Tataouine",
    "Gafsa", "Tozeur", "Kebili",
]  # + "National" (contenu valable pour tout le pays, toujours inclus par le Lot 3)
