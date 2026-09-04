from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .notes_parser import NotesDocument, NoteMessage, normalize_verse_ref
from .project_loader import NotesFile


def _norm_name(value: str) -> str:
    return (value or "").strip().casefold()


def _is_generic_target(value: str) -> bool:
    return _norm_name(value) in {"", "team", "equipo"}


@dataclass
class InteractionMessage:
    owner: str
    document: NotesDocument
    message: NoteMessage

    @property
    def date(self) -> str:
        return self.message.date

    @property
    def deleted(self) -> bool:
        return self.message.deleted


@dataclass
class InteractionThread:
    thread: str
    verse_ref: str
    messages: list[InteractionMessage] = field(default_factory=list)
    consultant: str = ""

    @property
    def visible_messages(self) -> list[InteractionMessage]:
        return [m for m in self.messages if not m.deleted]

    def messages_by_owner(self, owner: str) -> list[InteractionMessage]:
        key = _norm_name(owner)
        return [m for m in self.messages if _norm_name(m.owner) == key]

    def consultant_messages(self) -> list[InteractionMessage]:
        return self.messages_by_owner(self.consultant)

    def other_messages(self) -> list[InteractionMessage]:
        c = _norm_name(self.consultant)
        return [m for m in self.messages if _norm_name(m.owner) != c]

    def resolved_for_consultant(self) -> bool:
        mine = self.consultant_messages()
        if not mine:
            return False
        mine = sorted(mine, key=lambda m: (m.message.date, m.message.source_index))
        return mine[-1].deleted

    def counterpart(self) -> str:
        """
        Determina con quién está interactuando el consultor en este hilo.

        Prioridad:
        1. ReplyToUser de las intervenciones del consultor.
        2. AssignedUser de las intervenciones del consultor.
        3. Autor de una respuesta externa dirigida al consultor.
        4. Único autor externo presente en el Thread.
        5. Team.
        """
        consultant_key = _norm_name(self.consultant)
        mine = sorted(
            self.consultant_messages(),
            key=lambda m: (m.message.date, m.message.source_index),
            reverse=True,
        )

        for field_name in ("reply_to_user", "assigned_user"):
            for wrapped in mine:
                value = getattr(wrapped.message, field_name, "")
                if (
                    value
                    and not _is_generic_target(value)
                    and _norm_name(value) != consultant_key
                ):
                    return value.strip()

        # Buscar quién escribió en otro archivo y dirigió su intervención
        # al consultor.
        externals = sorted(
            self.other_messages(),
            key=lambda m: (m.message.date, m.message.source_index),
            reverse=True,
        )
        for wrapped in externals:
            msg = wrapped.message
            if (
                _norm_name(msg.assigned_user) == consultant_key
                or _norm_name(msg.reply_to_user) == consultant_key
            ):
                return wrapped.owner

        owners = []
        seen = set()
        for wrapped in externals:
            key = _norm_name(wrapped.owner)
            if key and key not in seen:
                owners.append(wrapped.owner)
                seen.add(key)

        if len(owners) == 1:
            return owners[0]
        return "Team"

    def has_reply_from_counterpart(self) -> bool:
        counterpart = self.counterpart()
        if _is_generic_target(counterpart):
            # Si fue dirigido al Team, cualquier mensaje externo cuenta
            # como respuesta.
            return any(not m.deleted for m in self.other_messages())

        key = _norm_name(counterpart)
        return any(
            _norm_name(m.owner) == key and not m.deleted
            for m in self.other_messages()
        )

    def latest_visible(self) -> InteractionMessage | None:
        visible = self.visible_messages
        return visible[-1] if visible else None

    def original_consultant_message(self) -> InteractionMessage | None:
        mine = [m for m in self.consultant_messages() if not m.deleted]
        return mine[0] if mine else None


