from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
import re
from typing import Iterable


MARKERS = {
    "COM",
    "PT",
    "SUG",
    "CONT",
    "INDS",
    "RES",
}

BOOK_CODES = {
    "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT",
    "1SA", "2SA", "1KI", "2KI", "1CH", "2CH", "EZR", "NEH",
    "EST", "JOB", "PSA", "PRO", "ECC", "SNG", "ISA", "JER",
    "LAM", "EZK", "DAN", "HOS", "JOL", "AMO", "OBA", "JON",
    "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL", "MAT",
    "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL",
    "EPH", "PHP", "COL", "1TH", "2TH", "1TI", "2TI", "TIT",
    "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN", "3JN",
    "JUD", "REV",
}

WORD_RE = re.compile(
    r"[^\W\d_]+(?:['’\-][^\W\d_]+)*",
    re.UNICODE,
)

URL_RE = re.compile(
    r"(?:https?://|www\.)\S+",
    re.IGNORECASE,
)

EMAIL_RE = re.compile(
    r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
    re.UNICODE,
)

SFM_MARKER_RE = re.compile(
    r"\\[A-Za-z][A-Za-z0-9]*\*?",
)

VERSE_CODE_RE = re.compile(
    r"\b[1-3]?[A-Z]{2,3}[ .]\d+(?::|\.)\d+(?:-\d+)?\b"
)

VERSE_NAME_RE = re.compile(
    r"\b(?:[1-3]\s+)?"
    r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}"
    r"(?:\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,})?"
    r"\s+\d+:\d+(?:-\d+)?\b",
    re.UNICODE,
)

MARKER_PREFIX_RE = re.compile(
    r"(?im)^[ \t]*(?:COM|PT|SUG|CONT|IndS|RES)[ \t]*:"
)

OPTION_PREFIX_RE = re.compile(
    r"(?m)^[ \t]*[A-ZÁÉÍÓÚÜÑ][\)\.][ \t]*"
)


@dataclass(frozen=True)
class SpellToken:
    start: int
    end: int
    word: str


def _overlaps(
    start: int,
    end: int,
    spans: list[tuple[int, int]],
) -> bool:
    for span_start, span_end in spans:
        if start < span_end and end > span_start:
            return True
    return False


def excluded_spans(
    text: str,
) -> list[tuple[int, int]]:
    spans = []

    for regex in (
        URL_RE,
        EMAIL_RE,
        SFM_MARKER_RE,
        VERSE_CODE_RE,
        VERSE_NAME_RE,
        MARKER_PREFIX_RE,
        OPTION_PREFIX_RE,
    ):
        spans.extend(
            (match.start(), match.end())
            for match in regex.finditer(
                text
            )
        )

    spans.sort()
    return spans


def token_is_structural(
    text: str,
    token: SpellToken,
) -> bool:
    word = token.word
    upper = word.upper()

    if upper in MARKERS:
        return True

    if upper in BOOK_CODES:
        return True

    # Acrónimos cortos: DHH, NVI, NTV, XML, SFM, CBT...
    if (
        word.isupper()
        and 2 <= len(word) <= 6
    ):
        return True

    # A), B), C) y similares, incluso si el regex de prefijo no alcanza
    # una letra aislada por formato extraño.
    if len(word) == 1:
        after = text[
            token.end:
            token.end + 1
        ]
        if after in {
            ")",
            ".",
        }:
            return True

    # No revisar la parte alfabética de un identificador pegado a números.
    before = (
        text[token.start - 1]
        if token.start > 0
        else ""
    )
    after = (
        text[token.end]
        if token.end < len(text)
        else ""
    )
    if before.isdigit() or after.isdigit():
        return True

    return False


def iter_spell_tokens(
    text: str,
) -> Iterable[SpellToken]:
    spans = excluded_spans(
        text
    )

    for match in WORD_RE.finditer(
        text
    ):
        token = SpellToken(
            start=match.start(),
            end=match.end(),
            word=match.group(0),
        )

        if _overlaps(
            token.start,
            token.end,
            spans,
        ):
            continue

        if token_is_structural(
            text,
            token,
        ):
            continue

        yield token


def unique_words(
    text: str,
) -> list[str]:
    seen = set()
    result = []

    for token in iter_spell_tokens(
        text
    ):
        key = token.word.casefold()
        if key in seen:
            continue
        seen.add(
            key
        )
        result.append(
            token.word
        )

    return result


def load_plain_wordlist(
    path: str | Path,
) -> set[str]:
    path = Path(path)
    words = set()

    lines = path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    for index, raw in enumerate(
        lines
    ):
        value = raw.strip()

        if not value:
            continue

        # Primera línea numérica en archivos .dic de Hunspell.
        if (
            index == 0
            and value.isdigit()
        ):
            continue

        # Hunspell: palabra/FLAGS y opcionalmente campos morfológicos.
        value = value.split(
            "\t",
            1,
        )[0]
        value = re.sub(
            r"(?<!\\)/.*$",
            "",
            value,
        )
        value = value.replace(
            r"\/",
            "/",
        ).strip()

        if not value:
            continue

        for token in WORD_RE.finditer(
            value
        ):
            word = token.group(
                0
            ).strip()
            if word:
                words.add(
                    word.casefold()
                )

    return words


class WordListBackend:
    def __init__(
        self,
        words: Iterable[str] = (),
    ):
        self.words = {
            str(word).strip().casefold()
            for word in words
            if str(word).strip()
        }

    def lookup(
        self,
        word: str,
    ) -> bool:
        return (
            str(word).casefold()
            in self.words
        )

    def suggest(
        self,
        word: str,
        limit: int = 6,
    ) -> list[str]:
        source = str(
            word
        )
        key = source.casefold()

        candidates = get_close_matches(
            key,
            self.words,
            n=max(
                1,
                int(limit),
            ),
            cutoff=0.72,
        )

        result = []
        for candidate in candidates:
            if source[:1].isupper():
                candidate = (
                    candidate[:1].upper()
                    + candidate[1:]
                )
            result.append(
                candidate
            )

        return result
