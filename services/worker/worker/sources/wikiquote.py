"""Wikiquote comme réserve de vraies citations d'auteurs (série « Citations d'auteurs », docs/70).

Demande de Luca (12/10) : des citations fortes de personnalités connues (Einstein, Maupassant, Hugo…), avec leur nom.
Le piège du format : les comptes de citations collent de fausses phrases sur Einstein ou Aristote (docs/58). Wikiquote
range chaque citation avec sa source (œuvre, édition, page) et met à part celles qu'on ne peut pas sourcer
(« Citations rapportées », « attribuées », « apocryphes ») et celles qui parlent de l'auteur (« Citations sur… ») :
on ne garde que les premières.

API publique sans clé (`/w/api.php?action=parse`), mêmes règles que Wikipédia (sources/wikipedia.py) : User-Agent
avec un contact, une requête à la fois, pause entre les appels, cache local d'un mois par auteur
(DATA_DIR/sources/wikiquote/<lang>/<auteur>.json). Les textes de Wikiquote sont sous CC BY-SA 4.0 : la description
de la vidéo cite l'auteur, l'œuvre et Wikiquote (steps/seo.attribution).

Page d'un auteur : `<div class="citation">` (le texte, en français), parfois l'original et des précisions, puis
`<div class="ref">` (« Bel-Ami (1885), Guy de Maupassant, éd. Ollendorf, 1901, p. 159 »).
"""

from __future__ import annotations

import hashlib
import html
import json
import random
import re
import time
from collections.abc import Collection, Sequence
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import structlog

from ..models import Fact, SourceRef

log = structlog.get_logger(__name__)

# Auteurs connus d'un public français de 16 à 35 ans dont la page Wikiquote existe (vérifié le 12/10) ; réglable par
# série (source_config.authors). Ni homme politique vivant ni personnalité clivante
AUTHORS = (
    "Victor Hugo", "Guy de Maupassant", "Albert Einstein", "Marc Aurèle", "Sénèque", "Épictète", "Voltaire", "Molière",
    "Jean de La Fontaine", "Blaise Pascal", "Michel de Montaigne", "François de La Rochefoucauld", "Charles Baudelaire",
    "Arthur Rimbaud", "Honoré de Balzac", "Émile Zola", "Gustave Flaubert", "Alexandre Dumas", "Stendhal", "George Sand",
    "Jules Verne", "Marcel Proust", "Oscar Wilde", "William Shakespeare", "Léon Tolstoï", "Friedrich Nietzsche",
    "Confucius", "Lao Tseu", "Socrate", "Platon", "Aristote", "Mohandas Karamchand Gandhi", "Charles Darwin",
    "Marie Curie", "Léonard de Vinci", "Antoine de Saint-Exupéry", "Sigmund Freud", "Albert Camus", "Jean-Paul Sartre",
    "Simone de Beauvoir", "Paul Verlaine", "Alfred de Musset", "Jean-Jacques Rousseau", "Denis Diderot", "Montesquieu",
    "Franz Kafka", "Rainer Maria Rilke", "Gibran Khalil Gibran", "Mark Twain", "Charlie Chaplin", "Winston Churchill",
    "Abraham Lincoln", "Martin Luther King", "Nelson Mandela", "Mère Teresa", "Frida Kahlo", "Coco Chanel",
    "Vincent van Gogh", "Pablo Picasso", "Jean Cocteau", "Paul Éluard", "Louis Aragon", "Jacques Prévert", "Boris Vian",
    "Romain Gary", "Marguerite Yourcenar", "Colette", "Anatole France", "Alphonse de Lamartine", "Gérard de Nerval",
    "Pierre Corneille", "Jean Racine", "Sun Zi", "Cicéron", "Ovide", "Fernando Pessoa", "Ernest Hemingway",
    "Gabriel García Márquez", "Paulo Coelho", "Steve Jobs", "Épicure", "Nicolas Machiavel", "Arthur Schopenhauer",
    "Søren Kierkegaard", "Emil Cioran", "Christian Bobin", "Joseph Joubert", "Jules Renard", "Sacha Guitry",
    "Hippocrate", "Héraclite d'Éphèse", "Diogène de Sinope", "Baruch Spinoza", "Emmanuel Kant", "Jean de La Bruyère",
    "Johann Wolfgang von Goethe", "Siddhartha Gautama", "Tenzin Gyatso",
)  # fmt: skip
# Les aphoristes que Luca voit marcher (12/10 : Nietzsche, Coelho, Einstein, Aristote, Hippocrate) et leurs pareils :
# la moitié des auteurs de chaque lot vient d'ici
PRIORITY = (
    "Friedrich Nietzsche", "Paulo Coelho", "Albert Einstein", "Aristote", "Hippocrate", "Marc Aurèle", "Sénèque",
    "Épictète", "Confucius", "Lao Tseu", "Oscar Wilde", "François de La Rochefoucauld", "Victor Hugo", "Albert Camus",
    "Antoine de Saint-Exupéry", "Emil Cioran", "Arthur Schopenhauer", "Blaise Pascal", "Michel de Montaigne",
    "Socrate", "Siddhartha Gautama", "Johann Wolfgang von Goethe", "Jean de La Bruyère",
)  # fmt: skip
# Nom affiché sous la citation quand le titre de la page est un nom d'état civil
DISPLAY = {
    "Mohandas Karamchand Gandhi": "Gandhi",
    "Gibran Khalil Gibran": "Khalil Gibran",
    "Sun Zi": "Sun Tzu",
    "Héraclite d'Éphèse": "Héraclite",
    "Diogène de Sinope": "Diogène",
    "Johann Wolfgang von Goethe": "Goethe",
    "Siddhartha Gautama": "Bouddha",
    "Tenzin Gyatso": "Le dalaï-lama",
}
# Sections écartées : citations non sourcées par l'auteur lui-même, ou qui parlent de lui, et l'appareil de la page
EXCLUDED = re.compile(
    r"rapport|attribu|apocryph|douteu|\bsur\b|au sujet|à propos|concernant|voir aussi|liens|notes|références|"
    r"bibliographie|articles connexes|sources",
    re.I,
)
# Celles qui marchent sont courtes (« L'ignorant affirme, le savant doute, le sage réfléchit », 7 mots) : 5 à 28 mots
WORDS = (5, 28)
CHARS_MAX = 180
CACHE_DAYS = 30
_HEADING = re.compile(r'<div class="mw-heading mw-heading([2-4])">(.*?)</div>', re.S)
_CITATION = re.compile(r'<div class="citation">(.*?)</div>', re.S)
_REF = re.compile(r'<div class="ref">(.*?)</div>', re.S)
_LABEL = re.compile(r"^([A-ZÀ-Ý][\w.'’-]*(?: [\w.'’-]+){0,3}) ?: ")


