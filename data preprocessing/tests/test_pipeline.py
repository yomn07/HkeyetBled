"""Tests hors-ligne : un faux serveur imite l'API MediaWiki et deux pages web,
puis on exécute collect -> process -> report dans un dossier temporaire.
Lancer :  python -m pytest -q tests/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hkeyet import common  # noqa: E402
from hkeyet.annotate import Annotator  # noqa: E402
from hkeyet.clean import detect_lang, mediawiki_html_to_text, normalize_text  # noqa: E402
from hkeyet.dedup import deduplicate  # noqa: E402

EL_JEM_FR = """
<div class="mw-parser-output">
<div class="bandeau-container">Cet article est une ébauche.</div>
<table class="infobox_v2"><tr><td>Pays Tunisie</td></tr></table>
<p>L'<b>amphithéâtre d'El Jem</b> est un amphithéâtre romain situé dans la ville d'El Jem, dans le gouvernorat de Mahdia, en Tunisie<sup class="reference">[1]</sup>.
Construit au IIIe siècle dans l'antique Thysdrus, il pouvait accueillir 35 000 spectateurs [réf. nécessaire].</p>
<p>""" + " ".join(["Les arènes romaines d'El Jem dominent la plaine du Sahel, entre Sousse et Sfax."] * 6) + """</p>
<div class="mw-heading mw-heading2"><h2 id="Histoire">Histoire</h2></div>
<p>Le monument romain fut transformé en forteresse et inscrit au patrimoine mondial de l'UNESCO en 1979. Les vestiges et les mosaïques du musée voisin témoignent de la richesse de la colonie romaine.</p>
<ul><li>Festival international de musique symphonique d'El Jem</li><li>Musée archéologique d'El Jem et ses mosaïques</li></ul>
<div class="mw-heading mw-heading2"><h2>Section vide</h2></div>
<div class="mw-heading mw-heading2"><h2 id="Notes">Notes et références</h2></div>
<ol class="references"><li>Source X</li></ol>
<p>Texte après références qui ne doit pas apparaître.</p>
</div>"""

EL_JEM_AR = """<div class="mw-parser-output"><p>قصر الجم أو مسرح الجم الأثري هو مسرح روماني يقع في مدينة الجم بولاية المهدية في تونس<sup>[١]</sup>. بُنِيَ في القرن الثالث ميلادي، ويعدّ من أكبر المسارح الرومانية في العالم وهو مدرج ضمن التراث العالمي لليونسكو منذ 1979. يقع المسرح الأثري في وسط المدينة ويستقبل كل صيف مهرجان الجم الدولي للموسيقى السمفونية. كان المسرح يتسع لخمسة وثلاثين ألف متفرج، واستعمل لاحقا حصنا. الآثار الرومانية في الجم تشمل أيضا متحفا يضم فسيفساء رائعة من العهد الروماني. تـــونس بلد غني بالآثار الرومانية والبونية.</p>
<h2>مراجع</h2><p>مرجع</p></div>"""

HARISSA_FR = """<div class="mw-parser-output"><p>La <b>harissa</b> est une purée de piments rouges, d'ail et d'épices, emblématique de la cuisine tunisienne. Inscrite en 2022 au patrimoine culturel immatériel de l'UNESCO, elle accompagne le couscous, la brik, l'ojja et le lablabi. La région de Nabeul et du Cap Bon est réputée pour ses piments séchés au soleil.</p>
<h2>Préparation</h2><p>""" + " ".join(["Les piments sont séchés, broyés puis mélangés à l'huile d'olive, au carvi, à la coriandre et à l'ail selon une recette transmise dans les familles tunisiennes."] * 5) + "</p></div>"

POTTERY_EN = """<div class="mw-parser-output"><p>Sejnane pottery is a traditional craft practised by the women of Sejnane, in the Bizerte Governorate of Tunisia. The pottery is shaped by hand without a wheel, fired in open fires and decorated with geometric motifs. This know-how was inscribed on the UNESCO intangible heritage list in 2018.</p><p>""" + " ".join(["The potters collect clay in the surrounding hills and transmit the craft from mother to daughter."] * 6) + "</p></div>"

OFFTOPIC_EN = "<div class='mw-parser-output'><p>" + " ".join(["An internal combustion engine is a heat engine that converts chemical energy into mechanical work."] * 10) + "</p></div>"

WEB_COPY = "<html><head><title>El Jem – Blog voyage | MonBlog</title></head><body><nav>Accueil Menu</nav><article><h1>El Jem</h1><p>" + \
    "L'amphithéâtre d'El Jem est un amphithéâtre romain situé dans la ville d'El Jem, dans le gouvernorat de Mahdia, en Tunisie. " + \
    " ".join(["Les arènes romaines d'El Jem dominent la plaine du Sahel, entre Sousse et Sfax."] * 6) + \
    "</p></article><footer>© MonBlog</footer></body></html>"

WEB_MOJIBAKE = "<html><head><title>Fête de la Ghriba</title></head><body><article><p>" + \
    ("Le pÃ¨lerinage de la Ghriba Ã  Djerba est une fÃªte traditionnelle juive qui attire chaque annÃ©e des milliers de fidÃ¨les. "
     "La synagogue d'Erriadh accueille processions, chants et rites. ") * 5 + "</p></article></body></html>"

PAGES = {
    ("fr", "Amphithéâtre d'El Jem"): (EL_JEM_FR, [{"lang": "ar", "title": "قصر الجم"}, {"lang": "en", "title": "Amphitheatre of El Jem"}], []),
    ("ar", "قصر الجم"): (EL_JEM_AR, [], []),
    ("en", "Amphitheatre of El Jem"): (None, [], []),  # simulate a fetch failure
    ("fr", "Harissa"): (HARISSA_FR, [], ["Cuisine tunisienne"]),
    ("en", "Combustion engine"): (OFFTOPIC_EN, [], []),
    ("en", "Sejnane pottery"): (POTTERY_EN, [], []),
}


class FakeResp:
    def __init__(self, status=200, js=None, text="", headers=None, content=b""):
        self.status_code, self._js, self.text = status, js, text
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self.content, self.encoding, self.apparent_encoding = content, "utf-8", "utf-8"

    def json(self):
        return self._js


class FakeSession:
    def __init__(self, *a, **k):
        self.calls = []

    def get(self, url, params=None, check_robots=False):
        self.calls.append((url, params))
        if "api.php" in url:
            lang = url.split("//")[1].split(".")[0]
            p = params or {}
            if p.get("list") == "categorymembers":
                return FakeResp(js={"query": {"categorymembers": [{"title": "Sejnane pottery"}, {"title": "Combustion engine"}]}})
            if p.get("list") == "search":
                hits = [{"title": "Harissa"}] if "harissa" in p["srsearch"].lower() else []
                return FakeResp(js={"query": {"search": hits}})
            if p.get("action") == "query":
                t = p["titles"]
                if t == "Homonymie":
                    return FakeResp(js={"query": {"pages": [{"title": t, "pageprops": {"disambiguation": ""}}]}})
                if (lang, t) not in PAGES:
                    return FakeResp(js={"query": {"pages": [{"title": t, "missing": True}]}})
                return FakeResp(js={"query": {"pages": [{"title": t, "pageid": 1, "langlinks": PAGES[(lang, t)][1]}]}})
            if p.get("action") == "parse":
                html, _, cats = PAGES.get((lang, p["page"]), (None, [], []))
                if html is None:
                    return FakeResp(js={"error": {"code": "missingtitle"}})
                return FakeResp(js={"parse": {"title": p["page"], "pageid": 1, "revid": 123, "text": html,
                                              "categories": [{"category": c} for c in cats]}})
        if url.endswith("/eljem"):
            return FakeResp(text=WEB_COPY)
        if url.endswith("/ghriba"):
            return FakeResp(text=WEB_MOJIBAKE)
        return FakeResp(status=404)


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    for mod in ("common", "collect_mediawiki", "collect_web", "process", "report"):
        m = __import__(f"hkeyet.{mod}", fromlist=["x"])
        for name, val in {"DATA_DIR": tmp_path / "data", "RAW_DIR": tmp_path / "data" / "raw",
                          "DOCS_DIR": tmp_path / "docs"}.items():
            if hasattr(m, name):
                monkeypatch.setattr(m, name, val)
    return tmp_path


CFG = {
    "wikipedia": {"license": "CC BY-SA 4.0", "redistributable": True, "source_type": "encyclopedie",
                  "pivot_lang": "fr", "follow_langlinks": ["ar", "en"], "max_per_category": 10,
                  "seeds": {"patrimoine_archeologique": ["Amphithéâtre d'El Jem", "Titre inexistant", "Homonymie"],
                            "gastronomie": ["harissa recette"]},
                  "categories": {"en": ["Category:Tunisian crafts"]}},
    "wikivoyage": {"license": "CC BY-SA 4.0", "redistributable": True, "source_type": "guide_voyage",
                   "langs": ["fr"], "pages": []},
    "web": [{"name": "blogs", "source_type": "blog", "license": "©", "redistributable": False,
             "urls": ["https://blog.example/eljem", "https://blog.example/ghriba", "https://blog.example/404"]}],
}


def test_end_to_end(sandbox):
    from hkeyet.collect_mediawiki import collect_wikipedia
    from hkeyet.collect_web import collect_web
    from hkeyet.process import run_process
    from hkeyet.report import run_report

    s = FakeSession()
    collect_wikipedia(CFG, s, ["fr", "ar", "en"])
    collect_web(CFG, s)
    raw = common.read_jsonl(sandbox / "data/raw/wikipedia.jsonl")
    assert {(r["lang"], r["title"]) for r in raw} == {
        ("fr", "Amphithéâtre d'El Jem"), ("ar", "قصر الجم"), ("fr", "Harissa"),
        ("en", "Sejnane pottery"), ("en", "Combustion engine")}
    # re-running collection must not duplicate (resume from cache)
    collect_wikipedia(CFG, FakeSession(), ["fr", "ar", "en"])
    assert len(common.read_jsonl(sandbox / "data/raw/wikipedia.jsonl")) == 5

    stats = run_process()
    docs = {d["title"]: d for d in common.read_jsonl(sandbox / "data/corpus.jsonl")}
    rejected = common.read_jsonl(sandbox / "data/rejected.jsonl")
    print(json.dumps(stats, indent=1))
    for d in docs.values():
        print(d["lang"], d["title"], "|", d["region"], d["region_macro"], d["regions"], "|", d["theme"], d["themes"])
    for r in rejected:
        print("REJ", r["title"], r["reason"])

    eljem = docs["Amphithéâtre d'El Jem"]
    assert "Texte après références" not in eljem["text"]
    assert "[1]" not in eljem["text"] and "réf. nécessaire" not in eljem["text"]
    assert "ébauche" not in eljem["text"] and "Pays Tunisie" not in eljem["text"]
    assert "## Histoire" in eljem["text"] and "Section vide" not in eljem["text"]
    assert "- Musée archéologique" in eljem["text"]
    assert eljem["region"] == "Mahdia" and eljem["theme"] == "patrimoine_archeologique"

    ar = docs["قصر الجم"]
    assert ar["lang"] == "ar" and ar["region"] == "Mahdia"
    assert "ـ" not in ar["text"] and "بُنِيَ" not in ar["text"] and "بني" in ar["text"]
    assert ar["group_id"] == eljem["group_id"]  # translations linked, not deduplicated

    assert docs["Harissa"]["theme"] == "gastronomie" and docs["Harissa"]["region"] in ("Nabeul", "National")
    assert "L'amphithéâtre" in eljem["text"]
    assert docs["Sejnane pottery"]["region"] == "Bizerte" and docs["Sejnane pottery"]["theme"] == "artisanat"
    ghriba = docs["Fête de la Ghriba"]
    assert "pèlerinage" in ghriba["text"] and "Ã" not in ghriba["text"]
    assert ghriba["region"] == "Medenine" and ghriba["theme"] == "coutumes_fetes"

    reasons = {r["title"]: r["reason"] for r in rejected}
    assert reasons.get("El Jem – Blog voyage", "").startswith("doublon")  # blog copy of Wikipedia
    assert reasons["Combustion engine"].startswith("hors sujet")

    public = common.read_jsonl(sandbox / "data/corpus_public.jsonl")
    assert all((d["text"] is None) == (not d["redistributable"]) for d in public)

    run_report(stats)
    md = (sandbox / "docs/fiche_corpus.md").read_text(encoding="utf-8")
    assert "Fiche de corpus" in md and "Mahdia" in md
    assert (sandbox / "docs/echantillon_validation.csv").exists()
    assert (sandbox / "docs/couverture.png").exists()


def test_units():
    assert detect_lang("Le patrimoine de la Tunisie est riche et varié.") == "fr"
    assert detect_lang("The heritage of Tunisia is rich.") == "en"
    assert detect_lang("التراث التونسي غني ومتنوع") == "ar"
    # Arabic presentation forms (ﻣﺪﻳﻨﺔ) -> standard letters
    assert normalize_text("ﻣﺪﻳﻨﺔ") == "مدينة"
    assert normalize_text("Kairouan​ est   belle [12] .") == "Kairouan est belle."
    a = Annotator()
    d = a.annotate({"id": "x", "title": "Tozeur", "text": "Oasis du Jérid, palmeraie et désert près de Nefta. Tunisie " * 5, "categories": []})
    assert d["region"] == "Tozeur" and d["theme"] == "nature_paysages"
    d = a.annotate({"id": "y", "title": "Régence", "text": "يقع سعيد بعيدا عن الأسباب " * 10, "categories": []})
    assert d["theme"] != "coutumes_fetes"  # 'عيد' must not match inside 'سعيد/بعيد'
    docs = [{"id": "a", "text": "un deux trois quatre cinq six sept huit neuf dix " * 20, "lang": "fr", "source_type": "blog"},
            {"id": "b", "text": "un deux trois quatre cinq six sept huit neuf dix " * 20 + " onze", "lang": "fr", "source_type": "encyclopedie"}]
    kept, removed = deduplicate(docs)
    assert [d["id"] for d in kept] == ["b"] and removed[0]["id"] == "a"
    assert "<p>" not in mediawiki_html_to_text("<div class='mw-parser-output'><p>ok</p></div>")


def test_manual(sandbox, monkeypatch):
    from hkeyet import collect_manual as cm
    from hkeyet.clean import clean_record
    from hkeyet.annotate import Annotator

    folder = sandbox / "cfg"
    (folder / "manual").mkdir(parents=True)
    body = "## Salutations\n- **Aslema** : bonjour en Tunisie. " + "Le marchandage au souk de la médina de Kairouan est habituel. " * 15
    (folder / "manual" / "ok.md").write_text("---\ntitle: Expressions\nlang: fr\ntheme: langue_savoir_vivre\nverified: true\n---\n" + body, encoding="utf-8")
    (folder / "manual" / "draft.md").write_text("---\ntitle: Brouillon\nverified: false\n---\ntexte", encoding="utf-8")
    monkeypatch.setattr(cm, "CONFIG_DIR", folder)
    cm.collect_manual({"manual": {"license": "CC BY 4.0", "redistributable": True, "source_type": "equipe"}})
    recs = common.read_jsonl(sandbox / "data/raw/manual.jsonl")
    assert [r["title"] for r in recs] == ["Expressions"]
    d = clean_record(recs[0]); d["id"] = "m1"
    a = Annotator().annotate(d)
    assert a["theme"] == "langue_savoir_vivre" and "**Aslema**" in a["text"]
