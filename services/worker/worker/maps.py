"""Scène carte des récits : la caméra descend de l'espace jusqu'au lieu, dont le tracé se dessine (docs/24).

Demandé par Luca le 28/09 après la vidéo du canal Rhin-Main-Danube : « une carte du monde où on part assez haut, puis
on zoome à l'endroit exact », et « montrer exactement la ligne du canal, de quel bout à quel bout ».

Rendu local et gratuit, sans modèle d'IA ni clé :
- fond : images satellite Sentinel-2 cloudless 2016 d'EOX (CC BY 4.0), tuiles XYZ de 256 px gardées dans
  DATA_DIR/maps/tiles ; la mention est gravée en bas de l'image et ajoutée à la description (steps/seo.py) ;
- lieux : la page Wikipédia du lieu donne ses coordonnées et son identifiant Wikidata, qui retrouve l'objet dans
  OpenStreetMap (Overpass : le tracé exact d'un canal ou d'un fleuve, le contour d'une île) ; repli sur Nominatim (la
  recherche d'OpenStreetMap), puis sur le seul point de la page. Repères (bouts du tracé, grands repères) : le point de
  leur page Wikipédia, sinon Nominatim. Données © contributeurs d'OpenStreetMap (ODbL), en cache dans DATA_DIR/maps/geo ;
- image : globe en projection orthographique calculée avec numpy (le globe grandit jusqu'à remplir l'écran, puis la
  vue continue de descendre), deux niveaux de tuiles mélangés à chaque image pour ne jamais voir la netteté sauter,
  tracé, repères et étiquettes dessinés par Pillow, images envoyées à FFmpeg.
numpy vient de l'extra « tts » du worker (comme worker/timeline.py) : les steps n'importent ce module que pour une
scène carte.

Déroulé d'une scène de T secondes : descente depuis l'espace (avec des grands repères : une pause sur la vue large où
ils apparaissent), tracé du lieu d'un bout à l'autre (les repères des bouts s'affichent au départ et à l'arrivée), puis
une fin tenue avec une légère avancée. L'image du storyboard est la fin de la scène (tout est tracé).
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import subprocess
import threading
import time
from collections import OrderedDict
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import structlog
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .models import MapSpec
from .sources.wikipedia import DEFAULT_USER_AGENT, WikipediaClient

log = structlog.get_logger(__name__)

W, H, FPS = 1080, 1920, 30
CENTER_Y = 0.45  # le lieu un peu au-dessus du milieu : les sous-titres sont centrés vers 52 % de la hauteur
TILE = 256
MAX_ZOOM = 14
MAX_LAT = 85.0511  # limite de la projection des tuiles (Web Mercator)
TILE_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg"
TILE_SET = "s2cloudless_2016"
# Deux serveurs Overpass publics, gratuits et sans clé ; le premier répond 429 quand on enchaîne les requêtes
OVERPASS_URLS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
FONT_FILE = "Montserrat-SemiBold.ttf"  # police livrée avec le worker (assets/fonts)
CREDIT = {
    "fr": "Satellite : Sentinel-2 cloudless 2016 par EOX (CC BY 4.0) · tracé © contributeurs OpenStreetMap",
    "en": "Satellite: Sentinel-2 cloudless 2016 by EOX (CC BY 4.0) · route © OpenStreetMap contributors",
}

GLOBE_SCALE = 0.42 * W  # rayon de la Terre à l'écran au départ : le globe entier, vu de l'espace
POINT_VIEW_KM = 60.0  # largeur de la vue finale sur un lieu sans tracé (ville, monument)
MIN_VIEW_KM = 3.0
ZOOM_BIAS = 0.35  # niveau de tuiles un peu plus fin que la taille d'un pixel : image nette
GOLD = (255, 200, 61)
RIVER = (120, 200, 255)
SPACE = np.array([4, 7, 16], dtype=np.float32)
ATMOSPHERE = np.array([70, 140, 255], dtype=np.float32)

LonLat = tuple[float, float]


class MapError(RuntimeError):
    """La carte ne peut pas être faite (lieu introuvable, réseau) : la scène repasse par l'image et le clip d'IA."""


# ---------------------------------------------------------------------------
# Lieux : Wikipédia → Wikidata → OpenStreetMap
# ---------------------------------------------------------------------------


@dataclass
class Place:
    name: str  # tel qu'affiché, dans la langue de la vidéo
    lon: float
    lat: float
    lines: list[list[LonLat]] = field(default_factory=list)  # tracé ou contour ; vide = un point
    source: str = "wikipedia"  # osm | nominatim | wikipedia

    def points(self) -> list[LonLat]:
        return [p for line in self.lines for p in line] or [(self.lon, self.lat)]

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "lon": self.lon,
            "lat": self.lat,
            "source": self.source,
            "lines": [[list(p) for p in line] for line in self.lines],
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Place:
        return cls(
            name=d["name"],
            lon=float(d["lon"]),
            lat=float(d["lat"]),
            source=d.get("source", "wikipedia"),
            lines=[[(float(p[0]), float(p[1])) for p in line] for line in d.get("lines") or []],
        )


def label_of(name: str) -> str:
    """Nom affiché : sans la précision d'un titre Wikipédia (« Main (rivière) » → « Main »)."""
    return re.sub(r"\s*\([^)]*\)\s*", " ", name).strip() or name.strip()


def bbox(points: Sequence[LonLat]) -> tuple[float, float, float, float]:
    """(ouest, sud, est, nord) de points (longitudes sans passage de l'antiméridien)."""
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    return min(lons), min(lats), max(lons), max(lats)


