"""Nombres en chiffres à l'écran, en lettres pour la voix (règle de Luca du 28/09, docs/33-nombres-en-chiffres.md).

Luca veut les nombres et les années en chiffres dans tout ce qui s'affiche : sous-titres, titre d'accroche, textes à
l'écran (« 852 morts en pleine mer », jamais « huit cent cinquante-deux morts »). Les agents écrivent donc en chiffres
(consignes rules_storytelling et rules_hook_title) et ce module fait le reste :
- spoken() : les chiffres redeviennent des mots juste avant la voix de synthèse (providers/tts.py), qui lit mal
  « 1 350 », « 19e » ou « 14,5 M€ » ; il sert aussi à compter les mots dits (correcteur, minutage des sous-titres) ;
- to_digits(), merge_timed() : un nombre resté en lettres (script d'avant la règle, oubli du LLM) passe en chiffres,
  dans le script (normalize_story, normalize_script) et au montage, mots horodatés des sous-titres compris. Français
  seulement. Restent en lettres : « un » et « une » seuls (articles), « zéro » seul, « neuf » adjectif (« un navire
  neuf »), « tous les deux », « pour cent » après un nombre, les noms propres (« les Trois Mousquetaires »,
  « Trois-Rivières »).
Typographie française : années collées (« en 1992 »), quantités groupées par 3 avec une espace insécable
(« 1 350 tonnes », « 10 000 »), « 3 millions », « 19e siècle », « 30 % ».
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from .models import ScriptV1, WordTiming

NBSP = " "

# ---------------------------------------------------------------------------------------------------------------------
# Nombre → mots
# ---------------------------------------------------------------------------------------------------------------------

_FR_UNITS = ("zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze", "treize",
             "quatorze", "quinze", "seize")
_FR_TENS = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _fr_below_100(n: int, final: bool) -> str:
    """`final` : rien ne suit (« quatre-vingts ans ») ; sinon « quatre-vingt mille »."""
    if n <= 16:
        return _FR_UNITS[n]
    if n < 20:
        return "dix-" + _FR_UNITS[n - 10]
    if n >= 80:
        return "quatre-vingt" + (f"-{_fr_below_100(n - 80, True)}" if n > 80 else "s" if final else "")
    if n >= 70:
        return "soixante et onze" if n == 71 else "soixante-" + _fr_below_100(n - 60, True)
    tens, unit = divmod(n, 10)
    return _FR_TENS[tens] + ("" if unit == 0 else " et un" if unit == 1 else f"-{_FR_UNITS[unit]}")


def _fr_below_1000(n: int, final: bool) -> str:
    hundreds, rest = divmod(n, 100)
    words = []
    if hundreds:
        words.append("cent" if hundreds == 1 else f"{_FR_UNITS[hundreds]} cent{'s' if rest == 0 and final else ''}")
    if rest:
        words.append(_fr_below_100(rest, final))
    return " ".join(words)


def fr_cardinal(n: int, feminine: bool = False) -> str:
    """852 → « huit cent cinquante-deux », 1992 → « mille neuf cent quatre-vingt-douze » ; `feminine` : « vingt et une »."""
    if n < 0:
        return "moins " + fr_cardinal(-n, feminine)
    if n == 0:
        return "zéro"
    parts = []
    for size, name in ((10**9, "milliard"), (10**6, "million")):
        count, n = divmod(n, size)
        if count:
            parts.append(f"{fr_cardinal(count)} {name}{'s' if count > 1 else ''}")
    thousands, n = divmod(n, 1000)
    if thousands:
        parts.append("mille" if thousands == 1 else f"{_fr_below_1000(thousands, False)} mille")
    if n:
        parts.append(_fr_below_1000(n, True))
    text = " ".join(parts)
    return text[:-2] + "une" if feminine and text.endswith("un") else text


def fr_ordinal(n: int, feminine: bool = False) -> str:
    """19 → « dix-neuvième » ; 1 → « premier » (« première »)."""
    if n == 1:
        return "première" if feminine else "premier"
    words = re.sub(r"(vingt|cent|million|milliard)s$", r"\1", fr_cardinal(n))
    if words.endswith("cinq"):
        return words + "uième"
    if words.endswith("neuf"):
        return words[:-1] + "vième"
    return (words[:-1] if words.endswith("e") else words) + "ième"


_EN_UNITS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
             "seventeen eighteen nineteen").split()
_EN_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_EN_ORDINAL = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
               "twelve": "twelfth"}


def _en_below_100(n: int) -> str:
    if n < 20:
        return _EN_UNITS[n]
    tens, unit = divmod(n, 10)
    return _EN_TENS[tens] + (f"-{_EN_UNITS[unit]}" if unit else "")


def en_cardinal(n: int) -> str:
    if n < 0:
        return "minus " + en_cardinal(-n)
    if n < 100:
        return _en_below_100(n)
    parts = []
    for size, name in ((10**9, "billion"), (10**6, "million"), (1000, "thousand"), (100, "hundred")):
        count, n = divmod(n, size)
        if count:
            parts.append(f"{en_cardinal(count)} {name}")
    if n:
        parts.append(_en_below_100(n))
    return " ".join(parts)


def en_year(n: int) -> str:
    """1992 → « nineteen ninety-two », 1900 → « nineteen hundred », 1905 → « nineteen oh five », 2005 → « two thousand
    five », 2024 → « twenty twenty-four »."""
    if 2000 <= n <= 2009:
        return en_cardinal(n)
    high, low = divmod(n, 100)
    if low == 0:
        return f"{en_cardinal(high)} hundred"
    return f"{en_cardinal(high)} " + (f"oh {_EN_UNITS[low]}" if low < 10 else _en_below_100(low))


def en_ordinal(n: int) -> str:
    words = en_cardinal(n)
    last = re.search(r"[a-z]+$", words)
    assert last
    word = last.group(0)
    new = _EN_ORDINAL.get(word) or (word[:-1] + "ieth" if word.endswith("y") else word + "th")
    return words[: last.start()] + new


# ---------------------------------------------------------------------------------------------------------------------
# Chiffres → mots (voix)
# ---------------------------------------------------------------------------------------------------------------------

_FR_INT = r"\d{1,3}(?:[   .]\d{3})+(?!\d)|\d+"  # 1 350, 10 000, 1.350 (groupes de 3) ou chiffres collés
_EN_INT = r"\d{1,3}(?:,\d{3})+(?!\d)|\d+"
# symbole → (singulier, pluriel, féminin) ; les plus longs d'abord : « km² » avant « km » et « m »
_FR_UNIT_WORDS = {
    "%": ("pour cent", "pour cent", False),
    "M€": ("million d'euros", "millions d'euros", False),
    "Mds€": ("milliard d'euros", "milliards d'euros", False),
    "Md€": ("milliard d'euros", "milliards d'euros", False),
    "€": ("euro", "euros", False),
    "$": ("dollar", "dollars", False),
    "km²": ("kilomètre carré", "kilomètres carrés", False),
    "m²": ("mètre carré", "mètres carrés", False),
    "km/h": ("kilomètre heure", "kilomètres heure", False),
    "km": ("kilomètre", "kilomètres", False),
    "cm": ("centimètre", "centimètres", False),
    "mm": ("millimètre", "millimètres", False),
    "kg": ("kilo", "kilos", False),
    "°C": ("degré", "degrés", False),
    "°": ("degré", "degrés", False),
    "min": ("minute", "minutes", True),
    "m": ("mètre", "mètres", False),
}
_EN_UNIT_WORDS = {
    "%": ("percent", "percent"),
    "€": ("euro", "euros"),
    "km": ("kilometer", "kilometers"),
    "kg": ("kilogram", "kilograms"),
    "mph": ("mile per hour", "miles per hour"),
    "°C": ("degree Celsius", "degrees Celsius"),
    "°F": ("degree Fahrenheit", "degrees Fahrenheit"),
    "°": ("degree", "degrees"),
    "ft": ("foot", "feet"),
    "m": ("meter", "meters"),
}


def _units_rx(units: dict[str, object]) -> str:
    return "|".join(re.escape(u) for u in units)


_FR_NUMBER = re.compile(
    rf"(?<![\w,.])(?P<int>{_FR_INT})(?:[,.](?P<dec>\d+))?"
    rf"(?:(?P<ord>ères?|res?|ers?|èmes?|ndes?|nds?|es?)(?!\w)"
    rf"|[   ]?(?P<unit>{_units_rx(_FR_UNIT_WORDS)})(?![\w²/])|(?!\w))"
)
_EN_NUMBER = re.compile(
    rf"(?<![\w,.])(?P<int>{_EN_INT})(?:\.(?P<dec>\d+))?"
    rf"(?:(?P<ord>st|nd|rd|th|s)(?!\w)|[  ]?(?P<unit>{_units_rx(_EN_UNIT_WORDS)})(?![\w²/])|(?!\w))"
)
_FR_TIME = re.compile(r"(?<![\w,.])(?P<h>[01]?\d|2[0-4]) ?h ?(?P<min>[0-5]\d)?(?!\w)")  # 14 h 30, 14h30, 3 h
_RANGE = re.compile(r"(?<![\w,.])(\d{3,4}) ?[-–—] ?(\d{2,4})(?![-–\d])")  # 1914-1918
_EN_DOLLAR = re.compile(r"\$ ?(\d[\d,]*(?:\.\d+)?)((?: (?:thousand|million|billion|trillion))?)")
_NEXT_WORD = re.compile(r"[   ]*([^\W\d_]+)")
# Noms féminins courants dans les récits : « 21 personnes » se dit « vingt et une personnes »
_FEMININE = re.compile(
    r"(personne|victime|fois|année|heure|minute|seconde|semaine|journée|nuit|tonne|femme|fille|famille|vie|maison|ville|île|"
    r"pièce|marche|écluse|espèce|voiture|étoile|chambre|page|lettre|guerre|bataille|armée|bombe|tentative|vague|fenêtre|"
    r"porte|colonne|statue|pyramide|tombe|salle|cloche|route|rue|église|mine|galerie|barque|épave|victoire|dent|patte|tête|"
    r"mission|expédition|découverte|explosion|tempête|avalanche|inondation|éruption)s?"
)


def _next_word(text: str, pos: int) -> str:
    m = _NEXT_WORD.match(text, pos)
    return m.group(1).lower() if m else ""


def _fr_decimals(digits: str) -> str:
    """Partie après la virgule : « 05 » → « zéro cinq », « 14 » → « quatorze »."""
    rest = digits.lstrip("0")
    return " ".join(["zéro"] * (len(digits) - len(rest)) + ([fr_cardinal(int(rest))] if rest else []))


def _fr_number(m: re.Match[str]) -> str:
    n = int(re.sub(r"\D", "", m["int"]))
    suffix = m["ord"]
    if suffix:
        if suffix.startswith("nd"):
            word = "seconde" if suffix.startswith("nde") else "second"
        else:
            word = fr_ordinal(n, feminine=suffix.startswith(("re", "ère")))
        return word + ("s" if suffix.endswith("s") else "")
    dec = (m["dec"] or "").rstrip("0")
    unit = m["unit"]
    feminine = _FR_UNIT_WORDS[unit][2] if unit else bool(_FEMININE.fullmatch(_next_word(m.string, m.end())))
    words = fr_cardinal(n, feminine and not dec) + (f" virgule {_fr_decimals(dec)}" if dec else "")
    if unit:
        singular, plural, _ = _FR_UNIT_WORDS[unit]
        words += " " + (singular if n < 2 else plural)  # « 1,5 mètre » : singulier en dessous de 2
    return words


def _fr_time(m: re.Match[str]) -> str:
    h, minutes = int(m["h"]), int(m["min"] or 0)
    return f"{fr_cardinal(h, True)} heure{'s' if h > 1 else ''}" + (f" {fr_cardinal(minutes, True)}" if minutes else "")


def _en_number(m: re.Match[str]) -> str:
    n = int(m["int"].replace(",", ""))
    suffix, dec, unit = m["ord"], m["dec"], m["unit"]
    if suffix == "s":  # 1990s, 80s
        words = en_year(n) if 1000 <= n <= 2099 else en_cardinal(n)
        return re.sub(r"y$", "ie", words) + "s"
    if suffix:
        return en_ordinal(n)
    year = not dec and not unit and "," not in m["int"] and 1100 <= n <= 2099
    words = en_year(n) if year else en_cardinal(n)
    if dec:
        words += " point " + " ".join(_EN_UNITS[int(d)] for d in dec)
    if unit:
        one, many = _EN_UNIT_WORDS[unit]
        words += " " + (one if n == 1 and not dec else many)
    return words


def spoken(text: str, lang: str = "fr") -> str:
    """Le texte tel que la voix doit le dire : nombres, années, décimales, pourcentages, heures, ordinaux et unités en
    toutes lettres (« En 1992, 1 350 tonnes » → « En mille neuf cent quatre-vingt-douze, mille trois cent cinquante
    tonnes »). Un texte sans chiffre revient tel quel."""
    if not text or not any(ch.isdigit() for ch in text):
        return text
    if lang == "en":
        text = _EN_DOLLAR.sub(r"\1\2 dollars", text)
        return _EN_NUMBER.sub(_en_number, _RANGE.sub(r"\1 to \2", text))
    text = _FR_TIME.sub(_fr_time, _RANGE.sub(r"\1 à \2", text))
    return _FR_NUMBER.sub(_fr_number, text)


# ---------------------------------------------------------------------------------------------------------------------
# Mots → chiffres (écran)
# ---------------------------------------------------------------------------------------------------------------------

_FR_SMALL = {w: i for i, w in enumerate(_FR_UNITS)} | {
    "une": 1, "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
    "septante": 70, "huitante": 80, "octante": 80, "nonante": 90,
}
_FR_BIG = {"million": 10**6, "millions": 10**6, "milliard": 10**9, "milliards": 10**9}
_FR_WORDS = set(_FR_SMALL) | {"cent", "cents", "mille"} | set(_FR_BIG)
# Mots qui annoncent une année (« en 1992 », « l'an 1000 ») : elle s'écrit sans espace
_YEAR_BEFORE = {
    "en", "depuis", "dès", "vers", "an", "année", "années", "avant", "après", "fin", "début", "milieu", "printemps", "été",
    "automne", "hiver", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
    "novembre", "décembre",
}
# Mots suivis d'un numéro : « Jour un » est « Jour 1 », pas un article
_LABELS = {"jour", "page", "chapitre", "épisode", "saison", "acte", "étape", "numéro", "tome", "partie", "niveau", "an"}
# Mots qui ne sont pas le nom compté après un nombre (« de 1914 à 1918 », « en 1992 les travaux »)
_NOT_COUNTED = {
    "à", "au", "aux", "et", "ou", "puis", "avant", "après", "quand", "lorsque", "les", "le", "la", "un", "une", "des", "du",
    "de", "il", "elle", "ils", "elles", "on", "ce", "cet", "cette", "ces", "se", "sa", "son", "ses", "leur", "leurs", "mais",
    "donc", "pour", "par", "sur", "dans", "avec", "sans", "sous", "tout", "tous", "toute", "toutes", "déjà", "encore",
    "enfin", "alors", "que", "qui", "où", "entre", "contre", "vers", "chez", "plus", "moins", "seulement", "même", "aussi",
    "y", "en", "ne", "jusqu", "jusque",
}


def _ordinal_stem(word: str) -> str | None:
    """« neuvième » → « neuf », « unième » → « un » ; None si ce n'est pas un ordinal en -ième."""
    m = re.fullmatch(r"(.+?)ièmes?", word)
    if not m:
        return None
    base = m.group(1)
    for cand in (base, base + "e", base[:-1] if base.endswith("u") else "", base[:-1] + "f" if base.endswith("v") else ""):
        if cand in _FR_WORDS:
            return cand
    return None


