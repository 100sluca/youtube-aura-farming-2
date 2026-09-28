"""Wikipédia comme matière première des séries documentaires : fil du jour, recherches, pages.

Deux API publiques, sans clé :
- REST (`/api/rest_v1/feed/featured/AAAA/MM/JJ`) : article du jour (tfa, absent sur fr), articles les plus
  lus la veille (mostread), éphéméride (onthisday) ;
- action (`/w/api.php`) : recherche plein texte, pages au hasard, extrait en texte brut avec URL et révision.

Chaque document garde titre, URL et numéro de révision : le concept cite ses sources (concepts.sources)
et la description YouTube les mentionne (textes sous CC BY-SA 4.0 : les faits sont libres, l'attribution
est due si le texte est repris). Règles Wikimedia respectées : User-Agent identifiable avec un contact,
une requête à la fois, pause entre les appels, cache local par jour (DATA_DIR/sources/wikipedia/<lang>/).

`daily_material()` assemble la matière d'une série selon sa configuration (series.source_config) :
    {"lang": "fr", "feeds": ["tfa", "onthisday", "mostread"], "mostread_max": 6, "onthisday_max": 4,
     "onthisday_max_year": 1995, "queries": ["animal venimeux", …], "queries_per_day": 2, "search_limit": 5,
     "random": 2, "min_words": 200, "exclude": "(film|série|album)"}
Les requêtes tournent avec le jour de l'année, pour ne pas ressortir les mêmes pages chaque jour. La regex
`exclude` s'applique au titre, au texte de l'éphéméride et à la description avant de lire la page, puis au
titre et à la description de la page.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import structlog

from ..models import Fact, SourceRef

log = structlog.get_logger(__name__)

DEFAULT_USER_AGENT = "yt2-worker/0.1 (https://github.com/100sluca/youtube-shorts-daily)"
LIST_PREFIXES = ("Liste ", "Listes ", "List of ", "Chronologie ", "Timeline of ")


@dataclass
class SourceDoc:
    title: str
    url: str
    lang: str
    extract: str
    kind: str = "page"  # tfa | mostread | onthisday | search | random | page
    revision: int | None = None
    description: str | None = None
    thumbnail: str | None = None
    note: str | None = None  # « Article du jour », « 155 697 lectures hier », « 21 septembre 1930 : … »

    @property
    def words(self) -> int:
        return len(self.extract.split())

    def to_ref(self) -> SourceRef:
        return SourceRef(title=self.title, url=self.url, lang=self.lang, kind="wikipedia", revision=self.revision)


class WikipediaClient:
    def __init__(self, lang: str = "fr", user_agent: str = DEFAULT_USER_AGENT, timeout_s: float = 20.0, pause_s: float = 0.25) -> None:
        self.lang = lang
        self.headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self.timeout_s, self.pause_s = timeout_s, pause_s
        self.rest = f"https://{lang}.wikipedia.org/api/rest_v1"
        self.api = f"https://{lang}.wikipedia.org/w/api.php"

    def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        r = httpx.get(url, params=params, headers=self.headers, timeout=self.timeout_s, follow_redirects=True)
        r.raise_for_status()
        time.sleep(self.pause_s)
        return r.json()

    def featured(self, day: date) -> dict[str, Any]:
        """Fil du jour : clés tfa (parfois absente), mostread, onthisday, image, news, dyk (en)."""
        try:
            return self._get(f"{self.rest}/feed/featured/{day:%Y/%m/%d}")
        except httpx.HTTPError as exc:
            log.warning("wikipedia.featured_failed", lang=self.lang, error=str(exc)[:200])
            return {}

    def search(self, query: str, limit: int = 8) -> list[str]:
        data = self._get(
            self.api,
            {"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "srnamespace": 0,
             "format": "json", "formatversion": 2, "utf8": 1},
        )
        return [h["title"] for h in data.get("query", {}).get("search", [])]

    def random_titles(self, n: int) -> list[str]:
        if n <= 0:
            return []
        data = self._get(
            self.api,
            {"action": "query", "generator": "random", "grnnamespace": 0, "grnlimit": n, "grnfilterredir": "nonredirects",
             "format": "json", "formatversion": 2},
        )
        return [p["title"] for p in data.get("query", {}).get("pages", [])]

    def page(self, title: str, chars: int = 3500) -> SourceDoc | None:
        """Texte brut de la page (coupé à `chars` sur une fin de phrase), URL canonique, révision, description."""
        data = self._get(
            self.api,
            {"action": "query", "titles": title, "redirects": 1, "prop": "extracts|info|revisions|description|pageimages",
             "explaintext": 1, "exsectionformat": "plain", "inprop": "url", "rvprop": "ids",
             "piprop": "thumbnail", "pithumbsize": 640, "format": "json", "formatversion": 2},
        )
        pages = data.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing") or not pages[0].get("extract"):
            return None
        p = pages[0]
        revs = p.get("revisions") or [{}]
        return SourceDoc(
            title=p["title"],
            url=p.get("canonicalurl") or p.get("fullurl") or f"https://{self.lang}.wikipedia.org/wiki/{p['title'].replace(' ', '_')}",
            lang=self.lang,
            extract=clip_text(p["extract"], chars),
            revision=revs[0].get("revid"),
            description=p.get("description"),
            thumbnail=(p.get("thumbnail") or {}).get("source"),
        )

    def langlink(self, title: str, lang: str) -> str | None:
        """Titre de la même page dans une autre langue (liens interlangues) ; None si elle n'existe pas."""
        data = self._get(
            self.api,
            {"action": "query", "titles": title, "redirects": 1, "prop": "langlinks", "lllang": lang,
             "format": "json", "formatversion": 2},
        )
        pages = data.get("query", {}).get("pages", [])
        links = (pages[0].get("langlinks") or []) if pages else []
        return links[0].get("title") if links else None

    def place(self, name: str) -> dict[str, Any] | None:
        """Coordonnées principales et identifiant Wikidata de la page `name` (titre exact, sinon premier résultat de la
        recherche) : la carte des récits s'en sert pour trouver le lieu dans OpenStreetMap (worker/maps.py)."""
        for title in (name, *self.search(name, 1)):
            data = self._get(
                self.api,
                {"action": "query", "titles": title, "redirects": 1, "prop": "coordinates|pageprops|info",
                 "ppprop": "wikibase_item", "inprop": "url", "format": "json", "formatversion": 2},
            )
            pages = data.get("query", {}).get("pages", [])
            if not pages or pages[0].get("missing"):
                continue
            p = pages[0]
            coords = [c for c in p.get("coordinates") or [] if c.get("globe", "earth") == "earth"]
            return {
                "title": p["title"], "url": p.get("fullurl"), "qid": (p.get("pageprops") or {}).get("wikibase_item"),
                "lat": coords[0]["lat"] if coords else None, "lon": coords[0]["lon"] if coords else None,
            }
        return None


