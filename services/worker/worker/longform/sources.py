"""Sources fiables au-delà de Wikipédia (docs/63 §3, exigence de Luca du 04/10 : « des faits vérifiés et vérifiables
sur Internet avec de vraies sources ; je ne veux pas faire de désinformation »).

On part des références que Wikipédia cite elle-même (liens externes de l'article, API `prop=extlinks`) : elles ont
déjà été choisies par les rédacteurs. On ne garde que les domaines sérieux de TRUSTED (recherche, archéologie,
musées, archives, revues scientifiques, grands journaux, encyclopédies), on lit chaque page (texte des paragraphes,
analyseur HTML de Python), on garde celles qui parlent vraiment du sujet (ses mots-clés y reviennent), et elles
rejoignent le dossier du conteur, numérotées comme les pages Wikipédia. Les pages lues sont gardées en cache
(DATA_DIR/sources/web)."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

log = structlog.get_logger(__name__)

# domaine (ou fin de domaine) → ce que c'est, tel qu'affiché dans le dossier et la description
TRUSTED: dict[str, str] = {
    "inrap.fr": "INRAP (archéologie préventive)",
    "cnrs.fr": "CNRS",
    "persee.fr": "Persée (revues scientifiques)",
    "hal.science": "HAL (archive ouverte de la recherche)",
    "archives-ouvertes.fr": "HAL (archive ouverte de la recherche)",
    "openedition.org": "OpenEdition (revues scientifiques)",
    "cairn.info": "Cairn (revues scientifiques)",
    "bnf.fr": "Bibliothèque nationale de France",
    "culture.gouv.fr": "Ministère de la Culture",
    "archives-nationales.culture.gouv.fr": "Archives nationales",
    "louvre.fr": "Musée du Louvre",
    "britishmuseum.org": "British Museum",
    "metmuseum.org": "Metropolitan Museum",
    "smithsonianmag.com": "Smithsonian Magazine",
    "si.edu": "Smithsonian Institution",
    "nationalgeographic.com": "National Geographic",
    "nationalgeographic.fr": "National Geographic",
    "unesco.org": "UNESCO",
    "nature.com": "Nature",
    "science.org": "Science",
    "pnas.org": "PNAS",
    "cambridge.org": "Cambridge University Press",
    "academic.oup.com": "Oxford University Press",
    "jstor.org": "JSTOR",
    "britannica.com": "Encyclopædia Britannica",
    "universalis.fr": "Encyclopædia Universalis",
    "larousse.fr": "Larousse",
    "bbc.com": "BBC",
    "bbc.co.uk": "BBC",
    "theguardian.com": "The Guardian",
    "nytimes.com": "The New York Times",
    "lemonde.fr": "Le Monde",
    "lefigaro.fr": "Le Figaro",
    "liberation.fr": "Libération",
    "radiofrance.fr": "Radio France",
    "francetvinfo.fr": "France Info",
    "arte.tv": "Arte",
    "sciencesetavenir.fr": "Sciences et Avenir",
    "pourlascience.fr": "Pour la Science",
    "herodote.net": "Hérodote.net",
    "histoire-image.org": "L'histoire par l'image",
    "ifao.egnet.net": "IFAO (Institut français d'archéologie orientale)",
    "worldhistory.org": "World History Encyclopedia",
}
UNIVERSITY = re.compile(r"(^|\.)(univ-[a-z-]+\.fr|[a-z-]+\.edu|ox\.ac\.uk|cam\.ac\.uk|ac\.uk)$")
SKIP_PATH = re.compile(r"\.(pdf|jpg|jpeg|png|gif|zip|mp4|mp3)(\?|$)", re.I)
MAX_FETCH = 14  # pages lues au plus par vidéo
TEXT_CHARS = 6000  # signes gardés par page
MIN_CHARS = 900  # une page plus courte (paywall, page d'accueil) ne sert pas
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) yt2-worker documentary sources"


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def unwrap_archive(url: str) -> str:
    """Une copie archive.org d'une page : l'adresse d'origine (pour juger le domaine)."""
    m = re.match(r"https?://web\.archive\.org/web/[^/]+/(https?://.+)$", url)
    return m.group(1) if m else url


def trust_label(url: str) -> str | None:
    host = domain_of(unwrap_archive(url))
    for d, label in TRUSTED.items():
        if host == d or host.endswith("." + d):
            return label
    if UNIVERSITY.search(host):
        return "Université"
    return None