def simplify(line: Sequence[LonLat], tol: float) -> list[LonLat]:
    """Douglas-Peucker en degrés : ne garde que les points qui s'écartent de plus de `tol` de la corde."""
    if len(line) < 3 or tol <= 0:
        return list(line)
    pts = np.asarray(line, dtype=np.float64)
    keep = np.zeros(len(pts), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        seg, rel = pts[b] - pts[a], pts[a + 1 : b] - pts[a]
        norm = float(np.hypot(seg[0], seg[1]))
        d = np.hypot(rel[:, 0], rel[:, 1]) if norm == 0 else np.abs(seg[0] * rel[:, 1] - seg[1] * rel[:, 0]) / norm
        i = int(np.argmax(d))
        if d[i] > tol:
            k = a + 1 + i
            keep[k] = True
            stack += [(a, k), (k, b)]
    return [(float(x), float(y)) for x, y in pts[keep]]


def simplify_lines(lines: list[list[LonLat]], parts: float = 4000.0) -> list[list[LonLat]]:
    """Allège un tracé au 1/4000 de sa taille : plus fin qu'un pixel de la vue finale, sans les milliers de points d'OSM."""
    x0, y0, x1, y1 = bbox([p for line in lines for p in line])
    tol = max(x1 - x0, y1 - y0) / parts
    out: list[list[LonLat]] = []
    seen: set[tuple[LonLat, LonLat, int]] = set()
    for line in lines:
        key = (line[0], line[-1], len(line))
        if len(line) >= 2 and key not in seen and (line[-1], line[0], len(line)) not in seen:
            seen.add(key)
            out.append(simplify(line, tol))
    return out


def overpass_lines(data: dict[str, Any]) -> tuple[list[list[LonLat]], LonLat | None]:
    """Chemins (ways, membres des relations) et premier point (node) d'une réponse Overpass `out geom`."""
    lines: list[list[LonLat]] = []
    point: LonLat | None = None
    for e in data.get("elements", []):
        if e.get("type") == "node" and "lat" in e:
            point = point or (float(e["lon"]), float(e["lat"]))
        ways = [e] if e.get("type") == "way" else [m for m in e.get("members", []) if m.get("type") == "way"]
        for w in ways:
            geom = [(float(g["lon"]), float(g["lat"])) for g in w.get("geometry") or [] if g]
            if len(geom) >= 2:
                lines.append(geom)
    return lines, point


def geojson_lines(g: dict[str, Any] | None) -> list[list[LonLat]]:
    """Lignes d'une géométrie GeoJSON de Nominatim (contours extérieurs et intérieurs pour une surface)."""
    if not g:
        return []
    t, c = g.get("type"), g.get("coordinates") or []
    if t == "LineString":
        rings = [c]
    elif t in ("MultiLineString", "Polygon"):
        rings = c
    elif t == "MultiPolygon":
        rings = [ring for poly in c for ring in poly]
    else:
        return []
    return [[(float(p[0]), float(p[1])) for p in ring] for ring in rings if len(ring) >= 2]


class GeoResolver:
    """Trouve un lieu (point et, si `shape`, tracé) ; résultats gardés sur disque (un lieu ne bouge pas)."""

    def __init__(self, cache_dir: Path, lang: str = "fr", user_agent: str = DEFAULT_USER_AGENT, timeout_s: float = 90.0) -> None:
        self.cache_dir, self.lang, self.ua, self.timeout = cache_dir, lang, user_agent, timeout_s
        self.wiki = WikipediaClient(lang=lang, user_agent=user_agent)
        self._last_nominatim = self._last_overpass = 0.0

    def resolve(self, name: str, *, shape: bool) -> Place | None:
        name = name.strip()
        if not name:
            return None
        path = self.cache_dir / f"{hashlib.sha1(f'{self.lang}|{name}|{shape}'.encode()).hexdigest()[:16]}.json"
        if path.exists():
            try:
                return Place.from_json(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError):
                pass
        place = self._resolve(name, shape)
        if place:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(place.to_json(), ensure_ascii=False), encoding="utf-8")
        return place

    def _resolve(self, name: str, shape: bool) -> Place | None:
        page: dict[str, Any] | None = None
        for query in dict.fromkeys([name, label_of(name)]):  # titre exact (avec sa précision), puis le nom seul
            try:
                page = self.wiki.place(query)
            except httpx.HTTPError as exc:
                log.warning("maps.wikipedia_failed", name=query, error=str(exc)[:200])
            if page:
                break
        point: LonLat | None = (float(page["lon"]), float(page["lat"])) if page and page.get("lat") is not None else None
        lines: list[list[LonLat]] = []
        source = "wikipedia"
        if shape and page and re.fullmatch(r"Q\d+", str(page.get("qid") or "")):
            try:
                lines, node = self._overpass(str(page["qid"]))
                point = point or node
                source = "osm" if lines else source
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("maps.overpass_failed", name=name, qid=page.get("qid"), error=str(exc)[:200])
        if (shape and not lines) or point is None:
            for query in dict.fromkeys([label_of(name), *([page["title"]] if page else [])]):
                hit = self._nominatim(query, shape)
                if hit:
                    n_lines, n_point = hit
                    if shape and not lines and n_lines:
                        lines, source = n_lines, "nominatim"
                    if point is None:
                        point, source = n_point, source if lines else "nominatim"
                    break
        if point is None and lines:
            x0, y0, x1, y1 = bbox([p for line in lines for p in line])
            point = ((x0 + x1) / 2, (y0 + y1) / 2)
        if point is None:
            return None
        return Place(name=label_of(name), lon=point[0], lat=point[1], lines=simplify_lines(lines) if lines else [], source=source)

    def _overpass(self, qid: str) -> tuple[list[list[LonLat]], LonLat | None]:
        """L'objet OpenStreetMap qui porte cet identifiant Wikidata, avec sa géométrie ; nouvel essai après une pause si le
        serveur est saturé (429, 504), puis le serveur de secours."""
        query = f'[out:json][timeout:90][maxsize:67108864];nwr["wikidata"="{qid}"];out geom;'
        last: Exception | None = None
        for url in OVERPASS_URLS:
            for pause in (0, 20, 45):
                time.sleep(max(pause, 3.0 - (time.monotonic() - self._last_overpass)))  # 3 s entre deux requêtes
                self._last_overpass = time.monotonic()
                try:
                    r = httpx.post(url, data={"data": query}, headers={"User-Agent": self.ua}, timeout=self.timeout)
                    if r.status_code in (429, 502, 503, 504):
                        last = httpx.HTTPStatusError(f"Overpass {r.status_code}", request=r.request, response=r)
                        continue
                    r.raise_for_status()
                    return overpass_lines(r.json())
                except httpx.TransportError as exc:
                    last = exc
        raise last or httpx.HTTPError("Overpass injoignable")

    def _nominatim(self, query: str, shape: bool) -> tuple[list[list[LonLat]], LonLat] | None:
        """Recherche OpenStreetMap ; une requête par seconde au plus (règles d'usage de Nominatim)."""
        wait = 1.1 - (time.monotonic() - self._last_nominatim)
        if wait > 0:
            time.sleep(wait)
        params: dict[str, Any] = {"q": query, "format": "jsonv2", "limit": 1, "accept-language": self.lang}
        if shape:
            params.update({"polygon_geojson": 1, "polygon_threshold": 0.0005})
        try:
            r = httpx.get(NOMINATIM_URL, params=params, headers={"User-Agent": self.ua}, timeout=30)
            r.raise_for_status()
            hits = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("maps.nominatim_failed", query=query, error=str(exc)[:200])
            return None
        finally:
            self._last_nominatim = time.monotonic()
        if not hits:
            return None
        h = hits[0]
        return geojson_lines(h.get("geojson")), (float(h["lon"]), float(h["lat"]))


