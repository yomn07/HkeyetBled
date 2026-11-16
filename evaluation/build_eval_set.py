"""Construit evaluation/eval_set.jsonl : jeu de test multilingue (fr/en/ar), multi-régions, 4 types de questions.
  answer     : 1 question par (gouvernorat, langue) quand le corpus a un document dans cette langue
  story      : « raconte-moi… » (mode récit)
  itinerary  : parcours thématique sur une macro-région (mode itinéraire)
  hors_corpus: questions auxquelles le système DOIT refuser
Relancer : python evaluation/build_eval_set.py  (déterministe). Questions générées par gabarits : à relire."""
import json, random, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
chunks = [json.loads(l) for l in open(ROOT/"indexation/index/e5/chunks.jsonl", encoding="utf-8")]
docs = collections.OrderedDict()
for c in chunks: docs.setdefault(c["doc_id"], []).append(c)
groups = collections.defaultdict(set)
for d, cs in docs.items(): groups[cs[0]["group_id"]].add(d)
T = {
 "patrimoine_archeologique": {"fr": "Que peut-on découvrir sur le site de {t} ?", "en": "What can be learned about the site of {t}?", "ar": "ماذا نعرف عن موقع {t}؟"},
 "architecture_medinas": {"fr": "Que sait-on de l'architecture et du patrimoine bâti de {t} ?", "en": "What is notable about the architecture of {t}?", "ar": "ما الذي يميز عمارة {t}؟"},
 "nature_paysages": {"fr": "Comment est le paysage de {t} ?", "en": "What is the landscape of {t} like?", "ar": "كيف هي الطبيعة في {t}؟"},
 "histoire": {"fr": "Quelle est l'histoire de {t} ?", "en": "What is the history of {t}?", "ar": "ما هي قصة {t}؟"},
 "gastronomie": {"fr": "Que goûter à {t} ?", "en": "What local food is linked to {t}?", "ar": "ما هي الأكلات المرتبطة بـ {t}؟"},
 "coutumes_fetes": {"fr": "Quelles traditions ou fêtes sont liées à {t} ?", "en": "Which traditions are linked to {t}?", "ar": "ما هي العادات المرتبطة بـ {t}؟"},
 "musique_arts": {"fr": "Quelles traditions artistiques sont liées à {t} ?", "en": "Which arts are linked to {t}?", "ar": "ما هي الفنون المرتبطة بـ {t}؟"},
 "artisanat": {"fr": "Quel savoir-faire artisanal associe-t-on à {t} ?", "en": "Which craft is associated with {t}?", "ar": "ما هي الحرفة المرتبطة بـ {t}؟"},
}
STORY = {"fr": "Raconte-moi l'histoire de {t}.", "en": "Tell me the story of {t}.", "ar": "احكِ لي قصة {t}."}
MACRO = {"Grand Tunis": ("le Grand Tunis", "Greater Tunis", "تونس الكبرى"), "Nord-Est": ("le Nord-Est", "the north-east", "الشمال الشرقي"),
         "Nord-Ouest": ("le Nord-Ouest", "the north-west", "الشمال الغربي"), "Centre-Est": ("le Centre-Est (Sahel)", "the Sahel coast", "الساحل"),
         "Centre-Ouest": ("le Centre-Ouest", "central-western Tunisia", "الوسط الغربي"), "Sud-Est": ("le Sud-Est", "the south-east", "الجنوب الشرقي"),
         "Sud-Ouest": ("le Sud-Ouest", "the south-west", "الجنوب الغربي")}
ITI = {"patrimoine_archeologique": ("Propose-moi un itinéraire de sites archéologiques dans {m}.", "Plan an itinerary of archaeological sites in {m}.", "اقترح عليّ مسارا لزيارة المواقع الأثرية في {m}."),
       "gastronomie": ("Propose-moi un itinéraire gastronomique dans {m}.", "Plan a food itinerary in {m}.", "اقترح عليّ مسارا للمأكولات التقليدية في {m}."),
       "architecture_medinas": ("Propose-moi un itinéraire de médinas et monuments dans {m}.", "Plan an itinerary of medinas and monuments in {m}.", "اقترح عليّ مسارا لزيارة المدن العتيقة والمعالم في {m}.")}