def _fmt_int(n: int, group4: bool = False) -> str:
    """Groupes de 3 chiffres séparés par une espace insécable à partir de 5 chiffres (« 10 000 ») ; 4 chiffres collés
    (« 1992 ») sauf `group4`, une quantité (« 1 350 tonnes »)."""
    s = str(n)
    if len(s) < 4 or (len(s) == 4 and not group4):
        return s
    head = len(s) % 3 or 3
    return NBSP.join([s[:head], *(s[k : k + 3] for k in range(head, len(s), 3))])


@dataclass(frozen=True)
class _Value:
    n: int
    big: str = ""  # « millions », « milliard » : gardé en lettres après son multiple (« 3 millions »)
    ordinal: str = ""  # « e » ou « es » (« 19e siècle »)

    def shown(self, group4: bool = False) -> str:
        if self.ordinal:
            return f"{self.n}{self.ordinal}"
        if self.big:
            return f"{_fmt_int(self.n // _FR_BIG[self.big])} {self.big}"
        return _fmt_int(self.n, group4)


def _can_add(low: int, v: int) -> bool:
    """Le nombre en cours finit par `low` (moins de 100) : peut-on lui ajouter `v` (« vingt » + « deux ») ?"""
    if low == 0:
        return v < 100
    if low == 10:  # dix-sept, dix-huit, dix-neuf, cent dix-sept
        return 7 <= v <= 9
    if low in (20, 30, 40, 50, 70, 90):  # vingt-deux, soixante-dix-sept, quatre-vingt-dix-neuf
        return 1 <= v <= 9
    if low in (60, 80):  # soixante-douze, quatre-vingt-onze
        return 1 <= v <= 19
    return False