def clip_text(text: str, chars: int) -> str:
    """Coupe sur la dernière fin de phrase avant `chars` ; efface les blancs répétés."""
    text = re.sub(r"[ \t]+", " ", text).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) <= chars:
        return text
    cut = text[:chars]
    end = max(cut.rfind(". "), cut.rfind(".\n"), cut.rfind("! "), cut.rfind("? "))
    if end > chars // 2:
        return cut[: end + 1].rstrip()
    space = cut.rfind(" ")
    return (cut[:space] if space > chars // 2 else cut).rstrip() + "…"


def _candidates(client: WikipediaClient, config: dict[str, Any], day: date) -> list[tuple[str, str, str | None, str]]:
    """(titre, provenance, note, indice) dans l'ordre de priorité : fil du jour, recherches du jour, hasard.
    L'indice (texte de l'éphéméride, description du fil) sert à écarter une page avant de la lire."""
    out: list[tuple[str, str, str | None, str]] = []
    feeds = config.get("feeds", ["tfa", "onthisday", "mostread"])
    if feeds:
        feed = client.featured(day)
        tfa = feed.get("tfa")
        if "tfa" in feeds and tfa:
            out.append((tfa.get("titles", {}).get("normalized") or tfa.get("title"), "tfa", "Article du jour", tfa.get("description") or ""))
        if "onthisday" in feeds:
            max_year = config.get("onthisday_max_year")  # ex. 1995 : les drames récents ne font pas de bonnes histoires
            picked = 0
            for e in feed.get("onthisday", []):
                pages = e.get("pages") or []
                if not pages or (max_year and e.get("year") and int(e["year"]) > int(max_year)):
                    continue
                title = pages[0].get("titles", {}).get("normalized") or pages[0].get("title")
                text = e.get("text", "")
                out.append((title, "onthisday", f"{day:%d/%m} {e.get('year')} : {clip_text(text, 140)}", f"{text} {pages[0].get('description') or ''}"))
                picked += 1
                if picked >= int(config.get("onthisday_max", 4)):
                    break
        if "mostread" in feeds:
            for a in feed.get("mostread", {}).get("articles", [])[: int(config.get("mostread_max", 6))]:
                title = a.get("titles", {}).get("normalized") or a.get("title")
                out.append((title, "mostread", f"{a.get('views', 0):,} lectures hier".replace(",", " "), a.get("description") or ""))
    queries = list(config.get("queries", []))
    if queries:
        k = min(len(queries), int(config.get("queries_per_day", 2)))
        start = day.toordinal() % len(queries)
        for j in range(k):
            q = queries[(start + j) % len(queries)]
            for t in client.search(q, int(config.get("search_limit", 5))):
                out.append((t, "search", f"recherche « {q} »", ""))
    for t in client.random_titles(int(config.get("random", 0))):
        out.append((t, "random", "au hasard", ""))
    seen: set[str] = set()
    uniq = []
    for title, kind, note, hint in out:
        if title and title not in seen:
            seen.add(title)
            uniq.append((title, kind, note, hint))
    return uniq


def daily_material(
    client: WikipediaClient,
    config: dict[str, Any],
    day: date,
    exclude_urls: Iterable[str] = (),
    max_docs: int = 6,
    chars: int = 3500,
) -> list[SourceDoc]:
    """Pages du jour utilisables par l'agent idée : filtrées (regex `exclude` sur titre + description, pages
    déjà exploitées, pages trop courtes), au plus `max_docs`."""
    excluded = set(exclude_urls)
    pattern = config.get("exclude")
    min_words = int(config.get("min_words", 150))
    docs: list[SourceDoc] = []
    for title, kind, note, hint in _candidates(client, config, day):
        if len(docs) >= max_docs:
            break
        if pattern and re.search(pattern, f"{title} {hint}", re.I):
            continue
        try:
            doc = client.page(title, chars)
        except httpx.HTTPError as exc:
            log.warning("wikipedia.page_failed", title=title, error=str(exc)[:200])
            continue
        if not doc or doc.url in excluded or doc.words < min_words:
            continue
        if pattern and re.search(pattern, f"{doc.title} {doc.description or ''}", re.I):
            continue
        doc.kind, doc.note = kind, note
        docs.append(doc)
    return docs


def cached_material(
    client: WikipediaClient,
    config: dict[str, Any],
    day: date,
    cache_dir: Path,
    exclude_urls: Iterable[str] = (),
    max_docs: int = 6,
) -> list[SourceDoc]:
    """Même chose, avec un cache par jour et par configuration (les pages déjà exploitées sont filtrées après)."""
    key = hashlib.sha1(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]
    path = cache_dir / client.lang / f"{day.isoformat()}_{key}.json"
    if path.exists():
        docs = [SourceDoc(**d) for d in json.loads(path.read_text(encoding="utf-8"))]
    else:
        docs = daily_material(client, config, day, exclude_urls, max_docs)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([asdict(d) for d in docs], ensure_ascii=False, indent=1), encoding="utf-8")
    excluded = set(exclude_urls)
    return [d for d in docs if d.url not in excluded][:max_docs]


