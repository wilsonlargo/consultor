from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import html
import json
import re
import urllib.error
import urllib.request


HELLOAO_BASE = "https://bible.helloao.org/api/c"
DARBY_BASE = "https://www.sermonindex.net/commentary/darbynotes"


@dataclass(frozen=True)
class ContextProvider:
    key: str
    label: str
    group: str
    kind: str
    description: str
    license_name: str
    license_url: str
    attribution: str


PROVIDERS = (
    ContextProvider(
        key="darby-translation-notes",
        label="Darby Translation Notes",
        group="notes",
        kind="darby",
        description=(
            "Notas históricas de traducción de J. N. Darby. "
            "Incluyen observaciones sobre hebreo/griego, traducciones "
            "alternativas y decisiones léxicas."
        ),
        license_name="Dominio público",
        license_url=(
            "https://crosswire.org/sword/modules/"
            "ModInfo.jsp?modName=DTN"
        ),
        attribution=(
            "Notes to J. N. Darby's Translation of the Bible "
            "(Public Domain)."
        ),
    ),
    ContextProvider(
        key="tyndale",
        label="Tyndale Open Study Notes",
        group="notes",
        kind="helloao",
        description=(
            "Notas modernas de estudio y contexto. No son notas de "
            "traducción propiamente dichas, por eso se identifican como "
            "notas de estudio."
        ),
        license_name="CC BY-SA 4.0",
        license_url=(
            "https://creativecommons.org/licenses/by-sa/4.0/"
        ),
        attribution=(
            "Tyndale Open Study Notes © Tyndale House Publishers, "
            "licensed CC BY-SA 4.0."
        ),
    ),
    ContextProvider(
        key="adam-clarke",
        label="Adam Clarke Bible Commentary",
        group="commentary",
        kind="helloao",
        description="Comentario bíblico histórico.",
        license_name="Dominio público",
        license_url=(
            "https://creativecommons.org/publicdomain/mark/1.0/"
        ),
        attribution="Adam Clarke Bible Commentary (Public Domain).",
    ),
    ContextProvider(
        key="jamieson-fausset-brown",
        label="Jamieson-Fausset-Brown",
        group="commentary",
        kind="helloao",
        description="Comentario bíblico histórico.",
        license_name="Dominio público",
        license_url=(
            "https://creativecommons.org/publicdomain/mark/1.0/"
        ),
        attribution=(
            "Jamieson-Fausset-Brown Bible Commentary (Public Domain)."
        ),
    ),
    ContextProvider(
        key="john-calvin",
        label="John Calvin's Commentaries",
        group="commentary",
        kind="helloao",
        description="Comentarios históricos de Juan Calvino.",
        license_name="Dominio público",
        license_url=(
            "https://creativecommons.org/publicdomain/mark/1.0/"
        ),
        attribution="John Calvin's Commentaries (Public Domain).",
    ),
    ContextProvider(
        key="john-gill",
        label="John Gill Bible Commentary",
        group="commentary",
        kind="helloao",
        description="Comentario bíblico histórico.",
        license_name="Dominio público",
        license_url=(
            "https://creativecommons.org/publicdomain/mark/1.0/"
        ),
        attribution="John Gill Bible Commentary (Public Domain).",
    ),
    ContextProvider(
        key="keil-delitzsch",
        label="Keil & Delitzsch (AT)",
        group="commentary",
        kind="helloao",
        description="Comentario histórico del Antiguo Testamento.",
        license_name="Dominio público",
        license_url=(
            "https://creativecommons.org/publicdomain/mark/1.0/"
        ),
        attribution=(
            "Keil and Delitzsch Old Testament Commentary "
            "(Public Domain)."
        ),
    ),
    ContextProvider(
        key="matthew-henry",
        label="Matthew Henry Bible Commentary",
        group="commentary",
        kind="helloao",
        description="Comentario bíblico histórico.",
        license_name="Dominio público",
        license_url=(
            "https://creativecommons.org/publicdomain/mark/1.0/"
        ),
        attribution="Matthew Henry Bible Commentary (Public Domain).",
    ),
)


PROVIDER_BY_KEY = {
    provider.key: provider
    for provider in PROVIDERS
}


def providers_for_group(
    group: str,
) -> list[ContextProvider]:
    return [
        provider
        for provider in PROVIDERS
        if provider.group == group
    ]