def _fr_value(parts: Sequence[str]) -> _Value | None:
    """Valeur d'une suite de mots-nombres en minuscules (« dix-neuf cent quatre-vingt-douze » → 1992) ; None si la suite
    n'est pas un nombre bien formé (« deux trois »), ce qui arrête le nombre au mot précédent."""
    words = list(parts)
    ordinal = ""
    if words and words[-1].endswith(("ième", "ièmes")):
        stem = _ordinal_stem(words[-1])
        if stem is None:
            return None
        ordinal, words[-1] = ("es" if words[-1].endswith("s") else "e"), stem
    if not any(w != "et" for w in words):
        return None
    total = current = 0
    sizes: list[int] = []  # mille, million, milliard déjà vus : chacun plus petit que le précédent
    for k, w in enumerate(words):
        low = current % 100
        if w == "et":  # vingt et un, soixante et onze
            if low not in (20, 30, 40, 50, 60) or words[k + 1 : k + 2] not in (["un"], ["une"], ["onze"]):
                return None
        elif w in _FR_SMALL:
            v = _FR_SMALL[w]
            if v == 20 and low == 4 and k and words[k - 1] == "quatre":
                current += 76  # quatre-vingt(s)
            elif _can_add(low, v):
                current += v
            else:
                return None
        elif w in ("cent", "cents"):
            if current == 0:
                current = 100
            elif 2 <= current <= 9 or 11 <= current <= 19:  # deux cents ; dix-neuf cent (années), treize cent cinquante
                current *= 100
            else:
                return None
        elif w == "mille":
            if current >= 1000 or (sizes and sizes[-1] <= 1000):
                return None
            total, current = total + (current or 1) * 1000, 0
            sizes.append(1000)
        elif w in _FR_BIG:
            size = _FR_BIG[w]
            if not current or (sizes and sizes[-1] <= size):
                return None
            total, current = total + current * size, 0
            sizes.append(size)
        else:
            return None
    big = words[-1] if words[-1] in _FR_BIG and len(sizes) == 1 and not ordinal else ""
    return _Value(total + current, big, ordinal)


