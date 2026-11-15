"""Faux retriever (même schéma de chunk que le Lot 2) pour tester SANS modèle d'embeddings.

Le score vaut un recouvrement de mots 0..1 : avec ce retriever, utiliser min_score=0.3.
"""
import unicodedata

_L = "CC BY-SA 4.0"

PASSAGES = [
    {"chunk_id": "mock_carthage__000", "title": "Carthage", "section": "Histoire", "lang": "fr",
     "source": "wikipedia", "license": _L, "redistributable": True, "url": "https://example.org/carthage",
     "region": "Tunis", "theme": "patrimoine_archeologique",
     "text": "Fondée selon la tradition par des colons phéniciens venus de Tyr, Carthage fut une grande puissance méditerranéenne avant d'être détruite par Rome en 146 av. J.-C. Ses vestiges, dont les thermes d'Antonin et le tophet, se trouvent près de Tunis et sont inscrits au patrimoine mondial de l'UNESCO depuis 1979."},
    {"chunk_id": "mock_kairouan__000", "title": "Kairouan", "section": "Patrimoine", "lang": "fr",
     "source": "wikipedia", "license": _L, "redistributable": True, "url": "https://example.org/kairouan",
     "region": "Kairouan", "theme": "architecture_medinas",
     "text": "La Grande Mosquée de Kairouan, fondée en 670 par Oqba ibn Nafi, est l'un des plus anciens lieux de culte musulmans du Maghreb. La médina de Kairouan est inscrite à l'UNESCO depuis 1988 et la ville est réputée pour ses tapis et ses makrouds."},
    {"chunk_id": "mock_dougga__000", "title": "Dougga", "section": "", "lang": "fr",
     "source": "wikipedia", "license": _L, "redistributable": True, "url": "https://example.org/dougga",
     "region": "Beja", "theme": "patrimoine_archeologique",
     "text": "Dougga, dans le nord-ouest du pays, conserve l'un des sites romains les mieux préservés d'Afrique du Nord, avec son théâtre et son Capitole. Le site est inscrit à l'UNESCO depuis 1997."},
    {"chunk_id": "mock_matmata__000", "title": "Matmata", "section": "", "lang": "fr",
     "source": "wikipedia", "license": _L, "redistributable": True, "url": "https://example.org/matmata",
     "region": "Gabes", "theme": "architecture_medinas",
     "text": "À Matmata, dans le sud, des familles berbères vivent dans des habitations troglodytes creusées autour d'une cour centrale pour se protéger de la chaleur."},
    {"chunk_id": "mock_djerba__000", "title": "Djerba", "section": "Artisanat", "lang": "fr",
     "source": "wikipedia", "license": _L, "redistributable": True, "url": "https://example.org/djerba",
     "region": "Medenine", "theme": "artisanat",
     "text": "L'île de Djerba est connue pour la synagogue de la Ghriba, lieu de pèlerinage, et pour le marché de Houmt Souk. Les potiers de Guellala y perpétuent une tradition artisanale ancienne."},
]


def _tokens(text):
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    for ch in ".,;:!?()«»\"'’-":
        text = text.replace(ch, " ")
    return {w for w in text.split() if len(w) >= 5}


def retrieve(question, filtres=None, k=5):
    filtres = filtres or {}
    q = _tokens(question)
    out = []
    for p in PASSAGES:
        if any(v and str(p.get(key, "")).lower() != str(v).lower() for key, v in filtres.items()):
            continue
        overlap = len(q & _tokens(p["text"]))
        out.append({**p, "score": round(min(1.0, overlap / max(len(q), 1) * 1.5), 3)})
    return sorted(out, key=lambda p: p["score"], reverse=True)[:k]