def provider_by_key(
    key: str,
) -> ContextProvider:
    return PROVIDER_BY_KEY[
        key
    ]


def split_reference(
    reference: str,
) -> tuple[str, int, int]:
    match = re.match(
        r"^([1-3]?[A-Z]{2,3})\.(\d+)\.(\d+)",
        str(reference or "").strip().upper(),
    )
    if not match:
        raise ValueError(
            f"VerseRef inválido: {reference}"
        )

    return (
        match.group(1),
        int(match.group(2)),
        int(match.group(3)),
    )


def _flatten_content(
    value,
) -> str:
    if value is None:
        return ""

    if isinstance(
        value,
        str,
    ):
        return value

    if isinstance(
        value,
        (int, float),
    ):
        return str(value)

    if isinstance(
        value,
        list,
    ):
        parts = [
            _flatten_content(
                item
            )
            for item in value
        ]
        return " ".join(
            part.strip()
            for part in parts
            if part.strip()
        )

    if isinstance(
        value,
        dict,
    ):
        if value.get("text") not in (
            None,
            "",
        ):
            return _flatten_content(
                value.get("text")
            )

        if value.get("content") not in (
            None,
            "",
        ):
            return _flatten_content(
                value.get("content")
            )

        parts = []
        for key in (
            "heading",
            "title",
            "value",
        ):
            if value.get(key) not in (
                None,
                "",
            ):
                parts.append(
                    _flatten_content(
                        value.get(key)
                    )
                )

        return " ".join(
            part.strip()
            for part in parts
            if part.strip()
        )

    return str(value)


def parse_helloao_commentary(
    payload: dict,
    *,
    fallback_book: str,
    fallback_chapter: int,
) -> tuple[list[dict], dict]:
    commentary = (
        payload.get("commentary")
        or {}
    )
    book_data = (
        payload.get("book")
        or {}
    )
    chapter_data = (
        payload.get("chapter")
        or {}
    )

    book = str(
        book_data.get("id")
        or fallback_book
    ).upper()

    chapter = int(
        chapter_data.get("number")
        or fallback_chapter
    )

    notes: list[dict] = []

    introduction = str(
        chapter_data.get(
            "introduction"
        )
        or ""
    ).strip()

    for item in (
        chapter_data.get("content")
        or []
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        number = item.get(
            "number"
        )

        if number in (
            None,
            "",
        ):
            continue

        try:
            verse = int(
                str(number).split(
                    "-",
                    1,
                )[0]
            )
        except ValueError:
            continue

        body = _flatten_content(
            item.get(
                "text"
                if "text" in item
                else "content"
            )
        ).strip()

        if not body:
            continue

        notes.append(
            {
                "reference": (
                    f"{book}.{chapter}.{verse}"
                ),
                "heading": "",
                "text": body,
            }
        )

    meta = {
        "provider_name": str(
            commentary.get("name")
            or commentary.get("englishName")
            or ""
        ),
        "license_url": str(
            commentary.get("licenseUrl")
            or ""
        ),
        "license_name": "",
        "introduction": introduction,
    }

    return (
        notes,
        meta,
    )


class _BlockTextParser(HTMLParser):
    BLOCK_TAGS = {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "li",
        "div",
        "section",
        "article",
    }

    SKIP_TAGS = {
        "script",
        "style",
        "svg",
        "noscript",
    }

    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )
        self.blocks: list[str] = []
        self._parts: list[str] = []
        self._skip_depth = 0

    def _flush(self):
        value = re.sub(
            r"\s+",
            " ",
            " ".join(
                self._parts
            ),
        ).strip()
        if value:
            self.blocks.append(
                value
            )
        self._parts = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        tag = tag.lower()

        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return

        if (
            self._skip_depth == 0
            and tag in self.BLOCK_TAGS
        ):
            self._flush()

    def handle_endtag(
        self,
        tag,
    ):
        tag = tag.lower()

        if tag in self.SKIP_TAGS:
            self._skip_depth = max(
                0,
                self._skip_depth - 1,
            )
            return

        if (
            self._skip_depth == 0
            and tag in self.BLOCK_TAGS
        ):
            self._flush()

    def handle_data(
        self,
        data,
    ):
        if self._skip_depth:
            return

        value = str(
            data
            or ""
        ).strip()
        if value:
            self._parts.append(
                value
            )

    def close(self):
        super().close()
        self._flush()