class _Tok(NamedTuple):
    text: str
    lead: str  # ponctuation ouvrante (« , ( , ")
    elide: str  # « d' », « l' », « qu' »
    core: str
    trail: str  # ponctuation fermante (, . ! ? » …)
    parts: tuple[str, ...]  # mots-nombres en minuscules (« cinquante-deux » → cinquante, deux) ; vide si ce n'en est pas


_TOKEN = re.compile(
    r"(?P<lead>[«“\"'(\[]*)(?P<elide>(?:[dlnmstcj]|qu|jusqu|lorsqu|puisqu)['’])?"
    r"(?P<core>[^\W\d_]+(?:-[^\W\d_]+)*)(?P<trail>[»”\"')\].,;:!?…]*)",
    re.IGNORECASE,
)


def _tok(text: str) -> _Tok:
    m = _TOKEN.fullmatch(text)
    if not m:
        return _Tok(text, "", "", "", "", ())
    parts = tuple(m["core"].lower().split("-"))
    head, last = parts[:-1], parts[-1]
    number = all(p in _FR_WORDS or p == "et" for p in head) and (last in _FR_WORDS or _ordinal_stem(last) is not None)
    return _Tok(text, m["lead"], m["elide"] or "", m["core"], m["trail"], parts if number and last != "et" else ())


