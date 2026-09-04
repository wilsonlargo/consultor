from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass
class FootnoteRecord:
    number: int
    text: str


@dataclass
class AnchorTarget:
    """
    Relación entre un texto visible en la interfaz y el texto SFM que Paratext
    usa para StartPosition / SelectedText / ContextBefore / ContextAfter.
    """
    kind: str
    reference: str
    visible_text: str
    source_text: str
    char_map: list[int]
    marker: str = ""

    def raw_position(self, visible_position: int) -> int:
        if not self.char_map:
            return 0
        if visible_position <= 0:
            return self.char_map[0]
        if visible_position >= len(self.char_map):
            return self.char_map[-1] + 1
        return self.char_map[visible_position]

    def selection_metadata(
        self,
        selection_start: int,
        selection_end: int,
        context_size: int = 25,
    ) -> dict:
        start_vis = max(0, min(selection_start, len(self.visible_text)))
        end_vis = max(0, min(selection_end, len(self.visible_text)))

        if end_vis < start_vis:
            start_vis, end_vis = end_vis, start_vis

        if start_vis == end_vis:
            raw_start = self.raw_position(start_vis)
            raw_end = raw_start
            selected = ""
        else:
            raw_start = self.raw_position(start_vis)
            last_visible = end_vis - 1
            if 0 <= last_visible < len(self.char_map):
                raw_end = self.char_map[last_visible] + 1
            else:
                raw_end = raw_start
            selected = self.visible_text[start_vis:end_vis]

        context_before = self.source_text[
            max(0, raw_start - context_size):raw_start
        ]
        context_after = self.source_text[
            raw_end:min(len(self.source_text), raw_end + context_size)
        ]

        return {
            "SelectedText": selected,
            "StartPosition": raw_start,
            "ContextBefore": context_before,
            "ContextAfter": context_after,
            "VerseRef": self.reference,
            "Verse": self.source_text,
            "Kind": self.kind,
        }


@dataclass
class VerseRecord:
    book: str
    chapter: str
    verse: str
    text: str
    subtitles: list[str] = field(default_factory=list)
    subtitle_anchors: list[AnchorTarget] = field(default_factory=list)
    footnotes: list[FootnoteRecord] = field(default_factory=list)
    source_text: str = ""
    anchor: AnchorTarget | None = None

    @property
    def reference(self):
        return f"{self.book}.{self.chapter}.{self.verse}"


@dataclass
class SfmDocument:
    path: Path
    book: str
    title: str
    verses: list[VerseRecord]


ID_RE = re.compile(r"^\\id\s+([0-9A-Za-z]{3,4})(?:\s+.*)?$", re.IGNORECASE)
MT_RE = re.compile(r"^\\mt\d*\s+(.*)$", re.IGNORECASE)
CHAPTER_RE = re.compile(r"^\\c\s+(\d+)", re.IGNORECASE)
VERSE_RE = re.compile(
    r"^\\v\s+([0-9]+(?:-[0-9]+)?[a-z]?)\s*(.*)$",
    re.IGNORECASE,
)
SECTION_MARKER_RE = re.compile(r"\\s\d*\s+", re.IGNORECASE)
SECTION_LINE_RE = re.compile(r"^\\s\d*\s+(.*)$", re.IGNORECASE)

FT_RE = re.compile(
    r"\\ft\s+(.*?)(?=\\[A-Za-z0-9]+\*?|\Z)",
    re.IGNORECASE | re.DOTALL,
)
FOOTNOTE_RE = re.compile(
    r"\\f(?:\s+.*?)?\\f\*",
    re.IGNORECASE | re.DOTALL,
)


def read_text(path: str | Path) -> str:
    p = Path(path)
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return p.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return p.read_text(encoding="utf-8", errors="replace")


def _clean_inline_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\\[A-Za-z0-9]+\*?", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _canonical_join(lines: list[str]) -> str:
    return " ".join(line.strip() for line in lines if line.strip()).strip()