def _dist(a: LonLat, b: LonLat) -> float:
    """Distance approchée en degrés de latitude (longitudes ramenées à la latitude moyenne)."""
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * k, a[1] - b[1])


def chain(lines: list[list[LonLat]], start: LonLat | None = None, gap: float | None = None) -> list[list[LonLat]]:
    """Met les morceaux d'un tracé bout à bout dans l'ordre du parcours, en partant du bout le plus proche de `start` (le
    premier repère) ou, sans repère, de l'extrémité la plus éloignée du centre. Un morceau qui ne touche pas le précédent
    (bras, morceau isolé) commence un nouveau trait. Renvoie les traits dans l'ordre du dessin."""
    pieces = [list(line) for line in lines if len(line) >= 2]
    if not pieces:
        return []
    x0, y0, x1, y1 = bbox([p for line in pieces for p in line])
    gap = gap if gap is not None else max(x1 - x0, y1 - y0) * 0.01 + 1e-6
    ends = [(i, rev) for i in range(len(pieces)) for rev in (False, True)]

    def head(i: int, rev: bool) -> LonLat:
        return pieces[i][-1] if rev else pieces[i][0]

    anchor = start or max(
        (p for line in pieces for p in (line[0], line[-1])), key=lambda p: _dist(p, ((x0 + x1) / 2, (y0 + y1) / 2))
    )
    i, rev = min(ends, key=lambda e: _dist(head(*e), anchor))
    used = {i}
    strokes = [pieces[i][::-1] if rev else list(pieces[i])]
    while len(used) < len(pieces):
        tail = strokes[-1][-1]
        i, rev = min(((j, r) for j, r in ends if j not in used), key=lambda e: _dist(head(*e), tail))
        used.add(i)
        piece = pieces[i][::-1] if rev else list(pieces[i])
        if _dist(piece[0], tail) <= gap:
            strokes[-1].extend(piece[1:])
        else:
            strokes.append(piece)
    return strokes


def stroke_lengths(strokes: list[list[LonLat]]) -> list[list[float]]:
    """Longueur cumulée de chaque trait, point par point (pour le tracé progressif)."""
    out, total = [], 0.0
    for s in strokes:
        cum = [total]
        for a, b in zip(s, s[1:], strict=False):
            total += _dist(a, b)
            cum.append(total)
        out.append(cum)
    return out


# ---------------------------------------------------------------------------
# Caméra
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class View:
    lon: float
    lat: float
    scale: float  # rayon de la Terre à l'écran, en pixels (pixels par radian au centre de la vue)


def smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def fit_scale(points: Sequence[LonLat], center_lat: float, frac_w: float = 0.72, frac_h: float = 0.46) -> float:
    """Échelle où tous les points tiennent dans `frac_w` de la largeur et `frac_h` de la hauteur."""
    x0, y0, x1, y1 = bbox(points)
    dx = math.radians(max(x1 - x0, 1e-6)) / 2 * max(0.05, math.cos(math.radians(center_lat)))
    dy = math.radians(max(y1 - y0, 1e-6)) / 2
    scale = min(frac_w * W / 2 / dx, frac_h * H / 2 / dy)
    return min(max(scale, GLOBE_SCALE * 1.2), W / (MIN_VIEW_KM / 6371.0))


def blend_view(a: View, b: View, u: float) -> View:
    """Entre deux vues : l'échelle varie en logarithme (zoom régulier), le centre arrive avant la fin du zoom (on est
    au-dessus du lieu pendant la descente) ; la longitude prend le plus court chemin."""
    uz, uc = smoothstep(u), smoothstep(min(1.0, u * 1.6))
    dlon = (b.lon - a.lon + 180.0) % 360.0 - 180.0
    return View(
        lon=a.lon + dlon * uc,
        lat=a.lat + (b.lat - a.lat) * uc,
        scale=math.exp(math.log(a.scale) + (math.log(b.scale) - math.log(a.scale)) * uz),
    )