def is_dialogue(text: str) -> bool:
    """Réplique d'une pièce ou d'un film (« Alceste : … », « Le président Beaufort : … ») ; « Deux choses sont
    infinies : … » n'en est pas une (aucun nom propre avant les deux-points)."""
    m = _LABEL.match(text)
    if not m:
        return False
    ws = m.group(1).split()
    return len(ws) == 1 or any(w[:1].isupper() for w in ws[1:])


@dataclass
class Quote:
    text: str
    author: str  # nom affiché sous la citation
    page: str  # titre de la page Wikiquote
    ref: str  # œuvre, édition, page
    url: str
    lang: str = "fr"
    revision: int | None = None

    @property
    def key(self) -> str:
        """Identité stable d'une citation (déjà utilisée ou non) : son texte sans ponctuation ni casse."""
        return hashlib.sha1(norm(self.text).encode()).hexdigest()[:16]

    def to_ref(self) -> SourceRef:
        return SourceRef(title=self.author, url=self.url, lang=self.lang, kind="wikiquote", revision=self.revision)

    def facts(self) -> list[Fact]:
        """Ce que garde le concept (concepts.facts) : la citation mot pour mot, puis sa source."""
        return [Fact(claim=self.text, source=0), Fact(claim=self.ref, source=0)]


def norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