class _Text(HTMLParser):
    """Le texte des paragraphes, titres et éléments de liste, hors scripts, styles, menus et pieds de page."""

    SKIP = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"}
    KEEP = {"p", "h1", "h2", "h3", "li", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.keep = 0
        self.title = ""
        self.in_title = False
        self.parts: list[str] = []
        self.buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.KEEP:
            self.keep += 1
        elif tag == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.KEEP and self.keep:
            self.keep -= 1
            text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if len(text) > 40:
                self.parts.append(text)
            self.buf = []
        elif tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        elif self.keep and not self.skip:
            self.buf.append(data)


def html_text(html: str) -> tuple[str, str]:
    p = _Text()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 — HTML cassé : ce qui a été lu suffit
        pass
    return re.sub(r"\s+", " ", p.title).strip(), "\n".join(dict.fromkeys(p.parts))


def wiki_links(title: str, lang: str, user_agent: str) -> list[str]:
    """Les liens externes d'un article Wikipédia (références et liens de fin d'article)."""
    try:
        r = httpx.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={"action": "query", "prop": "extlinks", "titles": title, "ellimit": "500", "format": "json", "redirects": "1"},
            headers={"User-Agent": user_agent},
            timeout=20,
        )
        r.raise_for_status()
        pages = (r.json().get("query") or {}).get("pages") or {}
        return [
            e.get("*") or e.get("url") for p in pages.values() for e in (p.get("extlinks") or []) if e.get("*") or e.get("url")
        ]
    except httpx.HTTPError as exc:
        log.warning("sources.liens_wikipedia", title=title, error=str(exc)[:200])
        return []


def terms_of(*texts: str) -> set[str]:
    """Mots-clés d'un sujet (mots de 5 lettres et plus, sans accents), pour juger qu'une page en parle."""
    out: set[str] = set()
    for t in texts:
        norm = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
        out |= {w for w in re.findall(r"[a-z]{5,}", norm)}
    return out - {"histoire", "toute", "quelle", "comment", "pourquoi", "cette", "leurs", "after", "their", "which", "about"}


def relevance(text: str, terms: Iterable[str]) -> int:
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return sum(1 for t in terms if t in norm)


def fetch_page(url: str, cache_dir: Path) -> dict[str, Any] | None:
    key = hashlib.sha1(url.encode()).hexdigest()
    path = cache_dir / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")) or None
    try:
        r = httpx.get(url, headers={"User-Agent": UA, "Accept-Language": "fr,en;q=0.8"}, timeout=25, follow_redirects=True)
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or "html" not in ctype:
            page: dict[str, Any] | None = None
        else:
            title, text = html_text(r.text)
            page = {"url": str(r.url), "title": title[:200], "text": text} if len(text) >= MIN_CHARS else None
    except httpx.HTTPError as exc:
        log.info("sources.page_illisible", url=url, error=str(exc)[:150])
        page = None
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(page or {}, ensure_ascii=False), encoding="utf-8")
    return page


def external_sources(
    wiki_titles: Iterable[tuple[str, str]], subject: str, cache_dir: Path, user_agent: str, *, keep: int = 6
) -> list[dict[str, Any]]:
    """Les pages fiables citées par les articles Wikipédia du sujet, lues, qui parlent vraiment du sujet : au plus
    `keep`, des plus pertinentes aux moins pertinentes ; chacune {url, title, label, text}."""
    seen: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for title, lang in wiki_titles:
        for url in wiki_links(title, lang, user_agent):
            url = url.strip()
            if url.startswith("//"):
                url = "https:" + url
            if not url.startswith("http") or SKIP_PATH.search(url) or url in seen:
                continue
            label = trust_label(url)
            if label:
                seen.add(url)
                candidates.append((url, label))
    terms = terms_of(subject, *(t for t, _ in wiki_titles))
    found: list[dict[str, Any]] = []
    for url, label in candidates[: MAX_FETCH * 3]:
        if len(found) >= MAX_FETCH:
            break
        page = fetch_page(url, cache_dir)
        if not page:
            continue
        score = relevance(page["text"][:20000], terms)
        if score >= 2:
            found.append({**page, "label": label, "score": score, "text": page["text"][:TEXT_CHARS]})
    found.sort(key=lambda p: -p["score"])
    by_domain: dict[str, int] = {}
    kept: list[dict[str, Any]] = []
    urls: set[str] = set()
    for p in found:  # une page une fois (deux liens mènent souvent au même article), 2 pages par site au plus
        if p["url"] in urls:
            continue
        urls.add(p["url"])
        d = domain_of(p["url"])
        if by_domain.get(d, 0) >= 2:
            continue
        by_domain[d] = by_domain.get(d, 0) + 1
        kept.append(p)
        if len(kept) >= keep:
            break
    return kept
