"""Hkeyet Bled RAG — Lot 5 : interface « carnet de voyage » (Streamlit).
Lancer à la racine du dépôt :  streamlit run app.py
Photo de fond : déposer assets/tunisie.jpg (ou .png/.webp), 
HKEYET_DEMO=1 : faux retriever + faux LLM (aucun modèle requis), pour tester l'interface."""
import base64, os, json
from pathlib import Path
import plotly.graph_objects as go
import streamlit as st
from generation.constants import THEMES

ROOT = Path(__file__).resolve().parent
DEMO = os.getenv("HKEYET_DEMO") == "1"
NAMES = ["Tunis", "Ariana", "Ben Arous", "Manouba", "Nabeul", "Zaghouan", "Bizerte", "Beja", "Jendouba", "Le Kef", "Siliana", "Sousse", "Monastir",
         "Mahdia", "Sfax", "Kairouan", "Kasserine", "Sidi Bouzid", "Gabes", "Medenine", "Tataouine", "Gafsa", "Tozeur", "Kebili"]
GEO = json.loads((ROOT / "assets/tunisie_gouvernorats.geojson").read_text(encoding="utf-8"))  # limites réelles des 24 gouvernorats (iyedg/tunmaps, MIT)

MODES = {"Répondre": "answer", "Raconter": "story", "Itinéraire": "itinerary"}

st.set_page_config(page_title="Hkeyet Bled", page_icon="🌅", layout="wide")


def background_css():
    data, mime = None, "image/jpeg"
    for p in sorted((ROOT / "assets").glob("tunisie.*")) if (ROOT / "assets").exists() else []:
        data, mime = p.read_bytes(), "image/" + p.suffix[1:].replace("jpg", "jpeg"); break
    img = (f"url(data:{mime};base64,{base64.b64encode(data).decode()})" if data else
           "linear-gradient(180deg,#0e3b5c 0%,#2a7ca3 38%,#f0d9a8 62%,#c98b4e 100%)")  # repli : mer -> sable
    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Amiri:ital@0;1&family=Cormorant+Garamond:wght@500;700&family=Inter:wght@400;500&display=swap');
