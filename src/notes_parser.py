from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import uuid
import shutil
import xml.etree.ElementTree as ET


def _safe_int(value, default=0):
    try:
        return int(str(value or "").strip())
    except (TypeError, ValueError):
        return default


@dataclass
class NoteMessage:
    element: ET.Element
    thread: str
    user: str
    verse_ref: str
    date: str
    assigned_user: str
    reply_to_user: str
    status: str
    selected_text: str
    start_position: int
    context_before: str
    context_after: str
    verse_text: str
    contents: str
    source_index: int

    @property
    def deleted(self) -> bool:
        return self.status.strip().lower() == "deleted"


@dataclass
class NoteThread:
    thread: str
    verse_ref: str
    messages: list[NoteMessage] = field(default_factory=list)

    @property
    def original(self) -> NoteMessage | None:
        return self.messages[0] if self.messages else None

    @property
    def latest(self) -> NoteMessage | None:
        return self.messages[-1] if self.messages else None

    @property
    def visible_messages(self) -> list[NoteMessage]:
        return [m for m in self.messages if not m.deleted]


class NotesDocument:
    """
    Representa un único Notes_<persona>.xml.

    En los archivos reales analizados, todos los <Comment> de un mismo archivo
    tienen el mismo User: el propietario/autor de ese archivo. Las respuestas
    de otra persona están en SU propio Notes_*.xml y se relacionan por Thread.
    """

    def __init__(self, path: str | Path, owner: str):
        self.path = Path(path)
        self.owner = owner
        self.tree = ET.parse(self.path)
        self.root = self.tree.getroot()
        self.threads: list[NoteThread] = []
        self._parse()

    def _parse(self):
        grouped: dict[str, list[NoteMessage]] = {}

        for index, element in enumerate(self.root.findall("Comment")):
            thread = element.attrib.get("Thread", "").strip()
            if not thread:
                thread = f"_sin_thread_{index}"

            msg = NoteMessage(
                element=element,
                thread=thread,
                user=element.attrib.get("User", "").strip(),
                verse_ref=normalize_verse_ref(
                    element.attrib.get("VerseRef", "").strip()
                ),
                date=element.attrib.get("Date", "").strip(),
                assigned_user=(element.findtext("AssignedUser") or "").strip(),
                reply_to_user=(element.findtext("ReplyToUser") or "").strip(),
                status=(element.findtext("Status") or "").strip(),
                selected_text=(element.findtext("SelectedText") or "").strip(),
                start_position=_safe_int(
                    element.findtext("StartPosition"),
                    0,
                ),
                context_before=(element.findtext("ContextBefore") or ""),
                context_after=(element.findtext("ContextAfter") or ""),
                verse_text=(element.findtext("Verse") or ""),
                contents=contents_to_text(element.find("Contents")),
                source_index=index,
            )
            grouped.setdefault(thread, []).append(msg)

        threads = []
        for thread_id, messages in grouped.items():
            messages.sort(key=lambda m: (date_sort_key(m.date), m.source_index))
            verse_ref = next((m.verse_ref for m in messages if m.verse_ref), "")
            threads.append(
                NoteThread(
                    thread=thread_id,
                    verse_ref=verse_ref,
                    messages=messages,
                )
            )

        threads.sort(
            key=lambda t: (
                verse_sort_key(t.verse_ref),
                date_sort_key(t.original.date if t.original else ""),
            )
        )
        self.threads = threads

    def thread_by_id(self, thread_id: str) -> NoteThread | None:
        for thread in self.threads:
            if thread.thread == thread_id:
                return thread
        return None

    def update_message_contents(self, message: NoteMessage, text: str):
        if message.deleted:
            raise ValueError("No se puede modificar una intervención eliminada/resuelta.")

        # Seguridad: solo se permite modificar un elemento que pertenezca a
        # este árbol XML.
        if message.element not in list(self.root):
            raise ValueError("La intervención no pertenece a este archivo de notas.")

        contents = message.element.find("Contents")
        if contents is None:
            contents = ET.SubElement(message.element, "Contents")

        set_contents_from_text(contents, text)
        message.contents = text
        self.save_with_backup()
        self._parse()

    def create_note(
        self,
        anchor: dict,
        text: str,
        assigned_user: str = "Team",
    ) -> str:
        """
        Crea una nota nueva con una estructura compatible con los Notes_*.xml
        observados.

        anchor contiene:
          SelectedText
          StartPosition
          ContextBefore
          ContextAfter
          VerseRef
          Verse
        """
        assigned_user = (assigned_user or "").strip() or "Team"
        thread_id = uuid.uuid4().hex[:8]

        attrs = {
            "Thread": thread_id,
            "User": self.owner,
            "VerseRef": denormalize_verse_ref(
                anchor.get("VerseRef", "")
            ),
            "Language": "es",
            "Date": now_paratext_iso(),
        }

        comment = ET.SubElement(
            self.root,
            "Comment",
            attrs,
        )

        ET.SubElement(comment, "SelectedText").text = (
            anchor.get("SelectedText", "") or ""
        )
        ET.SubElement(comment, "StartPosition").text = str(
            int(anchor.get("StartPosition", 0) or 0)
        )
        ET.SubElement(comment, "ContextBefore").text = (
            anchor.get("ContextBefore", "") or ""
        )
        ET.SubElement(comment, "ContextAfter").text = (
            anchor.get("ContextAfter", "") or ""
        )

        ET.SubElement(comment, "Status").text = ""
        ET.SubElement(comment, "Type").text = ""
        ET.SubElement(
            comment,
            "ConflictType",
        ).text = "unknownConflictType"

        ET.SubElement(comment, "Verse").text = (
            anchor.get("Verse", "") or ""
        )

        ET.SubElement(
            comment,
            "AssignedUser",
        ).text = assigned_user
        ET.SubElement(
            comment,
            "ReplyToUser",
        ).text = assigned_user
        ET.SubElement(
            comment,
            "HideInTextWindow",
        ).text = "false"

        contents = ET.SubElement(
            comment,
            "Contents",
        )
        set_contents_from_text(
            contents,
            text,
        )

        self.save_with_backup()
        self._parse()
        return thread_id


    def append_message(
        self,
        thread_id: str,
        verse_ref: str,
        text: str,
        assigned_user: str,
        reply_to_user: str | None = None,
        template: NoteMessage | None = None,
    ):
        """
        Añade una intervención del propietario de ESTE archivo.

        Si Wilson responde a Nicolas, el nuevo <Comment> se escribe en
        Notes_Wilson.xml con User="Wilson", manteniendo el mismo Thread.
        """
        assigned_user = (assigned_user or "").strip() or "Team"
        reply_to_user = (
            (reply_to_user or "").strip()
            or assigned_user
        )

        language = "es"
        if template is not None:
            language = template.element.attrib.get("Language", "es") or "es"

        attrs = {
            "Thread": thread_id,
            "User": self.owner,
            "VerseRef": denormalize_verse_ref(verse_ref),
            "Language": language,
            "Date": now_paratext_iso(),
        }
        comment = ET.SubElement(self.root, "Comment", attrs)

        # Conserva el anclaje/contexto de la conversación, aunque la plantilla
        # provenga del XML del interlocutor.
        for tag in (
            "SelectedText",
            "StartPosition",
            "ContextBefore",
            "ContextAfter",
        ):
            target = ET.SubElement(comment, tag)
            if template is not None:
                source = template.element.find(tag)
                if source is not None and source.text:
                    target.text = source.text

        ET.SubElement(comment, "Status").text = ""
        ET.SubElement(comment, "Type").text = ""
        conflict = "unknownConflictType"
        if template is not None:
            conflict = (
                template.element.findtext("ConflictType")
                or "unknownConflictType"
            )
        ET.SubElement(comment, "ConflictType").text = conflict
        ET.SubElement(comment, "Verse")
        ET.SubElement(comment, "AssignedUser").text = assigned_user
        ET.SubElement(comment, "ReplyToUser").text = reply_to_user
        ET.SubElement(comment, "HideInTextWindow").text = "false"

        contents = ET.SubElement(comment, "Contents")
        set_contents_from_text(contents, text)

        self.save_with_backup()
        self._parse()


    def append_resolution_marker(
        self,
        thread_id: str,
        verse_ref: str,
        assigned_user: str = "",
        template: NoteMessage | None = None,
    ):
        """
        Cierra/resuelve un hilo siguiendo el patrón observado en Notes_*.xml:
        crea un nuevo <Comment> del mismo Thread con <Status>deleted</Status>.

        No elimina las intervenciones anteriores.
        """
        language = "es"
        if template is not None:
            language = template.element.attrib.get("Language", "es") or "es"

        attrs = {
            "Thread": thread_id,
            "User": self.owner,
            "VerseRef": denormalize_verse_ref(verse_ref),
            "Language": language,
            "Date": now_paratext_iso(),
        }
        comment = ET.SubElement(self.root, "Comment", attrs)

        for tag in (
            "SelectedText",
            "StartPosition",
            "ContextBefore",
            "ContextAfter",
        ):
            target = ET.SubElement(comment, tag)
            if template is not None:
                source = template.element.find(tag)
                if source is not None and source.text:
                    target.text = source.text

        ET.SubElement(comment, "Status").text = "deleted"
        ET.SubElement(comment, "Type").text = ""

        conflict = "unknownConflictType"
        if template is not None:
            conflict = (
                template.element.findtext("ConflictType")
                or "unknownConflictType"
            )
        ET.SubElement(comment, "ConflictType").text = conflict
        ET.SubElement(comment, "Verse")

        assigned_user = (assigned_user or "").strip()
        if assigned_user:
            ET.SubElement(comment, "AssignedUser").text = assigned_user

        ET.SubElement(comment, "HideInTextWindow").text = "false"

        self.save_with_backup()
        self._parse()

    def delete_message(self, message: NoteMessage):
        """
        Borrado físico de una intervención de ESTE archivo.

        Es diferente de resolver: resolver conserva el historial y añade
        Status=deleted; borrar elimina el nodo <Comment> seleccionado.
        """
        if message.element not in list(self.root):
            raise ValueError(
                "La intervención no pertenece a este archivo de notas."
            )

        self.root.remove(message.element)
        self.save_with_backup()
        self._parse()

    def append_imported_comments(
        self,
        comments: list[ET.Element],
    ):
        """
        Importación por lote: añade Comments ya validados y guarda una sola vez.

        La estructura interna de cada Comment se conserva; únicamente puede
        normalizarse la sangría al serializar el XML completo.
        """
        if not comments:
            return

        for comment in comments:
            self.root.append(comment)

        self.save_with_backup()
        self._parse()

    def save_with_backup(self):
        backup_dir = self.path.parent / ".consultor_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup = backup_dir / f"{self.path.stem}_{stamp}.xml"
        shutil.copy2(self.path, backup)

        try:
            ET.indent(self.tree, space="  ")
        except AttributeError:
            pass

        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        self.tree.write(
            temp,
            encoding="utf-8",
            xml_declaration=True,
            short_empty_elements=True,
        )
        temp.replace(self.path)
        return backup