def _run(toks: Sequence[_Tok], i: int) -> tuple[int, _Value] | None:
    """Le plus long nombre qui commence au mot i : (fin exclue, valeur) ; « et » reste entre deux mots-nombres."""
    if not toks[i].parts:
        return None
    parts, j = list(toks[i].parts), i + 1
    value = _fr_value(parts)
    if value is None:
        return None
    while j < len(toks) and not toks[j - 1].trail:
        nxt = toks[j]
        if nxt.lead or nxt.elide:
            break
        if nxt.core.lower() == "et" and not nxt.trail and j + 1 < len(toks) and toks[j + 1].parts and not toks[j + 1].lead:
            cand, width = [*parts, "et", *toks[j + 1].parts], 2
        elif nxt.parts:
            cand, width = [*parts, *nxt.parts], 1
        else:
            break
        v = _fr_value(cand)
        if v is None:
            break
        parts, value, j = cand, v, j + width
    return j, value


def _plain(tok: _Tok, word: str) -> bool:
    return tok.core.lower() == word and not tok.lead and not tok.elide


def _ends_sentence(text: str) -> bool:
    return bool(re.search(r"[.!?…:][»”\"')\]]*$", text))


def _keep_letters(toks: Sequence[_Tok], i: int, j: int, value: _Value) -> bool:
    """Un mot-nombre qui n'est pas un nombre à afficher : article, adjectif, pronom, « pour cent », nom propre."""
    first = toks[i]
    single = j - i == 1 and len(first.parts) == 1
    before = [t.core.lower() for t in toks[max(0, i - 2) : i]]
    if single and first.parts[0] in ("un", "une", "zéro"):  # « un homme », « l'un d'eux », « partir de zéro »
        return not (i > 0 and not toks[i - 1].trail and before[-1] in _LABELS)  # mais « Jour 1 », « le numéro 1 »
    if single and first.parts[0] == "cent" and before[-1:] == ["pour"]:  # « 30 pour cent »
        return True
    if single and first.parts[0] == "neuf":  # « neuf ans » oui, « un navire neuf » non
        nxt = toks[j].core if j < len(toks) and not first.trail else ""
        return not (nxt.isalpha() and nxt.islower() and nxt.endswith(("s", "x")))
    if single and value.n < 10 and not value.ordinal:
        if before[-2:] in (["tous", "les"], ["toutes", "les"]):  # « tous les deux »
            return True
        if before[-1:] == ["les"] and (first.trail or j == len(toks)):  # « entre les deux, »
            return True
    core = first.core  # majuscule au milieu d'une phrase : nom propre (« les Trois Mousquetaires »)
    return core[:1].isupper() and not core.isupper() and i > 0 and not _ends_sentence(toks[i - 1].text)