.stApp{{background:linear-gradient(rgba(8,20,30,.55),rgba(8,20,30,.72)),{img} center/cover fixed no-repeat;font-family:Inter,sans-serif}}
header[data-testid=stHeader]{{background:transparent}} .block-container,[data-testid=stMainBlockContainer]{{padding-top:1.2rem!important}} #MainMenu,footer{{visibility:hidden}}
h1.titre{{text-align:center;margin:0 0 .8rem!important;font-family:'Cormorant Garamond',serif;font-size:3.6rem;color:#fbf3e4;margin:0;letter-spacing:.02em}}
.titre small{{font-family:Amiri,serif;font-size:2rem;color:#e8a05a;margin-left:.8rem}}
[data-testid=stButtonGroup] button,button[data-testid^=stBaseButton-segmented_control]{{background:rgba(12,32,46,.82)!important;border:1px solid rgba(251,243,228,.45)!important}}
[data-testid=stButtonGroup] button *,button[data-testid^=stBaseButton-segmented_control] *{{color:#fbf3e4!important;font-weight:600!important}}
[data-testid=stButtonGroup] button:hover,button[data-testid^=stBaseButton-segmented_control]:hover{{background:rgba(232,160,90,.55)!important}}
[data-testid=stButtonGroup] button[aria-checked=true],button[aria-pressed=true],button[data-testid=stBaseButton-segmented_controlActive]{{background:#b8432f!important;border-color:#fbf3e4!important}}
h1.titre{{text-align:center;margin:0 0 .8rem!important;font-family:'Cormorant Garamond',serif;font-size:3.6rem;color:#fbf3e4;margin:0;letter-spacing:.02em}}
.titre small{{font-family:Amiri,serif;font-size:2rem;color:#e8a05a;margin-left:.8rem}}
button[data-testid^=stBaseButton-segmented_control]{{background:rgba(251,243,228,.15)!important;color:#fbf3e4!important}}
button[data-testid=stBaseButton-segmented_controlActive]{{background:#b8432f!important}}
[data-testid=stVerticalBlockBorderWrapper]{{background:rgba(251,243,228,.10);backdrop-filter:blur(14px);border:1px solid rgba(251,243,228,.25)!important;border-radius:18px}}
.stApp label,.stApp p,.stApp span,.stApp li{{color:#fbf3e4}}
.carte{{background:#fbf3e4;color:#1d2a30;border-radius:6px;padding:1.4rem 1.6rem;box-shadow:0 14px 40px rgba(0,0,0,.45);transform:rotate(-.6deg);
 border-left:10px solid #b8432f;position:relative;font-family:'Cormorant Garamond',serif;font-size:1.25rem;line-height:1.55}}
.carte p,.carte span,.carte li{{color:#1d2a30!important}}
.timbre{{position:absolute;top:-14px;right:18px;background:#b8432f;color:#fff!important;font:700 .8rem Inter;padding:.5rem .7rem;border:2px dashed #fbf3e4;transform:rotate(5deg)}}
.muet{{background:#1d2a30dd;color:#fbf3e4;border:1px dashed #e8a05a;border-radius:10px;padding:1rem 1.2rem}}
.tampon{{border:1px solid #e8a05a88;border-radius:10px;padding:.5rem .8rem;margin:.3rem 0;font-size:.9rem}}
.tampon.cite{{border-color:#e8a05a;background:#e8a05a22}} .rtl{{direction:rtl;font-family:Amiri,serif;font-size:1.5rem}}
</style>"""


@st.cache_resource(show_spinner="Chargement de l'index…")
def get_retriever():
    if DEMO:
        from generation.mock_retriever import retrieve
        return retrieve
    from generation.retriever_adapter import make_retriever
    return make_retriever()


def run(question, filters, mode):
    from generation import pipeline
    if DEMO:
        pipeline.call_llm = lambda s, u, max_tokens=0: "Selon les passages, ce lieu est connu pour son patrimoine [1]. On y trouve aussi des traditions locales [2]."
        return pipeline.rag_answer(question, get_retriever(), filters=filters, mode=mode, min_score=0.1)
    return pipeline.rag_answer(question, get_retriever(), filters=filters, mode=mode)


def carte(selected, route):
    on = set(route) | ({selected} if selected else set())
    z = [2 if n == selected else 1 if n in on else 0 for n in NAMES]
    fig = go.Figure(go.Choropleth(
        geojson=GEO, locations=NAMES, featureidkey="properties.NAME_EN", z=z, zmin=0, zmax=2, showscale=False,
        colorscale=[[0, "rgba(251,243,228,.30)"], [.5, "rgba(232,160,90,.70)"], [1, "rgba(184,67,47,.88)"]],
        marker=dict(line=dict(color="#fbf3e4", width=1.2)), hovertemplate="%{location}<extra></extra>",
        selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1))))
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator", bgcolor="rgba(0,0,0,0)")
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", geo_bgcolor="rgba(0,0,0,0)", dragmode=False, clickmode="event+select")
    return fig


ss = st.session_state
ss.setdefault("region", None); ss.setdefault("result", None); ss.setdefault("map_v", 0)
st.markdown(background_css(), unsafe_allow_html=True)
st.markdown("<h1 class='titre'>Hkeyet Bled<small>حكاية بلاد</small></h1>", unsafe_allow_html=True)

left, right = st.columns([5, 7], gap="large")
with left, st.container(border=True):
    ev = st.plotly_chart(carte(ss.region, ss.get("route", [])), key=f"map{ss.map_v}", on_select="rerun", selection_mode="points", config=dict(displayModeBar=False))
    pts = (ev.selection.points if ev and ev.selection else [])
    if pts: ss.region = pts[0].get("location") or ss.region
    c1, c2 = st.columns([3, 1]); c1.markdown(f"**Étape choisie :** {ss.region or 'toute la Tunisie'}")
    if c2.button("Tout", disabled=not ss.region): ss.region = None; ss.map_v += 1; st.rerun()

with right:
    with st.container(border=True):
        q = st.text_area("Votre question", placeholder="Que goûter à Sfax ? · أين أجد سوقا تقليديا ؟ · Where to see ksour?", height=90, label_visibility="collapsed", key="q")
        a, b = st.columns(2)
        mode_lbl = a.segmented_control("Forme", list(MODES), default="Répondre", label_visibility="collapsed") or "Répondre"
        theme = b.selectbox("Thème", ["Tous les thèmes"] + list(THEMES), format_func=lambda t: THEMES.get(t, t), label_visibility="collapsed")
        go_btn = st.button("Envoyer ", type="primary", use_container_width=True)
    question = q.strip()
    if go_btn and question:
        f = {k: v for k, v in {"region": ss.region, "theme": None if theme.startswith("Tous") else theme}.items() if v}
        with st.spinner("Le carnet feuillette ses pages…"):
            try: ss.result = (question, f, run(question, f, MODES[mode_lbl]))
            except Exception as e: ss.result = (question, f, {"error": str(e)})
    if ss.result:
        question, f, r = ss.result
        if "error" in r: st.error(f"Erreur : {r['error']} — vérifier l'index (Lot 2) et le LLM (Lot 4).")
        else:
            rtl = " rtl" if r["lang"] == "ar" else ""
            if r["refused"]:
                st.markdown(f"<div class='muet{rtl}'>📖 <b>Le carnet reste muet.</b><br>{r['answer']}<br><small>motif : {r['reason']}</small></div>", unsafe_allow_html=True)
                ss.route = []
            else:
                regs = list(dict.fromkeys(s["region"] for s in r["sources"] if s["region"] in NAMES)); ss.route = regs if r["mode"] == "itinerary" else regs[:3]
                stamp = (ss.region or (regs[0] if regs else "Tunisie")).upper()
                body = r["answer"].replace("\n", "<br>")
                st.markdown(f"<div class='carte{rtl}'><span class='timbre'>{stamp}</span>{body}</div>", unsafe_allow_html=True)
                if "filtre_assoupli" in r["warnings"]: st.caption("ℹ️ Peu de passages pour cette région : le filtre a été assoupli.")
                if {"no_citation", "weak_grounding"} & set(r["warnings"]): st.warning("Réponse à vérifier : citations faibles ou information absente des passages.")
            st.markdown("##### Tampons — sources")
            for s in r["sources"]:
                st.markdown(f"<div class='tampon {'cite' if s['cited'] else ''}'><b>[{s['id']}] {s['title']}</b> · {s['region']} · {THEMES.get(s['theme'], s['theme'])}<br>"
                            f"<a href='{s['url']}' target='_blank'>{s['source']}</a> · {s['license']}</div>", unsafe_allow_html=True)