@dataclass
class Plan:
    """Tout ce qu'il faut pour dessiner la scène : lieux résolus, trait ordonné, images clés de la caméra, calendrier."""

    place: Place
    ends: list[Place]
    context: list[Place]
    strokes: list[list[LonLat]]
    keys: list[tuple[float, View]]  # (fraction de la durée, vue)
    trace: tuple[float, float]  # début et fin du tracé (fractions)
    context_show: tuple[float, float] = (0.0, 0.0)  # grands repères visibles (fractions)
    rivers: list[Place] = field(default_factory=list)  # ce que le lieu relie, en bleu, dès que l'on s'approche

    def view(self, f: float) -> View:
        keys = self.keys
        if f <= keys[0][0]:
            return keys[0][1]
        for (fa, va), (fb, vb) in zip(keys, keys[1:], strict=False):
            if f <= fb:
                return blend_view(va, vb, (f - fa) / max(1e-6, fb - fa))
        return keys[-1][1]

    def progress(self, f: float) -> float:
        a, b = self.trace
        return smoothstep((f - a) / max(1e-6, b - a))


def make_plan(place: Place, ends: list[Place], context: list[Place], rivers: list[Place] | None = None) -> Plan:
    rivers = [r for r in rivers or [] if r.lines]
    subject = place.points() + [(p.lon, p.lat) for p in ends]
    x0, y0, x1, y1 = bbox(subject)
    center = ((x0 + x1) / 2, (y0 + y1) / 2)
    if place.lines or ends:
        final = fit_scale(subject, center[1])
    else:
        final = W / (POINT_VIEW_KM / 6371.0)
    target = View(center[0], center[1], final)
    start = View(center[0] - 60.0, max(-50.0, min(50.0, center[1] - 15.0)), GLOBE_SCALE)
    strokes = chain(place.lines, (ends[0].lon, ends[0].lat) if ends else None) if place.lines else []
    wide_scale = 0.0
    if context:
        everything = subject + [(p.lon, p.lat) for p in context]
        wx0, wy0, wx1, wy1 = bbox(everything)
        wide_scale = fit_scale(everything, (wy0 + wy1) / 2, 0.8, 0.55)
    if context and wide_scale < final * 0.5:  # une vraie vue large : pause sur les grands repères, puis on plonge
        wx0, wy0, wx1, wy1 = bbox(subject + [(p.lon, p.lat) for p in context])
        wide = View((wx0 + wx1) / 2, (wy0 + wy1) / 2, wide_scale)
        keys = [
            (0.0, start),
            (0.30, wide),
            (0.42, View(wide.lon, wide.lat, wide.scale * 1.06)),
            (0.72, target),
            (1.0, View(target.lon, target.lat, target.scale * 1.05)),
        ]
        return Plan(place, ends, context, strokes, keys, trace=(0.62, 0.92), context_show=(0.24, 0.52), rivers=rivers)
    keys = [(0.0, start), (0.55, target), (1.0, View(target.lon, target.lat, target.scale * 1.06))]
    return Plan(place, ends, [], strokes, keys, trace=(0.45, 0.88), rivers=rivers)


# ---------------------------------------------------------------------------
# Tuiles satellite
# ---------------------------------------------------------------------------


class TileCache:
    """Tuiles XYZ de 256 px : disque (DATA_DIR/maps/tiles/<jeu>/z/x/y.jpg), puis réseau ; mémoire LRU pour le rendu."""

    def __init__(self, cache_dir: Path, url: str = TILE_URL, user_agent: str = DEFAULT_USER_AGENT, memory: int = 1500) -> None:
        self.dir, self.url, self.memory = cache_dir, url, memory
        self.client = httpx.Client(headers={"User-Agent": user_agent}, timeout=30, follow_redirects=True)
        self._mem: OrderedDict[tuple[int, int, int], np.ndarray] = OrderedDict()
        self._lock = threading.Lock()
        self.missing = 0

    def path(self, z: int, x: int, y: int) -> Path:
        return self.dir / str(z) / str(x) / f"{y}.jpg"

    def fetch(self, z: int, x: int, y: int) -> bool:
        """Télécharge la tuile si elle n'est pas sur le disque ; False si elle reste introuvable."""
        p = self.path(z, x, y)
        if p.exists():
            return True
        for delay in (0.0, 2.0, 6.0):
            time.sleep(delay)
            try:
                r = self.client.get(self.url.format(z=z, x=x, y=y))
                if r.status_code == 200 and r.content:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    tmp = p.with_suffix(".part")
                    tmp.write_bytes(r.content)
                    tmp.replace(p)
                    return True
                if r.status_code == 404:
                    return False
            except httpx.HTTPError:
                continue
        return False

    def prefetch(self, tiles: set[tuple[int, int, int]], workers: int = 4) -> int:
        todo = [t for t in tiles if not self.path(*t).exists()]
        if todo:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                ok = sum(pool.map(lambda t: self.fetch(*t), todo))
            self.missing += len(todo) - ok
        return len(todo)

    def tile(self, z: int, x: int, y: int) -> np.ndarray:
        n = 1 << z
        key = (z, x % n, min(max(y, 0), n - 1))
        with self._lock:
            if key in self._mem:
                self._mem.move_to_end(key)
                return self._mem[key]
        arr = None
        if self.path(*key).exists() or self.fetch(*key):
            try:
                with Image.open(self.path(*key)) as im:
                    rgb = (im.convert("RGBA") if im.mode == "P" else im).convert("RGB")  # quelques tuiles en PNG à palette
                    arr = np.asarray(rgb.resize((TILE, TILE)) if rgb.size != (TILE, TILE) else rgb)
            except OSError:
                arr = None
        if arr is None:  # tuile absente : un fond neutre plutôt qu'un trou
            arr = np.full((TILE, TILE, 3), (22, 34, 52), dtype=np.uint8)
        with self._lock:
            self._mem[key] = arr
            while len(self._mem) > self.memory:
                self._mem.popitem(last=False)
        return arr

    def close(self) -> None:
        self.client.close()