def _find_footnotes(source: str) -> list[FootnoteRecord]:
    notes = []
    number = 0
    for match in FOOTNOTE_RE.finditer(source):
        number += 1
        block = match.group(0)
        parts = [
            _clean_inline_text(m.group(1))
            for m in FT_RE.finditer(block)
        ]
        note_text = " ".join(x for x in parts if x).strip()
        notes.append(FootnoteRecord(number, note_text))
    return notes


def _render_with_map(
    source: str,
    start: int,
    end: int,
    footnote_placeholder: bool = True,
) -> tuple[str, list[int]]:
    """
    Renderiza SFM a texto visible conservando un mapa carácter-visible →
    posición absoluta dentro de source.
    """
    out: list[str] = []
    char_map: list[int] = []
    i = max(0, start)
    end = min(len(source), end)
    footnote_number = 0

    def append_char(ch: str, raw_index: int):
        if ch.isspace():
            if not out or out[-1] == " ":
                return
            out.append(" ")
            char_map.append(raw_index)
        else:
            out.append(ch)
            char_map.append(raw_index)

    while i < end:
        # Nota al pie completa.
        if source.startswith("\\f", i):
            m = FOOTNOTE_RE.match(source, i)
            if m:
                footnote_number += 1
                if footnote_placeholder:
                    placeholder = f" [{footnote_number}] "
                    for ch in placeholder:
                        append_char(ch, i)
                i = m.end()
                continue

        # Cualquier marcador USFM.
        if source[i] == "\\":
            m = re.match(r"\\[A-Za-z0-9]+\*?", source[i:])
            if m:
                i += len(m.group(0))
                # El espacio inmediatamente posterior pertenece a la sintaxis
                # del marcador, no al texto seleccionado.
                if i < end and source[i] == " ":
                    i += 1
                continue

        append_char(source[i], i)
        i += 1

    # Trim sin perder correspondencia.
    while out and out[0] == " ":
        out.pop(0)
        char_map.pop(0)
    while out and out[-1] == " ":
        out.pop()
        char_map.pop()

    return "".join(out), char_map


def _verse_visible_anchor(
    source: str,
    reference: str,
    verse_number: str,
) -> AnchorTarget:
    prefix = re.match(
        r"^\\v\s+" + re.escape(verse_number) + r"\s*",
        source,
        re.IGNORECASE,
    )
    start = prefix.end() if prefix else 0

    section = SECTION_MARKER_RE.search(source, start)
    reference_marker = re.search(
        r"\\r\s+",
        source[start:],
        re.IGNORECASE,
    )

    end_candidates = []
    if section:
        end_candidates.append(section.start())
    if reference_marker:
        end_candidates.append(
            start + reference_marker.start()
        )

    end = (
        min(end_candidates)
        if end_candidates
        else len(source)
    )

    visible, mapping = _render_with_map(
        source,
        start,
        end,
        footnote_placeholder=True,
    )

    return AnchorTarget(
        kind="verse",
        reference=reference,
        visible_text=visible,
        source_text=source,
        char_map=mapping,
    )


def _section_anchors(
    source: str,
    reference: str,
) -> list[AnchorTarget]:
    anchors: list[AnchorTarget] = []

    for marker in SECTION_MARKER_RE.finditer(source):
        title_start = marker.end()

        # Termina en el siguiente marcador USFM.
        next_marker = re.search(
            r"\\[A-Za-z0-9]+",
            source[title_start:],
        )
        if next_marker:
            title_end = title_start + next_marker.start()
        else:
            title_end = len(source)

        visible, mapping = _render_with_map(
            source,
            title_start,
            title_end,
            footnote_placeholder=False,
        )
        if visible:
            anchors.append(
                AnchorTarget(
                    kind="section",
                    reference=reference,
                    visible_text=visible,
                    source_text=source,
                    char_map=mapping,
                    marker=marker.group(0).strip(),
                )
            )

    return anchors


