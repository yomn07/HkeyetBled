# Calibration du seuil de refus (e5, mode hybrid)

| Groupe | n | min | 10e centile | médiane | max |
|---|---|---|---|---|---|
| Questions du corpus | 37 | 0.825 | 0.833 | 0.867 | 0.932 |
| Questions hors sujet | 16 | 0.742 | 0.758 | 0.787 | 0.837 |

Les groupes se chevauchent (max hors sujet 0.837 ≥ 10e centile corpus 0.833). Seuil prudent suggéré : 0.847 (au-dessus du max hors sujet) ; certaines questions du corpus seront refusées. Alternative : garder un seuil plus bas et laisser le LLM refuser ([NO_INFO]).

## Questions du corpus les plus basses (risque de faux refus)

| Question | meilleur cosinus |
|---|---|
| Zone humide près de Sousse où s'arrêtent les oiseaux migrateurs | 0.825 |
| ما هي أشهر الأطباق التقليدية في صفاقس؟ | 0.829 |
| ما هي القرية ذات اللونين الأزرق والأبيض قرب تونس العاصمة؟ | 0.831 |
| ما هي المدينة البونيقية المكتشفة في الوطن القبلي؟ | 0.833 |
| Je cherche un site romain bien conservé dans le nord-ouest | 0.835 |
| Mountain oasis with a waterfall near Tozeur | 0.835 |
| Village bleu et blanc près de Tunis, célèbre pour ses cafés | 0.836 |
| ما هي أهم معالم موقع دقة الأثري؟ | 0.846 |

## Questions hors sujet, de la plus haute à la plus basse (risque de fausse réponse)

| Question | meilleur cosinus |
|---|---|
| Quel est le climat au Maroc en été ? | 0.837 |
| Quelle est la capitale de l'Algérie ? | 0.835 |
| Quelle est la recette de la pizza napolitaine ? | 0.809 |
| Combien de planètes y a-t-il dans le système solaire ? | 0.802 |
| كيف أصلح مكيف الهواء في المنزل؟ | 0.791 |
| Who won the 2018 football World Cup? | 0.790 |
| How do I train a neural network in PyTorch? | 0.788 |
| Quel est le meilleur smartphone en 2026 ? | 0.787 |
| What is the tallest building in Dubai? | 0.786 |
| Comment fonctionne un moteur de voiture ? | 0.783 |
| كيف أتعلم البرمجة بلغة بايثون؟ | 0.780 |
| Quelle est la capitale du Japon ? | 0.776 |
| شنوة أحسن تلفون في 2026؟ | 0.774 |
| ما هو سعر تذكرة الطائرة إلى باريس؟ | 0.763 |
| كم عدد الكواكب في المجموعة الشمسية؟ | 0.758 |
| ما هي عاصمة اليابان؟ | 0.742 |