# ---------------------------------------------------------------------------
# Rendu
# ---------------------------------------------------------------------------


def level(view: View) -> float:
    """Niveau de tuiles (fractionnaire) où un pixel de tuile vaut un pixel d'écran au centre de la vue."""
    k = 2 * math.pi * max(0.05, math.cos(math.radians(view.lat))) * view.scale / TILE
    return min(float(MAX_ZOOM), max(1.0, math.log2(max(k, 1e-9)) + ZOOM_BIAS))


def project(
    view: View, lon: np.ndarray, lat: np.ndarray, cx: float = W / 2, cy: float = H * CENTER_Y
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Orthographique : (x, y) à l'écran et visibilité (face visible du globe)."""
    phi0, lam0 = math.radians(view.lat), math.radians(view.lon)
    phi, dlam = np.radians(lat), np.radians(lon) - lam0
    cosc = math.sin(phi0) * np.sin(phi) + math.cos(phi0) * np.cos(phi) * np.cos(dlam)
    x = cx + view.scale * np.cos(phi) * np.sin(dlam)
    y = cy - view.scale * (math.cos(phi0) * np.sin(phi) - math.sin(phi0) * np.cos(phi) * np.cos(dlam))
    return x, y, cosc > 0


class Renderer:
    """Dessine les images d'une scène carte (numpy + Pillow)."""

    def __init__(
        self, plan: Plan, tiles: TileCache, font_path: Path | None, credit: str = "", size: tuple[int, int] = (W, H)
    ) -> None:
        self.plan, self.tiles, self.credit = plan, tiles, credit
        self.w, self.h = size
        self.k = self.w / W  # rendu plus petit (essais) : même cadrage, échelle réduite d'autant
        self.cx, self.cy = self.w / 2, self.h * CENTER_Y
        self.gx = (np.arange(self.w, dtype=np.float64) + 0.5 - self.cx)[None, :]
        self.gy = (self.cy - (np.arange(self.h, dtype=np.float64) + 0.5))[:, None]
        yy, xx = np.mgrid[0 : self.h, 0 : self.w]
        r = np.hypot((xx - self.w / 2) / (self.w / 2), (yy - self.h / 2) / (self.h / 2))
        self.vignette = (1.0 - 0.28 * np.clip(r - 0.35, 0, 1) ** 1.6).astype(np.float32)[..., None]
        rng = np.random.default_rng(7)
        stars = np.zeros((self.h, self.w), dtype=np.float32)
        n = self.w * self.h // 900
        stars[rng.integers(0, self.h, n), rng.integers(0, self.w, n)] = rng.uniform(0.25, 1.0, n).astype(np.float32)
        self.stars = stars[..., None] * 200.0
        self.font_path = font_path
        self._fonts: dict[int, Any] = {}
        self.lengths = stroke_lengths(plan.strokes)
        self.total = self.lengths[-1][-1] if self.lengths and self.lengths[-1] else 0.0

    # -- fond : espace, globe, satellite --------------------------------------

    def _sphere(self, view: View) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Latitude, longitude (radians) sous chaque pixel, masque du globe et distance au centre (en rayons). En float32 :
        largement assez précis jusqu'au niveau 14 (moins d'un demi-pixel de tuile) et deux fois plus rapide."""
        x = (self.gx / view.scale).astype(np.float32)
        y = (self.gy / view.scale).astype(np.float32)
        rho2 = x * x + y * y
        inside = rho2 < 1.0
        c = np.sqrt(np.clip(1.0 - rho2, 0.0, 1.0))
        phi0, lam0 = math.radians(view.lat), math.radians(view.lon)
        lat = np.arcsin(np.clip(c * np.float32(math.sin(phi0)) + y * np.float32(math.cos(phi0)), -1.0, 1.0))
        lon = np.float32(lam0) + np.arctan2(
            np.broadcast_to(x, rho2.shape), c * np.float32(math.cos(phi0)) - y * np.float32(math.sin(phi0))
        )
        return lat, lon, inside, np.sqrt(rho2)

    def _mercator(self, lat: np.ndarray, lon: np.ndarray, z: int, view: View) -> tuple[np.ndarray, np.ndarray]:
        size = TILE * (1 << z)
        latc = np.clip(lat.astype(np.float64), -math.radians(MAX_LAT), math.radians(MAX_LAT))
        px = (lon.astype(np.float64) / (2 * math.pi) + 0.5) * size
        # longitudes ramenées autour de la vue : pas de coupure à l'antiméridien
        ref = (math.radians(view.lon) / (2 * math.pi) + 0.5) * size
        px = ref + ((px - ref + size / 2) % size) - size / 2
        py = (0.5 - np.log(np.tan(math.pi / 4 + latc / 2)) / (2 * math.pi)) * size
        return px, py

    def _sample(self, px: np.ndarray, py: np.ndarray, z: int) -> np.ndarray:
        """Échantillonnage bilinéaire des tuiles du niveau z sous les pixels (px, py)."""
        n = 1 << z
        tx0, tx1 = int(math.floor(float(px.min()) / TILE)), int(math.floor(float(px.max()) / TILE))
        ty0, ty1 = max(0, int(math.floor(float(py.min()) / TILE))), min(n - 1, int(math.floor(float(py.max()) / TILE)))
        mh, mw = (ty1 - ty0 + 1) * TILE, (tx1 - tx0 + 1) * TILE
        mosaic = np.empty((mh, mw, 3), dtype=np.uint8)
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                mosaic[(ty - ty0) * TILE : (ty - ty0 + 1) * TILE, (tx - tx0) * TILE : (tx - tx0 + 1) * TILE] = self.tiles.tile(
                    z, tx, ty
                )
        u = np.clip(px - (tx0 * TILE + 0.5), 0, mw - 1.001)
        v = np.clip(py - (ty0 * TILE + 0.5), 0, mh - 1.001)
        x0, y0 = u.astype(np.int32), v.astype(np.int32)
        fx, fy = (u - x0).astype(np.float32)[:, None], (v - y0).astype(np.float32)[:, None]
        flat = mosaic.reshape(-1, 3)
        i00 = y0 * mw + x0  # indices à plat : bien plus rapide que l'indexation 2D
        a, b = np.take(flat, i00, axis=0).astype(np.float32), np.take(flat, i00 + 1, axis=0).astype(np.float32)
        top = a + (b - a) * fx
        a, b = np.take(flat, i00 + mw, axis=0).astype(np.float32), np.take(flat, i00 + mw + 1, axis=0).astype(np.float32)
        bottom = a + (b - a) * fx
        return top + (bottom - top) * fy

    def tiles_for(self, view: View) -> set[tuple[int, int, int]]:
        """Tuiles nécessaires à une vue (grille grossière d'échantillons) : pour les télécharger avant le rendu."""
        zf = level(view)
        z0 = int(math.floor(zf))
        step = 24
        sub = Renderer.__new__(Renderer)
        sub.cx, sub.cy = self.cx, self.cy
        sub.gx = self.gx[:, ::step]
        sub.gy = self.gy[::step, :]
        lat, lon, inside, _ = sub._sphere(view)
        if not inside.any():
            return set()
        out: set[tuple[int, int, int]] = set()
        w1 = zf - z0 if z0 < MAX_ZOOM else 0.0
        levels = ([z0] if w1 < 0.97 else []) + ([z0 + 1] if w1 > 0.03 else [])  # comme background()
        for z in levels:
            px, py = self._mercator(lat[inside], lon[inside], z, view)
            n = 1 << z
            for tx in range(int(px.min() // TILE), int(px.max() // TILE) + 1):
                for ty in range(max(0, int(py.min() // TILE)), min(n - 1, int(py.max() // TILE)) + 1):
                    out.add((z, tx % n, ty))
        return out

    def background(self, view: View) -> np.ndarray:
        lat, lon, inside, rho = self._sphere(view)
        if inside.all():  # descendu : la Terre remplit l'écran, ni espace ni halo à calculer
            img = np.empty((self.h, self.w, 3), dtype=np.float32)
        else:
            img = np.broadcast_to(SPACE, (self.h, self.w, 3)).astype(np.float32) + self.stars
            # halo de l'atmosphère autour du globe, visible tant que le bord du globe est à l'écran
            halo = np.exp(-np.clip(rho - 1.0, 0, None) * view.scale / 22.0).astype(np.float32)[..., None]
            img = img * (1 - halo * 0.9) + ATMOSPHERE * halo * 0.75
        if inside.any():
            ys, xs = np.nonzero(inside)
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            sl = (slice(y0, y1), slice(x0, x1))
            m = inside[sl]
            zf = level(view)
            z0 = int(math.floor(zf))
            la, lo = lat[sl][m], lon[sl][m]
            w1 = float(zf - z0) if z0 < MAX_ZOOM else 0.0
            # deux niveaux de tuiles mélangés (pas de saut de netteté) ; un niveau qui ne pèse presque rien est sauté
            sat = self._sample(*self._mercator(la, lo, z0, view), z0) if w1 < 0.97 else None
            if w1 > 0.03:
                fine = self._sample(*self._mercator(la, lo, z0 + 1, view), z0 + 1)
                sat = fine if sat is None else sat + (fine - sat) * w1
            assert sat is not None
            # bord du globe : un peu plus sombre et bleuté (épaisseur de l'atmosphère), invisible une fois descendu
            c = np.sqrt(np.clip(1.0 - rho[sl][m] ** 2, 0, 1)).astype(np.float32)[:, None]
            sat = sat * (0.55 + 0.45 * np.sqrt(c)) + ATMOSPHERE * (1 - c) ** 3 * 0.55
            block = img[sl]
            block[m] = sat * 0.85  # un peu assombri : le tracé doré ressort
        return np.clip(img * self.vignette, 0, 255).astype(np.uint8)

    # -- premier plan : tracé, repères, étiquettes -----------------------------

    def font(self, size: int) -> Any:
        if size not in self._fonts:
            try:
                self._fonts[size] = (
                    ImageFont.truetype(str(self.font_path), size) if self.font_path else ImageFont.load_default(size)
                )
            except OSError:
                self._fonts[size] = ImageFont.load_default(size)
        return self._fonts[size]

    def view_at(self, f: float) -> View:
        v = self.plan.view(f)
        return View(v.lon, v.lat, v.scale * self.k)

    def _screen(self, view: View, pts: Sequence[LonLat]) -> list[tuple[float, float]] | None:
        if not pts:
            return None
        arr = np.asarray(pts, dtype=np.float64)
        x, y, vis = project(view, arr[:, 0], arr[:, 1], self.cx, self.cy)
        if not vis.all():
            return None
        return list(zip(x.tolist(), y.tolist(), strict=True))

    def _runs(self, view: View, pts: Sequence[LonLat]) -> list[list[tuple[float, float]]]:
        """Morceaux visibles d'une ligne (face visible du globe, pas trop loin hors de l'écran)."""
        arr = np.asarray(pts, dtype=np.float64)
        x, y, vis = project(view, arr[:, 0], arr[:, 1], self.cx, self.cy)
        vis &= (x > -self.w) & (x < 2 * self.w) & (y > -self.h) & (y < 2 * self.h)
        runs: list[list[tuple[float, float]]] = []
        cur: list[tuple[float, float]] = []
        for xi, yi, ok in zip(x.tolist(), y.tolist(), vis.tolist(), strict=True):
            if ok:
                cur.append((xi, yi))
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        return [r for r in runs if len(r) >= 2]

    def _rivers(self, layer: Image.Image, view: View, alpha: int) -> Image.Image:
        """Ce que le lieu relie (fleuves, routes) : trait bleu fin et son nom, posé sur sa partie visible au plus loin des
        repères des bouts et des autres noms (sinon « Main » recouvrait « Bamberg »)."""
        sharp = Image.new("RGBA", (self.w * 2, self.h * 2), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sharp)
        spots: list[tuple[str, tuple[float, float]]] = []
        box = (0.1 * self.w, 0.2 * self.h, 0.9 * self.w, 0.85 * self.h)  # sous le titre d'accroche
        avoid = [p for e in self.plan.ends if (p := (self._screen(view, [(e.lon, e.lat)]) or [None])[0])]
        for river in self.plan.rivers:
            inner: list[tuple[float, float]] = []
            for line in river.lines:
                for run in self._runs(view, line):
                    sd.line([(x * 2, y * 2) for x, y in run], fill=(*RIVER, alpha), width=8, joint="curve")
                    inner += [p for p in run if box[0] < p[0] < box[2] and box[1] < p[1] < box[3]]
            if inner:
                others = avoid + [xy for _, xy in spots]
                best = (
                    max(inner, key=lambda q: min((math.hypot(q[0] - o[0], q[1] - o[1]) for o in others), default=0.0))
                    if others
                    else inner[len(inner) // 2]
                )
                spots.append((river.name, best))
        layer = Image.alpha_composite(layer, sharp.reduce(2))
        d = ImageDraw.Draw(layer)
        font = self.font(40)
        for name, (x, y) in spots:
            left, top, right, bottom = d.textbbox((0, 0), name, font=font, stroke_width=5)
            d.text(
                (x - (right - left) / 2, y - (bottom - top) - 16),
                name,
                font=font,
                fill=(*RIVER, alpha),
                stroke_width=5,
                stroke_fill=(6, 14, 30, alpha),
            )
        return layer

    def _partial(self, p: float) -> tuple[list[list[LonLat]], LonLat | None]:
        """Les traits dessinés à l'avancement p (0-1) et la pointe du tracé."""
        if not self.plan.strokes or p <= 0:
            return [], None
        stop = p * self.total
        out: list[list[LonLat]] = []
        tip: LonLat | None = None
        for stroke, cum in zip(self.plan.strokes, self.lengths, strict=True):
            if cum[0] >= stop:
                break
            if cum[-1] <= stop:
                out.append(stroke)
                tip = stroke[-1]
                continue
            k = next(i for i, d in enumerate(cum) if d > stop)
            a, b = stroke[k - 1], stroke[k]
            t = (stop - cum[k - 1]) / max(1e-12, cum[k] - cum[k - 1])
            tip = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            out.append([*stroke[:k], tip])
            break
        return out, tip

    def _label(
        self,
        draw: ImageDraw.ImageDraw,
        xy: tuple[float, float],
        text: str,
        size: int,
        color: tuple[int, int, int],
        alpha: int,
        dot: int,
    ) -> None:
        x, y = xy
        font = self.font(size)
        draw.ellipse((x - dot - 3, y - dot - 3, x + dot + 3, y + dot + 3), fill=(10, 12, 20, alpha))
        draw.ellipse((x - dot, y - dot, x + dot, y + dot), fill=(*color, alpha))
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=6)
        tw, th = right - left, bottom - top
        gap = dot + 18
        lx = x + gap if x + gap + tw < self.w - 40 else x - gap - tw
        lx = min(max(40.0, lx), self.w - 40.0 - tw)
        ly = min(max(140.0, y - th / 2 - top), self.h - 260.0)
        draw.text((lx, ly), text, font=font, fill=(*color, alpha), stroke_width=6, stroke_fill=(8, 10, 18, alpha))

    def overlay(self, f: float, duration_s: float) -> Image.Image | None:
        plan, view = self.plan, self.view_at(f)
        p = plan.progress(f)
        fade = 0.3 / max(duration_s, 0.5)  # 0,3 s d'apparition
        layer = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        drawn = False
        # grands repères de la vue large
        a, b = plan.context_show
        if plan.context and a < f < b:
            alpha = int(255 * min(1.0, (f - a) / fade, (b - f) / fade))
            draw = ImageDraw.Draw(layer)
            for c in plan.context:
                pts = self._screen(view, [(c.lon, c.lat)])
                if pts:
                    self._label(draw, pts[0], c.name, 44, (190, 230, 255), max(0, alpha), 7)
                    drawn = True
        # ce que le lieu relie, en bleu, dès que l'on s'approche de la Terre
        if plan.rivers and f > 0.12:
            layer = self._rivers(layer, view, int(220 * min(1.0, (f - 0.12) / 0.1)))
            drawn = True
        # tracé : halo flou puis trait net, dessiné deux fois plus grand puis réduit (lissage)
        strokes, tip = self._partial(p)
        if strokes:
            glow = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow)
            sharp = Image.new("RGBA", (self.w * 2, self.h * 2), (0, 0, 0, 0))
            sd = ImageDraw.Draw(sharp)
            for s in strokes:
                for pts in self._runs(view, s):
                    gd.line(pts, fill=(*GOLD, 170), width=26, joint="curve")
                    sd.line([(x * 2, y * 2) for x, y in pts], fill=(255, 214, 80, 255), width=16, joint="curve")
            layer = Image.alpha_composite(layer, glow.filter(ImageFilter.GaussianBlur(11)))
            layer = Image.alpha_composite(layer, sharp.reduce(2))
            drawn = True
            if tip and p < 0.999:
                pts = self._screen(view, [tip])
                if pts:
                    x, y = pts[0]
                    d = ImageDraw.Draw(layer)
                    d.ellipse((x - 13, y - 13, x + 13, y + 13), fill=(*GOLD, 110))
                    d.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(255, 250, 230, 255))
        # lieu sans tracé : un anneau qui pulse et son nom
        if not plan.strokes and p > 0:
            pts = self._screen(view, [(plan.place.lon, plan.place.lat)])
            if pts:
                x, y = pts[0]
                d = ImageDraw.Draw(layer)
                ring = 14 + 26 * ((f * duration_s * 0.8) % 1.0)
                d.ellipse((x - ring, y - ring, x + ring, y + ring), outline=(*GOLD, int(220 * (1 - (ring - 14) / 26))), width=5)
                self._label(d, (x, y), plan.place.name, 52, (255, 236, 170), int(255 * min(1.0, p / 0.3)), 10)
                drawn = True
        # repères des bouts : le départ dès le début du tracé, l'arrivée quand le trait l'atteint
        if plan.ends and p > 0:
            d = ImageDraw.Draw(layer)
            for k, e in enumerate(plan.ends):
                shown = p if k == 0 or len(plan.ends) == 1 else (p - 0.9) / 0.1
                alpha = int(255 * min(1.0, max(0.0, shown / 0.12)))
                pts = self._screen(view, [(e.lon, e.lat)])
                if pts and alpha > 0:
                    self._label(d, pts[0], e.name, 50, (255, 255, 255), alpha, 9)
                    drawn = True
        if self.credit:
            d = ImageDraw.Draw(layer)
            font = self.font(22)
            left, _, right, _ = d.textbbox((0, 0), self.credit, font=font)
            d.text(((self.w - (right - left)) / 2, self.h - 44), self.credit, font=font, fill=(255, 255, 255, 150))
            drawn = True
        return layer if drawn else None

    def frame(self, f: float, duration_s: float) -> np.ndarray:
        img = self.background(self.view_at(f))
        over = self.overlay(f, duration_s)
        if over is None:
            return img
        return np.asarray(Image.alpha_composite(Image.fromarray(img).convert("RGBA"), over).convert("RGB"))


# ---------------------------------------------------------------------------
# Scène complète
# ---------------------------------------------------------------------------


def prepare(spec: MapSpec, resolver: GeoResolver) -> Plan:
    """Résout le lieu et ses repères (réseau, puis cache), puis cale la caméra. MapError si le lieu est introuvable."""
    place = resolver.resolve(spec.place, shape=True)
    if not place:
        raise MapError(f"lieu introuvable sur Wikipédia et OpenStreetMap : « {spec.place} »")
    ends = [p for n in spec.ends[:2] if (p := resolver.resolve(n, shape=False))]
    context = [p for n in spec.context[:3] if (p := resolver.resolve(n, shape=False))]
    rivers = [p for n in spec.lines[:3] if (p := resolver.resolve(n, shape=True))]
    log.info(
        "maps.plan",
        place=place.name,
        source=place.source,
        pieces=len(place.lines),
        ends=[e.name for e in ends],
        context=[c.name for c in context],
        lines=[(r.name, len(r.lines)) for r in rivers],
    )
    return make_plan(place, ends, context, rivers)


def _renderer(
    plan: Plan, cache_root: Path, user_agent: str, font_path: Path | None, lang: str, size: tuple[int, int]
) -> Renderer:
    tiles = TileCache(cache_root / "tiles" / TILE_SET, user_agent=user_agent)
    return Renderer(plan, tiles, font_path, CREDIT.get(lang, CREDIT["en"]), size=size)


def render_clip(
    plan: Plan,
    out: Path,
    duration_s: float,
    *,
    cache_root: Path,
    user_agent: str = DEFAULT_USER_AGENT,
    font_path: Path | None = None,
    lang: str = "fr",
    size: tuple[int, int] = (W, H),
) -> float:
    """Clip MP4 de la scène (1080×1920, 30 i/s) ; renvoie sa durée."""
    r = _renderer(plan, cache_root, user_agent, font_path, lang, size)
    n = max(2, round(duration_s * FPS))
    try:
        wanted: set[tuple[int, int, int]] = set()
        for i in range(0, n, 3):
            wanted |= r.tiles_for(r.view_at(i / (n - 1)))
        fetched = r.tiles.prefetch(wanted)
        log.info("maps.tiles", wanted=len(wanted), downloaded=fetched, missing=r.tiles.missing)
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{r.w}x{r.h}",
            "-r",
            str(FPS),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "17",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out),
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.stdin is not None
        try:
            for i in range(n):
                proc.stdin.write(r.frame(i / (n - 1), duration_s).tobytes())
        finally:
            proc.stdin.close()
            err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            code = proc.wait()
        if code != 0:
            raise MapError(f"ffmpeg a échoué pour la carte : {err[-500:]}")
    finally:
        r.tiles.close()
    return n / FPS


def render_still(
    plan: Plan,
    out: Path,
    *,
    cache_root: Path,
    user_agent: str = DEFAULT_USER_AGENT,
    font_path: Path | None = None,
    lang: str = "fr",
    duration_s: float = 6.0,
    at: float = 0.97,
    size: tuple[int, int] = (W, H),
) -> Path:
    """Image du storyboard : la fin de la scène, tout tracé."""
    r = _renderer(plan, cache_root, user_agent, font_path, lang, size)
    try:
        r.tiles.prefetch(r.tiles_for(r.view_at(at)))
        out.parent.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        Image.fromarray(r.frame(at, duration_s)).save(buf, format="PNG")
        out.write_bytes(buf.getvalue())
    finally:
        r.tiles.close()
    return out


def scene_plan(settings: Any, spec: MapSpec, lang: str) -> Plan:
    """Plan d'une scène carte avec les réglages du worker (caches dans DATA_DIR/maps)."""
    resolver = GeoResolver(settings.data_dir / "maps" / "geo", lang=lang, user_agent=settings.effective_wikipedia_user_agent)
    return prepare(spec, resolver)


def font_for(settings: Any) -> Path | None:
    p = Path(settings.fonts_dir) / FONT_FILE
    return p if p.is_file() else None
