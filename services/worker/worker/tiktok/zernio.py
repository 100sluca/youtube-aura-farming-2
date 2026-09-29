"""Client de l'API Zernio, limité à ce que servent la publication TikTok et ses statistiques (https://docs.zernio.com).

Statistiques (docs/39) : `GET /analytics?platform=tiktok` (chaque vidéo sortie sur le compte, pages de 100),
`GET /analytics/tiktok/account-insights` (abonnés, j'aime, vidéos du compte) et `POST /posts/sync-external` (relecture
immédiate des vidéos publiées à la main dans TikTok). Incluses dans le plan gratuit (`hasAnalyticsAccess`, vérifié le
29/09) ; 402 `analytics_addon_required` sinon. Limite : 6 requêtes par seconde.

Envoi d'une vidéo en 3 appels : `POST /media/presign` (adresse d'envoi signée, valable 1 h), `PUT` du fichier vers le
stockage de Zernio (sans en-tête Authorization), puis `POST /posts` avec l'adresse publique du fichier. Le fichier
reste 7 jours en stockage temporaire, puis passe en stockage permanent quand la publication sort : on peut programmer
une publication jusqu'à 72 h à l'avance, comme l'envoi YouTube.

Réponses à connaître : `201` publication créée ; `207` quand `publishNow` a échoué chez TikTok (code 2xx, mais
`post.status = "failed"` et le message dans `platforms[].errorMessage`) ; `409` même contenu déjà publié sur le compte
dans les 24 h (`existingPostId`) ou envoi identique encore en cours (`idempotency_conflict`) ; `429` limite atteinte
(`Retry-After`).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://zernio.com/api/v1"
CHUNK = 1024 * 1024


class ZernioError(RuntimeError):
    """Réponse d'erreur de Zernio (ou de TikTok, relayée par Zernio)."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        retry_after: float | None = None,
        body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retry_after = retry_after
        self.body = body or {}


def _json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        return {"error": resp.text[:500]}
    return data if isinstance(data, dict) else {"data": data}