class NotesWorkspace:
    """
    Carga TODOS los Notes_*.xml del proyecto y fusiona conversaciones por Thread.

    Un mismo Thread puede estar repartido entre:
      Notes_wilson.xml
      Notes_Nicolas.xml
      Notes_Carmen.xml
    """

    def __init__(self, notes_files: Iterable[NotesFile], consultant: str):
        self.consultant = consultant.strip()
        self.documents: list[NotesDocument] = []
        self.documents_by_owner: dict[str, list[NotesDocument]] = {}
        self.thread_index: dict[str, list[InteractionMessage]] = {}

        for info in notes_files:
            doc = NotesDocument(info.path, info.owner)
            self.documents.append(doc)
            self.documents_by_owner.setdefault(
                _norm_name(info.owner), []
            ).append(doc)

        self._rebuild_index()

    def _rebuild_index(self):
        index: dict[str, list[InteractionMessage]] = {}

        for doc in self.documents:
            for thread in doc.threads:
                for msg in thread.messages:
                    index.setdefault(thread.thread, []).append(
                        InteractionMessage(
                            owner=doc.owner,
                            document=doc,
                            message=msg,
                        )
                    )

        for messages in index.values():
            messages.sort(
                key=lambda m: (
                    m.message.date,
                    _norm_name(m.owner),
                    m.message.source_index,
                )
            )

        self.thread_index = index

    def reload(self):
        refreshed: list[NotesDocument] = []
        by_owner: dict[str, list[NotesDocument]] = {}

        for doc in self.documents:
            new_doc = NotesDocument(doc.path, doc.owner)
            refreshed.append(new_doc)
            by_owner.setdefault(_norm_name(doc.owner), []).append(new_doc)

        self.documents = refreshed
        self.documents_by_owner = by_owner
        self._rebuild_index()

    def consultant_document(self) -> NotesDocument | None:
        docs = self.documents_by_owner.get(_norm_name(self.consultant), [])
        if not docs:
            return None
        # En un proyecto normal hay uno. Si hubiera copias, elegimos el
        # primero; el selector de proyecto evita backups.
        return docs[0]

    def all_people(self) -> list[str]:
        people = [doc.owner for doc in self.documents]
        unique = {}
        for person in people:
            unique.setdefault(_norm_name(person), person)
        return sorted(unique.values(), key=str.casefold)

    def thread(self, thread_id: str) -> InteractionThread | None:
        messages = self.thread_index.get(thread_id)
        if not messages:
            return None

        verse_ref = next(
            (
                m.message.verse_ref
                for m in messages
                if m.message.verse_ref
            ),
            "",
        )
        return InteractionThread(
            thread=thread_id,
            verse_ref=verse_ref,
            messages=list(messages),
            consultant=self.consultant,
        )

    def threads_for_reference(
        self,
        reference: str,
        include_resolved: bool = False,
    ) -> list[InteractionThread]:
        ref = normalize_verse_ref(reference)
        consultant_key = _norm_name(self.consultant)
        result: list[InteractionThread] = []

        for thread_id, messages in self.thread_index.items():
            # "Mis notas": solo hilos donde existe una intervención guardada
            # en el archivo del consultor.
            if not any(
                _norm_name(m.owner) == consultant_key
                for m in messages
            ):
                continue

            verse_ref = next(
                (
                    m.message.verse_ref
                    for m in messages
                    if m.message.verse_ref
                ),
                "",
            )
            if normalize_verse_ref(verse_ref) != ref:
                continue

            thread = InteractionThread(
                thread=thread_id,
                verse_ref=verse_ref,
                messages=list(messages),
                consultant=self.consultant,
            )
            if not include_resolved and thread.resolved_for_consultant():
                continue
            result.append(thread)

        result.sort(
            key=lambda t: (
                t.messages[0].message.date if t.messages else "",
                t.thread,
            )
        )
        return result

    def update_consultant_message(
        self,
        wrapped: InteractionMessage,
        text: str,
    ):
        if _norm_name(wrapped.owner) != _norm_name(self.consultant):
            raise ValueError(
                "Solo puede modificar intervenciones guardadas en su propio archivo de notas."
            )
        wrapped.document.update_message_contents(
            wrapped.message,
            text,
        )
        self.reload()

    def append_consultant_reply(
        self,
        thread: InteractionThread,
        text: str,
        target: str | None = None,
    ):
        doc = self.consultant_document()
        if doc is None:
            raise ValueError(
                f"No existe un archivo Notes_*.xml para el consultor '{self.consultant}'."
            )

        target = (target or thread.counterpart() or "Team").strip()
        template_wrapped = thread.latest_visible()
        template = template_wrapped.message if template_wrapped else None

        doc.append_message(
            thread_id=thread.thread,
            verse_ref=thread.verse_ref,
            text=text,
            assigned_user=target,
            reply_to_user=target,
            template=template,
        )
        self.reload()



    def create_consultant_note(
        self,
        anchor: dict,
        text: str,
        target: str = "Team",
    ) -> str:
        doc = self.consultant_document()
        if doc is None:
            raise ValueError(
                f"No existe un archivo Notes_*.xml para el consultor '{self.consultant}'."
            )

        thread_id = doc.create_note(
            anchor=anchor,
            text=text,
            assigned_user=target,
        )
        self.reload()
        return thread_id

    def resolve_thread(self, thread: InteractionThread):
        """
        Resolver/cerrar la nota sin perder el historial.

        Añade en el archivo del consultor un Comment del mismo Thread con
        Status=deleted, siguiendo el patrón observado en los XML reales.
        """
        if thread.resolved_for_consultant():
            raise ValueError("Este hilo ya está resuelto.")

        doc = self.consultant_document()
        if doc is None:
            raise ValueError(
                f"No existe un archivo Notes_*.xml para el consultor '{self.consultant}'."
            )

        target = thread.counterpart()
        if _is_generic_target(target):
            target = ""

        latest = thread.latest_visible()
        template = latest.message if latest else None

        doc.append_resolution_marker(
            thread_id=thread.thread,
            verse_ref=thread.verse_ref,
            assigned_user=target,
            template=template,
        )
        self.reload()

    def delete_consultant_message(
        self,
        wrapped: InteractionMessage,
    ):
        """
        Elimina físicamente solo una intervención perteneciente al consultor.
        """
        if _norm_name(wrapped.owner) != _norm_name(self.consultant):
            raise ValueError(
                "Solo puede borrar intervenciones guardadas en su propio archivo de notas."
            )

        if wrapped.deleted:
            raise ValueError(
                "No se borra directamente un marcador de resolución."
            )

        wrapped.document.delete_message(
            wrapped.message
        )
        self.reload()

    def is_original_consultant_message(
        self,
        thread: InteractionThread,
        wrapped: InteractionMessage,
    ) -> bool:
        original = thread.original_consultant_message()
        return bool(
            original
            and original.message.element is wrapped.message.element
        )

    def has_external_replies(
        self,
        thread: InteractionThread,
    ) -> bool:
        return any(
            not message.deleted
            for message in thread.other_messages()
        )

