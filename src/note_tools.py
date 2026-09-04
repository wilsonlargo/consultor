from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .notes_parser import NotesDocument, NoteMessage, contents_to_text


@dataclass
class NoteSearchHit:
    owner: str
    document: NotesDocument
    message: NoteMessage
    verse_ref: str
    thread: str
    date: str
    paragraph_index: int | None
    matched_text: str
    preview: str


@dataclass
class BulkApplyResult:
    changed_comments: int
    changed_paragraphs: int
    deleted_comments: int
    backup_path: Path | None


def compile_search_pattern(
    pattern: str,
    use_regex: bool = True,
    case_sensitive: bool = False,
):
    value = pattern or ""
    if not value:
        raise ValueError("Escriba un criterio de búsqueda.")

    if not use_regex:
        value = re.escape(value)

    flags = 0 if case_sensitive else re.IGNORECASE

    try:
        return re.compile(value, flags)
    except re.error as exc:
        raise ValueError(
            f"La expresión regular no es válida: {exc}"
        ) from exc


def _paragraphs(message: NoteMessage) -> list[ET.Element]:
    contents = message.element.find("Contents")
    if contents is None:
        return []
    return list(contents.findall("p"))


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(paragraph.itertext())


def _preview_text(text: str, match_start: int, match_end: int, radius: int = 70) -> str:
    text = (text or "").replace("\n", " ")
    start = max(0, match_start - radius)
    end = min(len(text), match_end + radius)
    preview = text[start:end].strip()

    if start > 0:
        preview = "…" + preview
    if end < len(text):
        preview = preview + "…"

    return preview


def search_document(
    document: NotesDocument,
    regex,
    operation: str = "search",
) -> list[NoteSearchHit]:
    """
    Busca en Contents de un NotesDocument.

    operation:
      search
      delete_comment
      delete_paragraph
      replace
    """
    hits: list[NoteSearchHit] = []

    for thread in document.threads:
        for message in thread.messages:
            paragraphs = _paragraphs(message)

            # Para borrar una nota completa basta una coincidencia por Comment.
            if operation == "delete_comment":
                full_text = message.contents or ""
                match = regex.search(full_text)
                if match:
                    hits.append(
                        NoteSearchHit(
                            owner=document.owner,
                            document=document,
                            message=message,
                            verse_ref=message.verse_ref,
                            thread=message.thread,
                            date=message.date,
                            paragraph_index=None,
                            matched_text=match.group(0),
                            preview=_preview_text(
                                full_text,
                                match.start(),
                                match.end(),
                            ),
                        )
                    )
                continue

            for index, paragraph in enumerate(paragraphs):
                paragraph_text = _paragraph_text(paragraph)
                match = regex.search(paragraph_text)
                if not match:
                    continue

                hits.append(
                    NoteSearchHit(
                        owner=document.owner,
                        document=document,
                        message=message,
                        verse_ref=message.verse_ref,
                        thread=message.thread,
                        date=message.date,
                        paragraph_index=index,
                        matched_text=match.group(0),
                        preview=_preview_text(
                            paragraph_text,
                            match.start(),
                            match.end(),
                        ),
                    )
                )

    return hits


def search_documents(
    documents: list[NotesDocument],
    pattern: str,
    use_regex: bool = True,
    case_sensitive: bool = False,
    operation: str = "search",
) -> list[NoteSearchHit]:
    regex = compile_search_pattern(
        pattern,
        use_regex=use_regex,
        case_sensitive=case_sensitive,
    )

    hits: list[NoteSearchHit] = []
    for document in documents:
        hits.extend(
            search_document(
                document,
                regex,
                operation=operation,
            )
        )
    return hits