def material_text(docs: list[SourceDoc], chars: int = 2500) -> str:
    """Matière numérotée pour le LLM : [n] titre, URL, provenance, puis l'extrait."""
    blocks = []
    for i, d in enumerate(docs, start=1):
        head = f"[{i}] {d.title} — {d.url}" + (f" · {d.note}" if d.note else "") + (f" · {d.description}" if d.description else "")
        blocks.append(head + "\n" + clip_text(d.extract, chars))
    return "\n\n".join(blocks)


def cached_page(client: WikipediaClient, title: str, chars: int, cache_dir: Path, day: date | None = None) -> SourceDoc | None:
    """Page entière (coupée à `chars`), en cache pour la journée dans cache_dir/pages/<langue>/."""
    day = day or date.today()
    key = hashlib.sha1(f"{title}|{chars}".encode()).hexdigest()[:12]
    path = cache_dir / "pages" / client.lang / f"{day.isoformat()}_{key}.json"
    if path.exists():
        return SourceDoc(**json.loads(path.read_text(encoding="utf-8")))
    doc = client.page(title, chars)
    if doc:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(doc), ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


def source_dossier(
    sources: list[dict[str, Any]],
    cache_dir: Path,
    user_agent: str = DEFAULT_USER_AGENT,
    *,
    chars: int = 12000,
    other_lang: str | None = "en",
    other_chars: int = 8000,
    max_pages: int = 3,
) -> str:
    """Le dossier du scénariste : les pages sources d'un concept, relues en entier. L'agent idée ne garde que quelques
    faits (3 pour le canal Rhin-Main-Danube, le 25/09) ; le récit a besoin du reste : à quoi ça sert, la controverse et sa
    raison, les personnes, les chiffres de comparaison. La version anglaise de chaque page s'ajoute quand elle existe
    (souvent plus fournie). Numérotation [n] des sources du concept ; une page illisible est sautée ; "" si rien."""
    blocks: list[str] = []
    for i, src in enumerate(sources[:max_pages], start=1):
        if src.get("kind", "wikipedia") != "wikipedia" or not src.get("title"):
            continue
        lang = str(src.get("lang") or "fr")
        client = WikipediaClient(lang=lang, user_agent=user_agent)
        try:
            doc = cached_page(client, str(src["title"]), chars, cache_dir)
            if doc:
                blocks.append(f"[{i}] {doc.title} — {doc.url}\n{doc.extract}")
            if other_lang and other_lang != lang:
                other = client.langlink(str(src["title"]), other_lang)
                if other:
                    odoc = cached_page(WikipediaClient(lang=other_lang, user_agent=user_agent), other, other_chars, cache_dir)
                    if odoc:
                        blocks.append(f"[{i}, version {other_lang}] {odoc.title} — {odoc.url}\n{odoc.extract}")
        except httpx.HTTPError as exc:
            log.warning("wikipedia.dossier_failed", title=src.get("title"), error=str(exc)[:200])
    return "\n\n".join(blocks)


def sources_for(docs: list[SourceDoc], facts: list[Fact]) -> tuple[list[SourceRef], list[Fact]]:
    """Traduit les faits cités [n] (1-based dans la matière) en sources du concept (0-based, uniques)
    et écarte les faits qui citent une source inexistante."""
    refs: list[SourceRef] = []
    index: dict[int, int] = {}
    kept: list[Fact] = []
    for f in facts:
        n = f.source
        if not 1 <= n <= len(docs):
            continue
        if n not in index:
            index[n] = len(refs)
            refs.append(docs[n - 1].to_ref())
        kept.append(Fact(claim=f.claim, source=index[n]))
    return refs, kept


def is_list_page(title: str) -> bool:
    return title.startswith(LIST_PREFIXES)
