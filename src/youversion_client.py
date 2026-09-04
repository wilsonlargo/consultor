from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests


class YouVersionError(RuntimeError):
    pass


class YouVersionClient:
    BASE_URL = "https://api.youversion.com/v1"

    def __init__(self, app_key: str, timeout: int = 15):
        self.app_key = (app_key or "").strip()
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        if not self.app_key:
            raise YouVersionError("No se ha configurado la App Key de YouVersion.")
        return {
            "X-YVP-App-Key": self.app_key,
            "Accept": "application/json",
            "Accept-Language": "es",
        }

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        url = f"{self.BASE_URL}{path}"
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params or {},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise YouVersionError(
                f"No fue posible conectar con YouVersion: {exc}"
            ) from exc

        if response.status_code == 401:
            raise YouVersionError(
                "YouVersion rechazó la App Key. Revisa la configuración."
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            extra = f" Intenta de nuevo en {retry_after} s." if retry_after else ""
            raise YouVersionError(
                "Se alcanzó temporalmente el límite de consultas de YouVersion."
                + extra
            )
        if not response.ok:
            try:
                data = response.json()
                detail = data.get("message") or data.get("error") or str(data)
            except Exception:
                detail = response.text[:300]
            raise YouVersionError(
                f"Error de YouVersion ({response.status_code}): {detail}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise YouVersionError(
                "YouVersion devolvió una respuesta que no es JSON válido."
            ) from exc

    def get_bibles(self, language_ranges: str = "es*") -> list[dict]:
        """
        Obtiene todas las Biblias disponibles para la App Key,
        paginando cuando sea necesario.
        """
        items: list[dict] = []
        page_token = None

        while True:
            params: dict[str, Any] = {
                "language_ranges[]": language_ranges,
                "page_size": 99,
            }
            if page_token:
                params["page_token"] = page_token

            payload = self._get("/bibles", params=params)
            items.extend(payload.get("data") or [])

            page_token = payload.get("next_page_token")
            if not page_token:
                break

        return items

    def get_bible(self, version_id: int) -> dict:
        payload = self._get(f"/bibles/{int(version_id)}")
        # Algunos recursos individuales llegan directamente y otros
        # pueden venir envueltos en "data". Aceptamos ambas formas.
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, dict) else payload

    def get_passage(
        self,
        version_id: int,
        usfm_reference: str,
        *,
        format_: str = "text",
    ) -> dict:
        safe_ref = quote(usfm_reference, safe=".-")
        payload = self._get(
            f"/bibles/{int(version_id)}/passages/{safe_ref}",
            params={
                "format": format_,
                "include_headings": "false",
                "include_notes": "false",
            },
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, dict) else payload

    def get_passage_with_attribution(
        self, version_id: int, usfm_reference: str
    ) -> dict:
        passage = self.get_passage(version_id, usfm_reference, format_="text")
        bible = self.get_bible(version_id)

        return {
            "passage": passage,
            "bible": bible,
            "attribution": (
                bible.get("copyright")
                or bible.get("promotional_content")
                or bible.get("promotionalContent")
                or ""
            ),
        }