def _make_verse_record(
    book: str,
    chapter: str,
    verse: str,
    block_lines: list[str],
    display_sections: list[AnchorTarget],
) -> VerseRecord:
    source = _canonical_join(block_lines)
    reference = f"{book}.{chapter}.{verse}"
    anchor = _verse_visible_anchor(
        source,
        reference,
        verse,
    )

    return VerseRecord(
        book=book,
        chapter=chapter,
        verse=verse,
        text=anchor.visible_text,
        subtitles=[a.visible_text for a in display_sections],
        subtitle_anchors=list(display_sections),
        footnotes=_find_footnotes(source),
        source_text=source,
        anchor=anchor,
    )


def parse_sfm(path: str | Path) -> SfmDocument:
    p = Path(path)
    text = read_text(p)
    lines = [
        line.rstrip()
        for line in text.splitlines()
        if line.strip()
    ]

    book = ""
    title = ""
    chapter = ""
    id_line = ""

    verses: list[VerseRecord] = []

    current_verse_number = ""
    current_block: list[str] = []
    current_display_sections: list[AnchorTarget] = []

    chapter_prefix: list[str] = []
    chapter_has_verse = False

    def finalize_current() -> list[AnchorTarget]:
        nonlocal current_verse_number, current_block, current_display_sections
        if not current_verse_number:
            return []

        record = _make_verse_record(
            book,
            chapter,
            current_verse_number,
            current_block,
            current_display_sections,
        )
        verses.append(record)

        # Secciones encontradas al final de este bloque se muestran antes del
        # siguiente versículo, pero conservan la referencia del versículo
        # anterior, tal como ocurre en los Notes_*.xml reales.
        trailing = _section_anchors(
            record.source_text,
            record.reference,
        )

        current_verse_number = ""
        current_block = []
        current_display_sections = []
        return trailing

    pending_sections: list[AnchorTarget] = []

    for raw_line in lines:
        stripped = raw_line.strip()

        m = ID_RE.match(stripped)
        if m:
            pending_sections.extend(finalize_current())
            book = m.group(1).upper()
            id_line = stripped
            continue

        m = MT_RE.match(stripped)
        if m:
            if not title:
                title = _clean_inline_text(m.group(1))
            continue

        m = CHAPTER_RE.match(stripped)
        if m:
            pending_sections.extend(finalize_current())
            chapter = m.group(1)
            chapter_has_verse = False
            chapter_prefix = []
            if id_line:
                chapter_prefix.append(id_line)
            chapter_prefix.append(stripped)
            pending_sections = []
            continue

        m = VERSE_RE.match(stripped)
        if m:
            # Al llegar a un nuevo versículo, primero se finaliza el anterior.
            pending_sections.extend(finalize_current())

            if not book:
                raise ValueError(
                    "El archivo no contiene un marcador \\id antes de los versículos."
                )
            if not chapter:
                raise ValueError(
                    "Se encontró \\v antes de un marcador \\c."
                )

            # Antes del primer versículo del capítulo, las \s se anclan a v.0.
            if not chapter_has_verse and chapter_prefix:
                prefix_source = _canonical_join(chapter_prefix)
                pre_sections = _section_anchors(
                    prefix_source,
                    f"{book}.{chapter}.0",
                )
                pending_sections = pre_sections + pending_sections

            current_verse_number = m.group(1)
            current_block = [stripped]
            current_display_sections = list(pending_sections)
            pending_sections = []
            chapter_has_verse = True
            continue

        if current_verse_number:
            # Todo hasta el siguiente \v pertenece al bloque source del
            # versículo actual: \p, \q, \f, \s, \r, etc.
            current_block.append(stripped)
        else:
            # Encabezado de capítulo previo a v.1.
            if chapter:
                chapter_prefix.append(stripped)

    finalize_current()

    if not book:
        raise ValueError("No se encontró el marcador \\id del libro.")
    if not verses:
        raise ValueError("No se encontraron versículos con marcador \\v.")
    if not title:
        title = book

    return SfmDocument(
        path=p,
        book=book,
        title=title,
        verses=verses,
    )