def _is_quantity(toks: Sequence[_Tok], i: int, j: int) -> bool:
    """Un nombre suivi du nom qu'il compte (« 1 350 tonnes ») ; une année (« en 1992 », « de 1914 à 1918 ») non."""
    if i > 0 and not toks[i - 1].trail and toks[i - 1].core.lower() in _YEAR_BEFORE:
        return False
    if j >= len(toks) or toks[j - 1].trail:
        return False
    nxt = toks[j]
    return nxt.core.isalpha() and nxt.core.islower() and not nxt.lead and not nxt.elide and nxt.core not in _NOT_COUNTED


def _spans(texts: Sequence[str]) -> list[tuple[int, int, str]]:
    """Nombres écrits en lettres dans une suite de mots : (premier mot, fin exclue, texte en chiffres, ponctuation
    comprise)."""
    toks = [_tok(t) for t in texts]
    out: list[tuple[int, int, str]] = []
    i = 0
    while i < len(toks):
        found = _run(toks, i)
        if found is None:
            i += 1
            continue
        j, value = found
        shown, trail, extended = value.shown(_is_quantity(toks, i, j)), toks[j - 1].trail, False
        simple = not toks[j - 1].trail and not value.ordinal and not value.big
        if simple and j + 1 < len(toks) and _plain(toks[j], "pour") and not toks[j].trail and _plain(toks[j + 1], "cent"):
            shown, trail, j, extended = f"{value.shown()}{NBSP}%", toks[j + 1].trail, j + 2, True  # trente pour cent → 30 %
        elif simple and j + 1 < len(toks) and _plain(toks[j], "virgule") and not toks[j].trail:
            dec = _run(toks, j + 1)  # deux virgule cinq milliards → 2,5 milliards
            if dec and not dec[1].ordinal:
                d = dec[1]
                digits = str(d.n // _FR_BIG[d.big]) if d.big else str(d.n)
                shown = f"{value.shown()},{digits}" + (f" {d.big}" if d.big else "")
                trail, j, extended = toks[dec[0] - 1].trail, dec[0], True
        if not extended and _keep_letters(toks, i, j, value):
            i = j
            continue
        elide = toks[i].elide
        if elide[:1].lower() in ("d", "q") and toks[i].parts[0] in ("un", "une"):  # plus d'un million → plus de 1 million
            elide = ("de " if elide[:1].lower() == "d" else "que ")
            elide = elide.capitalize() if toks[i].elide[:1].isupper() else elide
        out.append((i, j, f"{toks[i].lead}{elide}{shown}{trail}"))
        i = j
    return out


_GROUPS = re.compile(r"(?<![\d,.])(?:\d{1,3}(?:[   ]\d{3})+|\d{5,})(?!\d)")


def _regroup(text: str) -> str:
    """Chiffres écrits par le LLM : « 10000 » → « 10 000 », « 1 350 » garde son espace, devenue insécable (le nombre ne
    se coupe pas en fin de ligne) ; « 1992 » et les décimales ne bougent pas."""
    return _GROUPS.sub(lambda m: _fmt_int(int(re.sub(r"\D", "", m.group(0))), group4=True), text)


def to_digits(text: str, lang: str = "fr") -> str:
    """Le texte tel qu'il s'affiche : nombres écrits en lettres passés en chiffres (« Huit cent cinquante-deux morts »
    → « 852 morts », « au dix-neuvième siècle » → « au 19e siècle »), chiffres groupés à la française. Hors
    français : inchangé."""
    if not text or lang != "fr":
        return text
    words = [w for w in re.split(r"[ \t\r\n]+", text.strip()) if w]
    spans = _spans(words)
    if not spans:
        return _regroup(text)
    out, k = [], 0
    for i, j, shown in spans:
        out += [*words[k:i], shown]
        k = j
    return _regroup(" ".join([*out, *words[k:]]))


def merge_timed(words: Sequence[WordTiming], lang: str = "fr") -> list[WordTiming]:
    """Mots horodatés des sous-titres (narration d'avant la règle) : un nombre dit en plusieurs mots (« huit », « cent »,
    « cinquante-deux ») devient un seul mot en chiffres (« 852 ») qui dure du début du premier à la fin du dernier."""
    if lang != "fr" or not words:
        return list(words)
    from .models import WordTiming

    def regrouped(w: WordTiming) -> WordTiming:
        text = _regroup(w.text)
        return w if text == w.text else w.model_copy(update={"text": text})

    out: list[WordTiming] = []
    k = 0
    for i, j, shown in _spans([w.text for w in words]):
        out += [regrouped(w) for w in words[k:i]]
        out.append(WordTiming(text=shown, start=words[i].start, end=words[j - 1].end))
        k = j
    return out + [regrouped(w) for w in words[k:]]


def script_to_digits(script: ScriptV1) -> ScriptV1:
    """Nombres en chiffres dans ce que le script affiche ou fait dire (narration, textes à l'écran, titre d'accroche,
    titre YouTube) ; en place, comme normalize_story. La voix les relit en lettres (spoken)."""
    for s in script.scenes:
        s.narration = {lang: to_digits(t, lang) for lang, t in s.narration.items()}  # type: ignore[misc]
        s.on_screen_text = {lang: to_digits(t, lang) for lang, t in s.on_screen_text.items()}  # type: ignore[misc]
    script.hook_title = {lang: to_digits(t, lang) for lang, t in script.hook_title.items()}  # type: ignore[misc]
    for lang, meta in script.metadata.items():
        meta.title = to_digits(meta.title, lang)
    return script


_WORD = re.compile(r"(?<!\S)\d{1,3}(?:[   ]\d{3})+(?!\d)[^ \t\r\n]*|[^ \t\r\n]+")


def tokens(text: str) -> list[str]:
    """Mots d'un texte, séparés par les espaces ; un nombre écrit par groupes (« 1 350 », « 10 000 ») reste un mot."""
    return _WORD.findall(text or "")