OOC = [("fr", "Quelle est la capitale du Maroc ?"), ("en", "What is the capital of Algeria?"), ("ar", "ما هي عاصمة اليابان؟"),
       ("fr", "Comment préparer une pizza napolitaine ?"), ("en", "Who won the 2018 football World Cup?"), ("ar", "من هو رئيس فرنسا؟"),
       ("fr", "Comment réparer un moteur de voiture ?"), ("en", "What is the best programming language to learn?"), ("fr", "Quel est le plat national de l'Italie ?"),
       ("en", "How tall is the Eiffel Tower?")]
BAD = ("Gouvernorat", "Délégation", "délégation", "École", "Mekletna", "Barrage", "Bassin", "Governorate", "Delegation", "ولاية", "معتمدية")
rnd = random.Random(11); out = []
def add(**k): out.append({"id": f"q{len(out)+1:03d}", **k})
def ok(cs): return len(cs[0]["text"]) > 300 and sum(len(x["text"]) for x in cs) > 900 and not cs[0]["title"].startswith(BAD)
def expected(cs): return sorted({docs[d][0]["title"] for d in groups[cs[0]["group_id"]]})
regions = sorted({cs[0]["region"] for cs in docs.values()})
used = set(); theme_use = collections.Counter()
for lang in ("fr", "en", "ar"):                                   # 1) answer : région x langue
    for reg in regions:
        c = [(d, cs) for d, cs in docs.items() if cs[0]["lang"] == lang and cs[0]["region"] == reg and cs[0]["theme"] in T and ok(cs) and d not in used]
        if not c: continue
        rnd.shuffle(c); c.sort(key=lambda x: theme_use[x[1][0]["theme"]]); d, cs = c[0]; used.add(d); th = cs[0]["theme"]; theme_use[th] += 1
        add(mode="answer", lang=lang, region=reg, theme=th, question=T[th][lang].format(t=cs[0]["title"]), expected=expected(cs), reference=cs[0]["text"][:600], url=cs[0]["url"])
for lang in ("fr", "en", "ar"):                                   # 2) story : 4 par langue, régions variées
    c = [(d, cs) for d, cs in docs.items() if cs[0]["lang"] == lang and cs[0]["theme"] in ("histoire", "coutumes_fetes", "patrimoine_archeologique", "musique_arts")
         and ok(cs) and d not in used and cs[0]["region"] != "National"]
    rnd.shuffle(c); seen = set()
    for d, cs in c:
        if cs[0]["region"] in seen: continue
        seen.add(cs[0]["region"]); used.add(d)
        add(mode="story", lang=lang, region=cs[0]["region"], theme=cs[0]["theme"], question=STORY[lang].format(t=cs[0]["title"]), expected=expected(cs), reference=cs[0]["text"][:600], url=cs[0]["url"])
        if len(seen) == 4: break
macro_regs = collections.defaultdict(set)
for cs in docs.values():
    if cs[0]["region"] != "National": macro_regs[cs[0]["region_macro"]].add(cs[0]["region"])
i = 0
for m, regs in sorted(macro_regs.items()):                        # 3) itinerary : 7 macro-régions x 2 thèmes, langues en rotation
    for th in rnd.sample(sorted(ITI), 2):
        lang = ("fr", "en", "ar")[i % 3]; k = ("fr", "en", "ar").index(lang); i += 1
        add(mode="itinerary", lang=lang, region=m, theme=th, question=ITI[th][k].format(m=MACRO[m][k]), expected_regions=sorted(regs) + ["National"])
for lang, q in OOC:                                               # 4) hors corpus : refus attendu
    add(mode="hors_corpus", lang=lang, region=None, theme=None, question=q, expected=[])
Path(ROOT/"evaluation/eval_set.jsonl").write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in out), encoding="utf-8")
print(len(out), "questions")
for k in ("mode", "lang"): print(k, dict(collections.Counter(o[k] for o in out)))
print("mode x lang", dict(collections.Counter((o["mode"], o["lang"]) for o in out)))
