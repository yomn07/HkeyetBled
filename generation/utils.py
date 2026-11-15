"""Outils : détection de langue et de mode, mise en forme du contexte."""
import re
import unicodedata

_ARABIC = re.compile(r"[\u0600-\u06FF]")
_WORD = re.compile(r"[a-zàâçéèêëîïôûùüÿœ']+")

_FR = {
    "le", "la", "les", "des", "du", "de", "un", "une", "est", "et", "quel", "quelle",
    "quels", "quelles", "où", "comment", "pourquoi", "que", "qui", "dans", "pour",
    "sur", "avec", "je", "vous", "au", "aux", "en", "ce", "cette", "peut", "faire",
}
_EN = {
    "the", "is", "are", "what", "which", "where", "how", "why", "who", "of", "and",
    "to", "in", "for", "with", "can", "do", "does", "tell", "about", "best", "visit",
}

_ITINERARY_KEYS = (
    "itinéraire", "itineraire", "circuit", "plan de voyage", "itinerary", "trip plan",
    "مسار", "جولة", "برنامج رحلة",
)
_STORY_KEYS = (
    "raconte", "légende", "legende", "conte ", "story", "legend", "حكاية", "قصة", "احكي",
)


def detect_lang(text: str) -> str:
    """'ar' si majoritairement arabe, sinon 'en' ou 'fr' (défaut) selon les mots courants."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "fr"
    if sum(1 for c in letters if _ARABIC.match(c)) / len(letters) > 0.3:
        return "ar"
    words = _WORD.findall(text.lower())
    fr = sum(w in _FR for w in words)
    en = sum(w in _EN for w in words)
    return "en" if en > fr else "fr"


def detect_mode(text: str) -> str:
    """Devine le mode de sortie à partir de la question (défaut : 'answer')."""
    t = text.lower() + " "
    if any(k in t for k in _ITINERARY_KEYS):
        return "itinerary"
    if any(k in t for k in _STORY_KEYS):
        return "story"
    return "answer"


def format_context(passages: list, max_chars_per_passage: int, max_total_chars: int):
    """Numérote les passages [1], [2]... avec titre, section, région et langue.

    Retourne (texte du contexte, liste des passages réellement utilisés).
    """
    blocks, used, total = [], [], 0
    for p in passages:
        text = " ".join(str(p["text"]).split())[:max_chars_per_passage]
        head = str(p.get("title") or p.get("source") or "")
        if p.get("section"):
            head += f" — {p['section']}"
        meta = [x for x in (p.get("region"), p.get("lang")) if x]
        if meta:
            head += f" ({', '.join(meta)})"
        block = f"[{len(used) + 1}] {head}\n{text}"
        if used and total + len(block) > max_total_chars:
            break
        blocks.append(block)
        used.append(p)
        total += len(block)
    return "\n\n".join(blocks), used


# ---------------------------------------------------------------------------------------------
# Garde-fou n°0 : périmètre (le projet ne couvre que la Tunisie)
# ---------------------------------------------------------------------------------------------
def normalize(text: str) -> str:
    """Minuscules sans accents. Les lettres arabes sont gardées telles quelles
    (la décomposition Unicode retirerait la hamza de « الجزائر » ou « إيطاليا »)."""
    out = []
    for c in text.lower():
        if "\u0600" <= c <= "\u06FF":
            out.append(c)
        else:
            out.extend(ch for ch in unicodedata.normalize("NFD", c) if unicodedata.category(ch) != "Mn")
    return "".join(out)


_FOREIGN_LATIN = [
    "algerie", "maroc", "libye", "egypte", "france", "espagne", "italie", "turquie", "japon",
    "chine", "etats-unis", "usa", "allemagne", "royaume-uni", "angleterre", "arabie saoudite",
    "jordanie", "liban", "syrie", "russie", "inde", "bresil", "canada", "portugal", "grece",
    "mauritanie", "senegal", "qatar", "emirats", "algeria", "morocco", "libya", "egypt",
    "spain", "italy", "turkey", "japan", "china", "germany", "england", "saudi arabia",
    "russia", "india", "brazil", "greece", "united states",
]
_FOREIGN_AR = ["الجزائر", "المغرب", "ليبيا", "مصر", "فرنسا", "إسبانيا", "اسبانيا", "إيطاليا", "ايطاليا",
               "تركيا", "اليابان", "الصين", "ألمانيا", "السعودية", "روسيا", "الأردن", "لبنان", "سوريا"]
_TUNISIA_LATIN = [
    r"tunis\w*", "sfax", "sousse", "djerba", "kairouan", "carthage", "hammamet", "tozeur", "nefta",
    "monastir", "mahdia", "bizerte", "gabes", "gafsa", "kebili", "tataouine", "medenine", "nabeul",
    "zaghouan", "kasserine", "jendouba", "beja", "siliana", "le kef", "el jem", "dougga", "matmata",
    "sidi bou said", "kerkouane", "douz", "ariana", "manouba", "ben arous", "sidi bouzid",
]
_TUNISIA_AR = ["تونس", "صفاقس", "سوسة", "جربة", "القيروان", "قرطاج", "نابل", "الحمامات", "توزر",
               "المنستير", "المهدية", "بنزرت", "قابس", "قفصة", "الجم", "دقة"]


def _latin_re(terms):
    return re.compile(r"(?<![a-z])(?:" + "|".join(terms) + r")(?![a-z])")


_FOREIGN_RE = _latin_re(_FOREIGN_LATIN)
_TUNISIA_RE = _latin_re(_TUNISIA_LATIN)


def out_of_scope_term(question: str):
    """Renvoie le pays étranger cité si la question ne parle PAS de la Tunisie, sinon None.

    Garde-fou volontairement simple (liste de pays) : il attrape les questions proches du sujet
    qu'un seuil de similarité ne sépare pas (« capitale de l'Algérie », « climat au Maroc »).
    Une question qui cite un pays étranger ET un lieu tunisien n'est pas bloquée.
    """
    q = normalize(question)
    if _TUNISIA_RE.search(q) or any(w in q for w in _TUNISIA_AR):
        return None
    m = _FOREIGN_RE.search(q)
    if m:
        return m.group(0)
    for w in _FOREIGN_AR:
        if w in q:
            return w
    return None


# ---------------------------------------------------------------------------------------------
# Ancrage lexical : les mots distinctifs de la réponse figurent-ils dans les passages cités ?
# ---------------------------------------------------------------------------------------------
_STOP = {
    "cette", "ainsi", "aussi", "comme", "leurs", "elles", "vous", "nous", "dans", "avec", "pour",
    "sont", "plus", "mais", "peut", "peuvent", "donc", "alors", "etre", "tout", "tous", "entre",
    "which", "their", "there", "these", "those", "about", "where", "would", "could", "other",
}
_CITE = re.compile(r"\[\d+\]")


_NUM = re.compile(r"\d{1,3}(?:[\u202f\u00a0 ,.]\d{3})+|\d+")


def _numbers(text: str) -> set:
    """Nombres à 3 chiffres ou plus (« 35,000 », « 35 000 » et « 35.000 » donnent 35000) : dates,
    capacités... ce sont les détails que les LLM inventent le plus souvent."""
    digits = (re.sub(r"\D", "", m) for m in _NUM.findall(text))
    return {d for d in digits if len(d) >= 3}


def _content_words(text: str) -> set:
    clean = _CITE.sub(" ", text)
    words = {w for w in re.findall(r"[a-z]{5,}", normalize(clean)) if w not in _STOP}
    return words | _numbers(clean)


def grounding_score(answer: str, question: str, passages: list, answer_lang: str):
    """Part des mots distinctifs de la réponse (absents de la question) présents dans les passages.

    Renvoie None si le calcul n'a pas de sens : réponse en arabe, aucun passage cité dans la même
    langue que la réponse (une traduction ne partage pas les mots), ou aucun mot distinctif.
    Sert d'ALERTE (weak_grounding), jamais de refus automatique.
    """
    if answer_lang == "ar":
        return None
    same_lang = [p for p in passages if p.get("lang") == answer_lang]
    if not same_lang:
        return None
    words = _content_words(answer) - _content_words(question)
    if not words:
        return None
    context = set()
    for p in same_lang:
        context |= _content_words(str(p["text"]))
    return sum(w in context for w in words) / len(words)


# ---------------------------------------------------------------------------------------------
# Mode récit : ne garder que les passages qui parlent du sujet demandé
# ---------------------------------------------------------------------------------------------
_NOT_TOPIC = {
    "raconte", "raconter", "racontez", "histoire", "histoires", "legende", "legendes", "conte",
    "contes", "story", "stories", "legend", "legends", "tell", "myth", "mythe", "mythes",
    "tradition", "traditions", "quelle", "quels", "quelles", "comment", "pourquoi", "donne",
    "donnez", "parle", "parlez", "propose", "sujet", "please", "which", "where", "about",
}


def topic_terms(question: str) -> list:
    """Mots-clés du sujet d'une demande de récit : « Raconte-moi la légende de Carthage » -> ['carthage']."""
    words = re.findall(r"[a-z]{5,}", normalize(question))
    return [w for w in dict.fromkeys(words) if w not in _STOP and w not in _NOT_TOPIC]


def mentions_topic(passage: dict, terms: list) -> bool:
    """Vrai si le titre ou le texte du passage contient l'un des termes (6 premières lettres, pour
    tolérer pluriels et dérivés : « carthage » trouve « carthaginois »)."""
    text = normalize(f"{passage.get('title') or ''} {passage.get('text') or ''}")
    return any(re.search(r"(?<![a-z])" + re.escape(term[:6]), text) for term in terms)
