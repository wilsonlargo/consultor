from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from .sfm_parser import parse_sfm, SfmDocument


@dataclass
class ProjectText:
    path: Path
    document: SfmDocument

    @property
    def label(self) -> str:
        return self.document.title or f"{self.path.name} — {self.document.book}"


@dataclass
class NotesFile:
    path: Path
    owner: str

    @property
    def label(self) -> str:
        return self.owner


@dataclass
class TranslationProject:
    folder: Path
    texts: list[ProjectText]
    notes_files: list[NotesFile]


def notes_owner_from_filename(path: Path) -> str:
    name = path.stem
    if name.lower().startswith("notes_"):
        return name[6:].strip()
    return name


def detect_notes_owner(path: Path) -> str:
    """
    En los Notes_ observados, User identifica al propietario del archivo/hilo.
    Lo preferimos sobre el nombre del archivo para tolerar copias como '(1)'.
    """
    try:
        for _event, element in ET.iterparse(path, events=("start",)):
            if element.tag == "Comment":
                user = element.attrib.get("User", "").strip()
                if user:
                    return user
                break
    except Exception:
        pass
    return notes_owner_from_filename(path)


def load_project(folder: str | Path) -> TranslationProject:
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        raise ValueError("La carpeta del proyecto no existe.")

    text_paths = []
    for pattern in ("*.sfm", "*.usfm", "*.SFM", "*.USFM"):
        text_paths.extend(folder.rglob(pattern))

    unique_text_paths = sorted(set(text_paths), key=lambda p: str(p).lower())

    texts: list[ProjectText] = []
    for path in unique_text_paths:
        if ".consultor_backups" in path.parts:
            continue
        try:
            texts.append(ProjectText(path=path, document=parse_sfm(path)))
        except Exception:
            # Un proyecto puede contener SFM auxiliares que no sean un libro.
            # No bloqueamos todo el proyecto por uno de ellos.
            continue

    note_paths = sorted(
        [
            p for p in folder.rglob("*.xml")
            if p.name.lower().startswith("notes_")
            and ".consultor_backups" not in p.parts
        ],
        key=lambda p: p.name.lower(),
    )

    notes_files = [
        NotesFile(path=p, owner=detect_notes_owner(p))
        for p in note_paths
    ]

    if not texts and not notes_files:
        raise ValueError(
            "No encontré archivos .sfm/.usfm ni archivos Notes_*.xml "
            "dentro de la carpeta seleccionada."
        )

    return TranslationProject(
        folder=folder,
        texts=texts,
        notes_files=notes_files,
    )