def _retry_after(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("Retry-After")
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _error(resp: httpx.Response, what: str) -> ZernioError:
    body = _json(resp)
    detail = body.get("error") or body.get("message") or resp.reason_phrase
    return ZernioError(
        f"Zernio {what} : {resp.status_code} {detail}",
        status=resp.status_code,
        code=body.get("code"),
        retry_after=_retry_after(resp),
        body=body,
    )


class ZernioClient:
    def __init__(
        self, api_key: str, *, base_url: str = BASE_URL, timeout: float = 60.0, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=20.0),
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "youtube-aura-farming/worker"},
            transport=transport,
        )
        # l'envoi du fichier va au stockage (R2), pas à l'API : jamais la clé dans ces requêtes
        self.storage = httpx.Client(timeout=httpx.Timeout(600.0, connect=20.0), transport=transport)

    def close(self) -> None:
        self.http.close()
        self.storage.close()

    def __enter__(self) -> ZernioClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get(self, path: str, what: str, **params: Any) -> dict[str, Any]:
        resp = self.http.get(f"{self.base_url}{path}", params=params or None)
        if resp.status_code >= 400:
            raise _error(resp, what)
        return _json(resp)

    # ---- Comptes -------------------------------------------------------------------------------------------------
    def accounts(self) -> list[dict[str, Any]]:
        """Comptes connectés à Zernio, toutes plateformes (`_id`, `platform`, `username`, `displayName`…)."""
        data = self._get("/accounts", "comptes")
        return [a for a in data.get("accounts") or [] if isinstance(a, dict)]

    def tiktok_accounts(self) -> list[dict[str, Any]]:
        return [a for a in self.accounts() if a.get("platform") == "tiktok"]

    def creator_info(self, account_id: str) -> dict[str, Any]:
        """Ce que TikTok autorise pour ce compte : niveaux de visibilité, interactions, `canPostMore`."""
        return self._get(f"/accounts/{account_id}/tiktok/creator-info", "compte TikTok", mediaType="video")

    # ---- Fichier ---------------------------------------------------------------------------------------------------
    def upload_video(self, path: str | Path, on_progress: Callable[[float], None] | None = None, attempts: int = 3) -> str:
        """Envoie le MP4 au stockage de Zernio et renvoie son adresse publique (à mettre dans `mediaItems`)."""
        p = Path(path)
        size = p.stat().st_size
        resp = self.http.post(
            f"{self.base_url}/media/presign", json={"filename": p.name, "contentType": "video/mp4", "size": size}
        )
        if resp.status_code >= 400:
            raise _error(resp, "adresse d'envoi")
        presigned = _json(resp)
        upload_url, public_url = presigned.get("uploadUrl"), presigned.get("publicUrl")
        if not upload_url or not public_url:
            raise ZernioError(f"Zernio adresse d'envoi : réponse incomplète {presigned}")

        def chunks() -> Iterator[bytes]:
            sent = 0
            with p.open("rb") as f:
                while block := f.read(CHUNK):
                    sent += len(block)
                    yield block
                    if on_progress:
                        on_progress(sent / size)

        for attempt in range(1, attempts + 1):
            try:
                # Content-Length explicite : le stockage refuse l'envoi « chunked » d'une adresse signée
                put = self.storage.put(
                    upload_url, content=chunks(), headers={"Content-Type": "video/mp4", "Content-Length": str(size)}
                )
            except httpx.TransportError:
                if attempt == attempts:
                    raise
                time.sleep(5 * attempt)
                continue
            if put.status_code < 300:
                return str(public_url)
            if attempt == attempts or put.status_code < 500:
                raise ZernioError(
                    f"Envoi du fichier refusé par le stockage : {put.status_code} {put.text[:300]}", status=put.status_code
                )
            time.sleep(5 * attempt)
        raise AssertionError("inatteignable")

    # ---- Publications ----------------------------------------------------------------------------------------------
    def create_post(self, body: dict[str, Any], idempotency_key: str) -> tuple[int, dict[str, Any]]:
        """Crée (et programme ou publie) une publication. Renvoie le code HTTP et le corps : 200/201/207/409 sont des
        réponses normales à interpréter (voir le docstring du module) ; les autres codes lèvent ZernioError."""
        resp = self.http.post(
            f"{self.base_url}/posts",
            json=body,
            headers={"Idempotency-Key": idempotency_key},
            timeout=httpx.Timeout(300.0, connect=20.0),
        )  # publishNow : TikTok peut être lent
        data = _json(resp)
        if resp.status_code == 409 and data.get("code") == "idempotency_conflict":
            raise _error(resp, "publication")  # le même envoi est encore en cours chez Zernio : attendre Retry-After
        if resp.status_code in (200, 201, 202, 207, 409):
            return resp.status_code, data
        raise _error(resp, "publication")

    def get_post(self, post_id: str) -> dict[str, Any]:
        return self._get(f"/posts/{post_id}", "publication").get("post") or {}

    # ---- Statistiques (docs/39-tiktok-partout.md) ------------------------------------------------------------------
    def post_analytics(
        self, account_id: str, *, days: int = 365, max_pages: int = 20
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Chiffres de chaque vidéo sortie sur le compte (publiée par l'appli ou à la main), toutes pages lues, et le
        résumé de la première page (`overview.lastSync` : dernier passage de Zernio chez TikTok). Seules les vidéos
        sorties y figurent : une publication programmée n'apparaît qu'une fois publiée. 366 jours au plus par requête."""
        since = (datetime.now(UTC) - timedelta(days=min(days, 365))).date().isoformat()
        posts: list[dict[str, Any]] = []
        overview: dict[str, Any] = {}
        for page in range(1, max_pages + 1):
            data = self._get(
                "/analytics",
                "statistiques des vidéos",
                platform="tiktok",
                accountId=account_id,
                fromDate=since,
                limit=100,
                page=page,
                sortBy="date",
                order="desc",
            )
            if page == 1:
                overview = data.get("overview") or {}
            posts += [p for p in data.get("posts") or [] if isinstance(p, dict)]
            pages = int((data.get("pagination") or {}).get("pages") or 1)
            if page >= pages:
                break
        return posts, overview

    def account_posts(self, account_id: str) -> list[dict[str, Any]]:
        """Les 25 dernières vidéos du compte lues en direct chez TikTok (id TikTok, légende, date, lien, j'aime,
        commentaires, partages ; pas les vues) : une vidéo y figure dès sa sortie, avant le passage de Zernio."""
        data = self._get(f"/accounts/{account_id}/posts", "vidéos du compte")
        return [p for p in data.get("posts") or [] if isinstance(p, dict)]

    def sync_external(self, account_id: str) -> dict[str, Any]:
        """Fait relire tout de suite chez TikTok les vidéos publiées à la main sur le compte (sinon Zernio ne repasse qu'au
        mieux toutes les 90 min) : elles apparaissent alors dans `post_analytics` avec leurs j'aime et commentaires.
        Zernio ignore un second appel dans les 15 s."""
        resp = self.http.post(f"{self.base_url}/posts/sync-external", json={"accountId": account_id})
        if resp.status_code >= 400:
            raise _error(resp, "relecture des vidéos du compte")
        return _json(resp).get("synced") or {}

    def account_insights(self, account_id: str) -> dict[str, Any]:
        """Compteurs du compte lus en direct chez TikTok : abonnés, abonnements, j'aime reçus, vidéos."""
        return self._get(
            "/analytics/tiktok/account-insights",
            "statistiques du compte",
            accountId=account_id,
            metrics="follower_count,following_count,likes_count,video_count",
        )