def contents_to_text(contents: ET.Element | None) -> str:
    if contents is None:
        return ""

    children = list(contents)
    if not children:
        return "".join(contents.itertext()).strip()

    lines: list[str] = []
    for child in children:
        if child.tag == "p":
            lines.append("".join(child.itertext()))
        else:
            text = "".join(child.itertext())
            if text:
                lines.append(text)

    return "\n".join(lines)


def set_contents_from_text(contents: ET.Element, text: str):
    contents.text = None
    for child in list(contents):
        contents.remove(child)

    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines:
        lines = [""]

    for line in lines:
        p = ET.SubElement(contents, "p")
        if line:
            p.text = line


def normalize_verse_ref(reference: str) -> str:
    ref = (reference or "").strip().upper()
    if not ref:
        return ""

    if " " in ref:
        book, rest = ref.split(None, 1)
        if ":" in rest:
            chapter, verse = rest.split(":", 1)
            return f"{book}.{chapter}.{verse}"
        return f"{book}.{rest}"

    return ref.replace(":", ".")


def denormalize_verse_ref(reference: str) -> str:
    ref = normalize_verse_ref(reference)
    parts = ref.split(".")
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1]}:{'.'.join(parts[2:])}"
    if len(parts) == 2:
        return f"{parts[0]} {parts[1]}"
    return ref


def date_sort_key(value: str):
    return (value or "").strip()


def verse_sort_key(reference: str):
    ref = normalize_verse_ref(reference)
    parts = ref.split(".")
    book = parts[0] if parts else ""
    try:
        chapter = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        chapter = 0

    verse_raw = parts[2] if len(parts) > 2 else "0"
    digits = ""
    for ch in verse_raw:
        if ch.isdigit():
            digits += ch
        else:
            break
    try:
        verse = int(digits or 0)
    except ValueError:
        verse = 0

    return (book, chapter, verse, verse_raw)


def now_paratext_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")
