"""Tests du Lot 3 sans modèle ni GPU : lancer avec  python -m unittest discover retrieval/tests -v"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from retrieve import Retriever, normalize, rrf_fuse, tokenize, to_context  # noqa: E402


def chunk(i, title, text, region, theme, lang="fr", group=None):
    return {"chunk_id": f"c{i}", "doc_id": f"d{i}", "title": title, "text": text, "section": "", "lang": lang,
            "region": region, "region_ar": "", "regions": [region], "theme": theme, "themes": [theme],
            "group_id": group or f"g{i}", "url": f"http://x/{i}", "license": "CC"}


# 4 « sujets » = 4 axes de l'espace vectoriel ; la question est un vecteur sur un axe.
CHUNKS = [
    chunk(0, "Amphithéâtre d'El Jem", "Le grand amphithéâtre romain de El Jem.", "Mahdia", "archeo"),
    chunk(1, "Kerkouane", "Cité punique de Kerkouane au cap Bon.", "Nabeul", "archeo"),
    chunk(2, "Cuisine de Sfax", "Poissons et épices dans la cuisine sfaxienne.", "Sfax", "gastronomie"),
    chunk(3, "Cuisine tunisienne", "Le couscous et la harissa partout.", "National", "gastronomie"),
    chunk(4, "الجم", "مدرج روماني في الجم", "Mahdia", "archeo", lang="ar", group="g0"),  # traduction de c0
    chunk(5, "Poterie de Nabeul", "Poterie traditionnelle de Nabeul.", "Nabeul", "artisanat"),
]
VEC = np.array([[1, 0, 0, 0], [0.9, 0.1, 0, 0], [0, 1, 0, 0], [0, 0.9, 0.1, 0], [1, 0, 0, 0], [0, 0, 1, 0]],
               dtype="float32")
VEC /= np.linalg.norm(VEC, axis=1, keepdims=True)


def fake_encode(q):
    axis = 1 if "cuisine" in q.lower() or "manger" in q.lower() else 0
    v = np.zeros(4, dtype="float32")
    v[axis] = 1
    return v


class TestTexte(unittest.TestCase):
    def test_accents_et_elision(self):
        self.assertIn("amphitheatre", tokenize("L'amphithéâtre d'El Jem"))

    def test_arabe_unifie(self):
        self.assertEqual(normalize("أَرْيَانَة"), normalize("اريانه"))

    def test_stopwords(self):
        self.assertNotIn("the", tokenize("the couscous"))


class TestFusion(unittest.TestCase):
    def test_rrf(self):
        ordre, _ = rrf_fuse([[1, 2, 3], [2, 3, 9]])
        self.assertEqual(ordre[0], 2)  # bien classé dans les deux listes
        self.assertEqual(set(ordre), {1, 2, 3, 9})


class TestRetriever(unittest.TestCase):
    def setUp(self):
        self.r = Retriever(CHUNKS, VEC, fake_encode)

    def test_bm25_trouve_nom_propre(self):
        res = self.r.search("Kerkouane", k=3, mode="bm25")
        self.assertEqual(res[0]["title"], "Kerkouane")

    def test_dense(self):
        res = self.r.search("que manger ?", k=2, mode="dense")
        self.assertEqual({x["title"] for x in res}, {"Cuisine de Sfax", "Cuisine tunisienne"})

    def test_hybride_combine(self):
        res = self.r.search("cuisine Kerkouane", k=4, mode="hybrid")
        titres = [x["title"] for x in res]
        self.assertIn("Kerkouane", titres)  # apporté par BM25
        self.assertTrue(any("Cuisine" in t for t in titres))  # apporté par le dense

    def test_filtre_region_garde_national(self):
        res = self.r.search("cuisine", k=3, region="Sfax", mode="dense", fallback=False)
        self.assertEqual({x["region"] for x in res}, {"Sfax", "National"})

    def test_filtre_region_sans_national(self):
        res = self.r.search("cuisine", k=3, region="Sfax", mode="dense", fallback=False, include_national=False)
        self.assertEqual({x["region"] for x in res}, {"Sfax"})

    def test_repli_si_filtre_trop_strict(self):
        res = self.r.search("poterie", k=3, region="Sfax", theme="artisanat", mode="bm25")
        self.assertTrue(res)  # le filtre exact ne donne rien : on assouplit
        self.assertTrue(all(x["repli"] for x in res))

    def test_pas_de_repli_si_assez_de_resultats(self):
        res = self.r.search("cuisine", k=2, region="Sfax", mode="dense")
        self.assertFalse(any(x["repli"] for x in res))

    def test_traductions_dedupliquees(self):
        res = self.r.search("amphithéâtre romain", k=5, mode="dense", max_per_group=1)
        groupes = [x["group_id"] for x in res]
        self.assertEqual(len(groupes), len(set(groupes)))

    def test_contrat_champs(self):
        res = self.r.search("Kerkouane", k=1, mode="bm25")
        for champ in ("chunk_id", "title", "text", "url", "license", "region", "score", "rank", "mode"):
            self.assertIn(champ, res[0])

    def test_bm25_seul_sans_vecteurs(self):
        r = Retriever(CHUNKS)
        self.assertEqual(r.search("poterie", k=1, mode="bm25")[0]["title"], "Poterie de Nabeul")
        with self.assertRaises(RuntimeError):
            r.search("poterie", mode="dense")

    def test_to_context(self):
        txt = to_context(self.r.search("Kerkouane", k=1, mode="bm25"))
        self.assertIn("[1] Kerkouane", txt)
        self.assertIn("http://x/1", txt)


if __name__ == "__main__":
    unittest.main()
