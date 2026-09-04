from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import copy
import re
import xml.etree.ElementTree as ET


@dataclass
class ImportPreview:
    comments: list[ET.Element]
    users: list[str]
    assigned_users: list[str]
    verse_refs: list[str]
    thread_ids: list[str]

    @property
    def count(self) -> int:
        return len(self.comments)


@dataclass
class ImportResult:
    imported: int
    skipped_duplicates: int
    imported_threads: list[str]
    imported_refs: list[str]


def clean_clipboard_xml(text: str) -> str:
    """
    Acepta XML puro copiado con el botón de un bloque de código de ChatGPT
    y también texto que aún tenga ```xml ... ```.
    """
    value = (text or "").strip()
    if not value:
        raise ValueError("El portapapeles está vacío.")

    # Quitar cercas Markdown.
    value = re.sub(r"^\s*```(?:xml)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```\s*$", "", value)

    # Si se copió texto alrededor del XML, conservar solo CommentList.
    start = value.find("<CommentList")
    end_tag = "</CommentList>"
    end = value.rfind(end_tag)

    if start >= 0 and end >= 0:
        value = value[start:end + len(end_tag)]
        return value.strip()

    # También admitimos un único <Comment>.
    cstart = value.find("<Comment ")
    cend_tag = "</Comment>"
    cend = value.rfind(cend_tag)
    if cstart >= 0 and cend >= 0:
        comment = value[cstart:cend + len(cend_tag)]
        return f"<CommentList>{comment}</CommentList>"

    return value


def parse_comment_xml(xml_text: str) -> ImportPreview:
    xml_text = clean_clipboard_xml(xml_text)

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(
            f"El contenido no es un XML de notas válido: {exc}"
        ) from exc

    if root.tag == "Comment":
        comments = [root]
    elif root.tag == "CommentList":
        comments = list(root.findall("Comment"))
    else:
        raise ValueError(
            "El elemento raíz debe ser <CommentList> o <Comment>."
        )

    if not comments:
        raise ValueError("El XML no contiene elementos <Comment>.")

    users = []
    assigned = []
    refs = []
    threads = []

    for index, comment in enumerate(comments, start=1):
        if comment.tag != "Comment":
            continue

        thread = (comment.attrib.get("Thread") or "").strip()
        verse_ref = (comment.attrib.get("VerseRef") or "").strip()
        user = (comment.attrib.get("User") or "").strip()

        if not thread:
            raise ValueError(
                f"El Comment #{index} no tiene atributo Thread."
            )
        if not verse_ref:
            raise ValueError(
                f"El Comment #{index} no tiene atributo VerseRef."
            )

        contents = comment.find("Contents")
        if contents is None:
            # Se admite, pero se crea un Contents vacío para mantener la
            # estructura esperada.
            ET.SubElement(comment, "Contents")

        users.append(user)
        refs.append(verse_ref)
        threads.append(thread)

        target = (comment.findtext("AssignedUser") or "").strip()
        if target:
            assigned.append(target)

    return ImportPreview(
        comments=comments,
        users=sorted(set(users), key=str.casefold),
        assigned_users=sorted(set(assigned), key=str.casefold),
        verse_refs=refs,
        thread_ids=threads,
    )


def parse_comment_file(path: str | Path) -> ImportPreview:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    return parse_comment_xml(text)


def import_comments(
    destination_document,
    preview: ImportPreview,
    existing_thread_ids: set[str],
    override_target: str | None = None,
    force_user: str | None = None,
    skip_duplicates: bool = True,
) -> ImportResult:
    """
    Inserta Comments completos en el Notes_*.xml del consultor.

    Se conserva el árbol de cada Comment, incluidos:
      SelectedText / StartPosition / ContextBefore / ContextAfter
      Status / Type / ConflictType / Verse
      Contents con sus <p> y <p />
      Date / Thread / VerseRef / Language

    Si override_target se indica, se actualizan AssignedUser y ReplyToUser
    para mantener la lógica de conversación del proyecto.
    """
    imported = 0
    skipped = 0
    imported_threads = []
    imported_refs = []

    pending = []

    for source in preview.comments:
        thread = (source.attrib.get("Thread") or "").strip()

        if (
            skip_duplicates
            and thread
            and thread in existing_thread_ids
        ):
            skipped += 1
            continue

        comment = copy.deepcopy(source)

        if force_user:
            comment.set("User", force_user)

        if override_target is not None:
            target = override_target.strip() or "Team"

            assigned_el = comment.find("AssignedUser")
            if assigned_el is None:
                assigned_el = ET.SubElement(
                    comment,
                    "AssignedUser",
                )
            assigned_el.text = target

            reply_el = comment.find("ReplyToUser")
            if reply_el is None:
                reply_el = ET.SubElement(
                    comment,
                    "ReplyToUser",
                )
            reply_el.text = target

        pending.append(comment)
        imported += 1
        imported_threads.append(thread)
        imported_refs.append(
            (comment.attrib.get("VerseRef") or "").strip()
        )

        if thread:
            existing_thread_ids.add(thread)

    if pending:
        destination_document.append_imported_comments(
            pending
        )

    return ImportResult(
        imported=imported,
        skipped_duplicates=skipped,
        imported_threads=imported_threads,
        imported_refs=imported_refs,
    )
