from __future__ import annotations

import re

from .sfm_parser import VerseRecord


def _clean_verse_text(text: str) -> str:
    # Las notas \f...\f* ya no forman parte del texto visible del versículo,
    # pero el visor puede mostrar sus referencias [1], [2], etc.
    # Para copiar a ChatGPT se eliminan también esos indicadores.
    value = re.sub(r"\s*\[\d+\]\s*", " ", text or "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def build_sfm_range(
    verses: list[VerseRecord],
    start_index: int,
    end_index: int,
) -> str:
    r"""
    Devuelve únicamente marcadores de sección (\s, \s1, \s2...) y versículo
    (\v) del rango indicado.

    start_index/end_index son posiciones dentro de la lista del capítulo,
    inclusivas.
    """
    if not verses:
        return ""

    start_index = max(0, min(start_index, len(verses) - 1))
    end_index = max(0, min(end_index, len(verses) - 1))

    if end_index < start_index:
        start_index, end_index = end_index, start_index

    lines: list[str] = []

    for verse in verses[start_index:end_index + 1]:
        for section in verse.subtitle_anchors:
            marker = section.marker or r"\s"
            text = section.visible_text.strip()
            if text:
                lines.append(f"{marker} {text}")

        verse_text = _clean_verse_text(verse.text)
        if verse_text:
            lines.append(
                rf"\v {verse.verse} {verse_text}"
            )
        else:
            lines.append(
                rf"\v {verse.verse}"
            )

    return "\n".join(lines)
