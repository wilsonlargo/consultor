from __future__ import annotations

import difflib
import html
import re


TOKEN_RE = re.compile(r"\s+|[^\s]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text or "")


def diff_html(old_text: str, new_text: str) -> tuple[str, str]:
    """
    Devuelve dos fragmentos HTML:
      - versión anterior con eliminaciones/cambios resaltados;
      - versión actual con inserciones/cambios resaltados.

    Conserva el texto completo y solo añade <span> a los fragmentos que
    SequenceMatcher considera distintos.
    """
    old_tokens = _tokens(old_text)
    new_tokens = _tokens(new_text)

    matcher = difflib.SequenceMatcher(
        None,
        old_tokens,
        new_tokens,
        autojunk=False,
    )

    old_parts: list[str] = []
    new_parts: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old_chunk = html.escape(
            "".join(old_tokens[i1:i2])
        )
        new_chunk = html.escape(
            "".join(new_tokens[j1:j2])
        )

        if tag == "equal":
            old_parts.append(old_chunk)
            new_parts.append(new_chunk)

        elif tag == "delete":
            old_parts.append(
                '<span style="background:#f8dddd;'
                'text-decoration:line-through;">'
                f"{old_chunk}</span>"
            )

        elif tag == "insert":
            new_parts.append(
                '<span style="background:#dff2e2;'
                'font-weight:600;">'
                f"{new_chunk}</span>"
            )

        elif tag == "replace":
            if old_chunk:
                old_parts.append(
                    '<span style="background:#f8dddd;'
                    'text-decoration:line-through;">'
                    f"{old_chunk}</span>"
                )
            if new_chunk:
                new_parts.append(
                    '<span style="background:#dff2e2;'
                    'font-weight:600;">'
                    f"{new_chunk}</span>"
                )

    return (
        "".join(old_parts),
        "".join(new_parts),
    )