DARBY_BOOK_CODE = {
    "SNG": "SOS",
}


def parse_darby_html(
    raw_html: str,
    *,
    book: str,
    chapter: int,
) -> list[dict]:
    parser = _BlockTextParser()
    parser.feed(
        raw_html
    )
    parser.close()

    # Deduplicate nested DIV/P blocks while preserving order.
    blocks = []
    seen = set()

    for raw in parser.blocks:
        value = html.unescape(
            raw
        )
        value = re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

        if (
            not value
            or value in seen
        ):
            continue

        seen.add(
            value
        )
        blocks.append(
            value
        )

    notes = []
    pattern = re.compile(
        r"^\s*(\d+):(\d+)\s+(.+)$"
    )

    for block in blocks:
        match = pattern.match(
            block
        )
        if not match:
            continue

        block_chapter = int(
            match.group(1)
        )
        verse = int(
            match.group(2)
        )

        if block_chapter != int(
            chapter
        ):
            continue

        body = match.group(
            3
        ).strip()

        if not body:
            continue

        notes.append(
            {
                "reference": (
                    f"{book}.{chapter}.{verse}"
                ),
                "heading": "",
                "text": body,
            }
        )

    return notes


def _fetch_bytes(
    url: str,
    *,
    timeout: int = 45,
) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Consultor-App/20 "
                "(Bible translation consultation tool)"
            ),
            "Accept": (
                "application/json,text/html,"
                "application/xhtml+xml"
            ),
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:
        return response.read()


def fetch_context_chapter(
    provider_key: str,
    reference: str,
) -> dict:
    provider = provider_by_key(
        provider_key
    )
    book, chapter, _verse = (
        split_reference(
            reference
        )
    )

    if provider.kind == "helloao":
        url = (
            f"{HELLOAO_BASE}/"
            f"{provider.key}/"
            f"{book}/"
            f"{chapter}.json"
        )

        try:
            raw = _fetch_bytes(
                url
            )
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {
                    "provider": provider.key,
                    "provider_name": provider.label,
                    "book": book,
                    "chapter": chapter,
                    "notes": [],
                    "source_url": url,
                    "license_name": provider.license_name,
                    "license_url": provider.license_url,
                    "attribution": provider.attribution,
                    "introduction": "",
                    "fetched_at": (
                        datetime.now(
                            timezone.utc
                        ).isoformat()
                    ),
                }
            raise

        payload = json.loads(
            raw.decode(
                "utf-8"
            )
        )

        notes, remote_meta = (
            parse_helloao_commentary(
                payload,
                fallback_book=book,
                fallback_chapter=chapter,
            )
        )

        license_url = (
            remote_meta.get(
                "license_url"
            )
            or provider.license_url
        )

        return {
            "provider": provider.key,
            "provider_name": (
                remote_meta.get(
                    "provider_name"
                )
                or provider.label
            ),
            "book": book,
            "chapter": chapter,
            "notes": notes,
            "source_url": url,
            "license_name": (
                provider.license_name
            ),
            "license_url": (
                license_url
            ),
            "attribution": (
                provider.attribution
            ),
            "introduction": (
                remote_meta.get(
                    "introduction"
                )
                or ""
            ),
            "fetched_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }

    if provider.kind == "darby":
        remote_book = DARBY_BOOK_CODE.get(
            book,
            book,
        )

        url = (
            f"{DARBY_BASE}/"
            f"{remote_book}/"
            f"{chapter}"
        )

        try:
            raw = _fetch_bytes(
                url
            )
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raw = b""
            else:
                raise

        raw_html = raw.decode(
            "utf-8",
            errors="replace",
        )

        notes = parse_darby_html(
            raw_html,
            book=book,
            chapter=chapter,
        )

        return {
            "provider": provider.key,
            "provider_name": (
                provider.label
            ),
            "book": book,
            "chapter": chapter,
            "notes": notes,
            "source_url": url,
            "license_name": (
                provider.license_name
            ),
            "license_url": (
                provider.license_url
            ),
            "attribution": (
                provider.attribution
            ),
            "introduction": "",
            "fetched_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }

    raise ValueError(
        f"Proveedor no soportado: {provider.key}"
    )