def apply_bulk_operation(
    document: NotesDocument,
    hits: list[NoteSearchHit],
    pattern: str,
    operation: str,
    replacement: str = "",
    use_regex: bool = True,
    case_sensitive: bool = False,
) -> BulkApplyResult:
    """
    Aplica una edición masiva únicamente a UN NotesDocument.

    Se hace un único backup y una única escritura para toda la operación.
    """
    editable_hits = [
        hit
        for hit in hits
        if hit.document.path == document.path
    ]

    if not editable_hits:
        return BulkApplyResult(0, 0, 0, None)

    regex = compile_search_pattern(
        pattern,
        use_regex=use_regex,
        case_sensitive=case_sensitive,
    )

    changed_comments = set()
    changed_paragraphs = 0
    deleted_comments = 0

    if operation == "delete_comment":
        elements = []
        seen = set()

        for hit in editable_hits:
            element = hit.message.element
            identity = id(element)
            if identity in seen:
                continue
            seen.add(identity)
            elements.append(element)

        for element in elements:
            if element in list(document.root):
                document.root.remove(element)
                deleted_comments += 1

    elif operation == "delete_paragraph":
        # Agrupar por Comment y borrar de atrás hacia delante para que los
        # índices de los párrafos restantes no cambien.
        grouped: dict[int, tuple[ET.Element, set[int]]] = {}

        for hit in editable_hits:
            if hit.paragraph_index is None:
                continue

            element = hit.message.element
            key = id(element)

            if key not in grouped:
                grouped[key] = (
                    element,
                    set(),
                )
            grouped[key][1].add(
                hit.paragraph_index
            )

        for element, indexes in grouped.values():
            contents = element.find("Contents")
            if contents is None:
                continue

            paragraphs = list(
                contents.findall("p")
            )

            changed_here = False
            for index in sorted(indexes, reverse=True):
                if 0 <= index < len(paragraphs):
                    paragraph = paragraphs[index]
                    current = _paragraph_text(paragraph)

                    # Verificar nuevamente que aún coincide antes de borrar.
                    if regex.search(current):
                        contents.remove(paragraph)
                        changed_paragraphs += 1
                        changed_here = True

            if changed_here:
                changed_comments.add(
                    id(element)
                )

    elif operation == "replace":
        grouped: dict[int, tuple[ET.Element, set[int]]] = {}

        for hit in editable_hits:
            if hit.paragraph_index is None:
                continue

            element = hit.message.element
            key = id(element)

            if key not in grouped:
                grouped[key] = (
                    element,
                    set(),
                )
            grouped[key][1].add(
                hit.paragraph_index
            )

        for element, indexes in grouped.values():
            contents = element.find("Contents")
            if contents is None:
                continue

            paragraphs = list(
                contents.findall("p")
            )

            changed_here = False

            for index in sorted(indexes):
                if not (0 <= index < len(paragraphs)):
                    continue

                paragraph = paragraphs[index]
                current = _paragraph_text(paragraph)
                updated, count = regex.subn(
                    replacement,
                    current,
                )
                if count <= 0:
                    continue

                # Los Contents reales analizados usan <p> de texto simple.
                # Si existiera contenido anidado, se normaliza el párrafo a
                # texto plano para evitar una estructura XML inconsistente.
                for child in list(paragraph):
                    paragraph.remove(child)
                paragraph.text = updated or None

                changed_paragraphs += 1
                changed_here = True

            if changed_here:
                changed_comments.add(
                    id(element)
                )

    else:
        raise ValueError(
            f"Operación de edición no soportada: {operation}"
        )

    total_changes = (
        deleted_comments
        + changed_paragraphs
    )

    if total_changes == 0:
        return BulkApplyResult(
            changed_comments=0,
            changed_paragraphs=0,
            deleted_comments=0,
            backup_path=None,
        )

    backup = document.save_with_backup()
    document._parse()

    if operation == "delete_comment":
        changed_comment_count = deleted_comments
    else:
        changed_comment_count = len(
            changed_comments
        )

    return BulkApplyResult(
        changed_comments=changed_comment_count,
        changed_paragraphs=changed_paragraphs,
        deleted_comments=deleted_comments,
        backup_path=backup,
    )