def clean_html(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", fragment)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_page(page_html: str, author: str, page: str, url: str, lang: str = "fr", revision: int | None = None) -> list[Quote]:
    """Citations sourcées d'une page d'auteur : celles des sections gardées (EXCLUDED écarte les autres, sous-sections
    comprises), chacune avec la première référence qui la suit."""
    cuts = [(m.start(), int(m.group(1)), clean_html(m.group(2))) for m in _HEADING.finditer(page_html)]
    excluded_at: list[tuple[int, bool]] = []  # (position, section écartée ?)
    levels: dict[int, bool] = {}
    for pos, level, title in cuts:
        levels = {k: v for k, v in levels.items() if k < level}
        levels[level] = bool(EXCLUDED.search(title))
        excluded_at.append((pos, any(levels.values())))

    def excluded(pos: int) -> bool:
        state = False
        for p, ex in excluded_at:
            if p > pos:
                break
            state = ex
        return state

    quotes: list[Quote] = []
    cites = list(_CITATION.finditer(page_html))
    for k, m in enumerate(cites):
        if excluded(m.start()):
            continue
        stop = cites[k + 1].start() if k + 1 < len(cites) else len(page_html)
        ref = _REF.search(page_html, m.end(), stop)
        if not ref:  # sans référence : non sourcée
            continue
        quotes.append(Quote(clean_html(m.group(1)), author, page, clean_html(ref.group(1)), url, lang=lang, revision=revision))
    return quotes


def usable(q: Quote) -> bool:
    """Une citation qui se lit seule sur une image : 6 à 40 mots, pas une réplique de film ni un extrait tronqué au
    début, sans appel de note."""
    n = len(q.text.split())
    if not WORDS[0] <= n <= WORDS[1] or len(q.text) > CHARS_MAX:
        return False
    if is_dialogue(q.text) or q.text.startswith(("[…]", "[...]", "…")) or re.search(r"\[\d+\]", q.text):
        return False
    return True


class WikiquoteClient:
    def __init__(self, lang: str = "fr", user_agent: str = "", timeout_s: float = 20.0, pause_s: float = 0.25) -> None:
        self.lang = lang
        self.headers = {"User-Agent": user_agent or "yt2-worker/0.1", "Accept": "application/json"}
        self.timeout_s, self.pause_s = timeout_s, pause_s
        self.api = f"https://{lang}.wikiquote.org/w/api.php"

    def page_url(self, page: str) -> str:
        return f"https://{self.lang}.wikiquote.org/wiki/{quote(page.replace(' ', '_'))}"

    def author_quotes(self, page: str) -> list[Quote]:
        r = httpx.get(
            self.api,
            params={"action": "parse", "page": page, "prop": "text|revid", "redirects": 1, "format": "json"},
            headers=self.headers,
            timeout=self.timeout_s,
            follow_redirects=True,
        )
        r.raise_for_status()
        time.sleep(self.pause_s)
        data = r.json().get("parse") or {}
        title = data.get("title") or page
        body = (data.get("text") or {}).get("*", "")
        return parse_page(body, DISPLAY.get(title, title), title, self.page_url(title), self.lang, data.get("revid"))


def cached_quotes(client: WikiquoteClient, page: str, cache_dir: Path, today: date | None = None) -> list[Quote]:
    """Citations d'un auteur, lues sur Wikiquote une fois par mois au plus ; [] si la page est introuvable."""
    today = today or date.today()
    path = cache_dir / client.lang / f"{norm(page).replace(' ', '_')}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if date.fromisoformat(data["fetched"]) > today - timedelta(days=CACHE_DAYS):
            return [Quote(**q) for q in data["quotes"]]
    try:
        quotes = client.author_quotes(page)
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("wikiquote.page_illisible", page=page, error=str(exc)[:200])
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fetched": today.isoformat(), "quotes": [asdict(q) for q in quotes]}, ensure_ascii=False), encoding="utf-8"
    )
    return quotes


def candidates(
    client: WikiquoteClient,
    cache_dir: Path,
    *,
    authors: Sequence[str] = AUTHORS,
    used: Collection[str] = (),
    recent_authors: Collection[str] = (),
    n_authors: int = 10,
    per_author: int = 5,
    seed: str | None = None,
    priority: Sequence[str] = PRIORITY,
) -> list[Quote]:
    """Citations proposées à l'agent idées : `n_authors` auteurs tirés au hasard, la moitié parmi `priority` (les
    aphoristes qui marchent), ceux des dernières vidéos en dernier ; `per_author` citations utilisables et jamais faites
    (`used` : Quote.key) chacun, les plus courtes d'abord."""
    rng = random.Random(seed)

    def shuffled(names: Sequence[str]) -> list[str]:
        out = list(names)
        rng.shuffle(out)
        out.sort(key=lambda a: a in recent_authors)  # tri stable : le hasard reste, les auteurs récents passent après
        return out

    first = shuffled([a for a in priority if a in authors])
    rest = shuffled([a for a in authors if a not in first])
    half = (n_authors + 1) // 2
    order = first[:half] + rest + first[half:]  # si un auteur prioritaire n'a plus rien, les autres prennent sa place
    out: list[Quote] = []
    taken = 0
    for page in order:
        if taken >= n_authors:
            break
        fresh = [q for q in cached_quotes(client, page, cache_dir) if usable(q) and q.key not in used]
        if not fresh:
            continue
        rng.shuffle(fresh)
        fresh.sort(key=lambda q: len(q.text.split()) > 16)  # les plus courtes d'abord, au hasard entre elles
        out += fresh[:per_author]
        taken += 1
    return out


def material_text(quotes: Sequence[Quote]) -> str:
    """Les citations numérotées, telles que l'agent idées les reçoit : [n] « texte » — auteur (œuvre)."""
    return "\n".join(f"[{i + 1}] « {q.text} » — {q.author} ({q.ref[:140]})" for i, q in enumerate(quotes))


def used_keys(rows: Sequence[dict[str, Any]]) -> set[str]:
    """Citations déjà proposées ou faites (concepts.facts[0] d'une série de citations d'auteurs)."""
    out: set[str] = set()
    for r in rows:
        facts = r.get("facts") or []
        if facts:
            out.add(hashlib.sha1(norm(str(facts[0].get("claim", ""))).encode()).hexdigest()[:16])
    return out
