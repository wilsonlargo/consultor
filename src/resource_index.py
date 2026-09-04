from __future__ import annotations

from pathlib import Path
import csv
import json
import re

from .notes_parser import normalize_verse_ref


class LocalResourceIndex:
    """
    Índice sencillo para recursos propios.

    Admite dos modelos:
    1. un archivo por referencia:
       MRK.1.1.md
       MRK_1_1.txt
       MRK-1-1.html

    2. archivos TSV/JSON con una columna/campo de referencia y contenido.
    """

    TEXT_EXTENSIONS = {
        ".md",
        ".markdown",
        ".txt",
        ".html",
        ".htm",
    }

    def __init__(self):
        self.folder: Path | None = None
        self._records: dict[str, list[dict]] = {}
        self.files_indexed = 0
        self.records_indexed = 0

    def clear(self):
        self.folder = None
        self._records = {}
        self.files_indexed = 0
        self.records_indexed = 0

    def load_folder(
        self,
        folder: str | Path,
    ):
        folder = Path(folder).expanduser()
        if not folder.exists():
            raise FileNotFoundError(
                f"La carpeta no existe: {folder}"
            )

        self.folder = folder
        self._records = {}
        self.files_indexed = 0
        self.records_indexed = 0

        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue

            suffix = path.suffix.lower()

            try:
                if suffix in self.TEXT_EXTENSIONS:
                    self._index_text_file(path)
                elif suffix == ".tsv":
                    self._index_tsv(path)
                elif suffix == ".json":
                    self._index_json(path)
            except Exception:
                # Un archivo individual mal formado no debe impedir que el
                # resto del recurso local siga disponible.
                continue

        return (
            self.files_indexed,
            self.records_indexed,
        )

    def _add(
        self,
        reference: str,
        title: str,
        content: str,
        format_name: str = "text",
        source_path: str = "",
    ):
        ref = normalize_verse_ref(
            reference
        )
        if not ref:
            return

        self._records.setdefault(
            ref,
            [],
        ).append(
            {
                "title": title,
                "content": content,
                "format": format_name,
                "source_path": source_path,
            }
        )
        self.records_indexed += 1

    def _reference_from_filename(
        self,
        path: Path,
    ) -> str:
        stem = path.stem.upper()

        match = re.search(
            r"([1-3]?[A-Z]{2,3})[._\-\s]+(\d+)[._\-\s]+(\d+(?:-\d+)?[A-Z]?)",
            stem,
        )
        if not match:
            return ""

        return normalize_verse_ref(
            f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
        )

    def _index_text_file(
        self,
        path: Path,
    ):
        reference = (
            self._reference_from_filename(
                path
            )
        )
        if not reference:
            return

        content = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        format_name = (
            "html"
            if path.suffix.lower()
            in {".html", ".htm"}
            else "text"
        )

        self._add(
            reference,
            path.stem,
            content,
            format_name,
            str(path),
        )
        self.files_indexed += 1

    @staticmethod
    def _first_value(
        row: dict,
        names: tuple[str, ...],
    ) -> str:
        lowered = {
            str(key).strip().casefold():
            value
            for key, value in row.items()
        }

        for name in names:
            value = lowered.get(
                name.casefold()
            )
            if value not in (
                None,
                "",
            ):
                return str(value)

        return ""

    def _index_tsv(
        self,
        path: Path,
    ):
        with path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
            newline="",
        ) as handle:
            reader = csv.DictReader(
                handle,
                delimiter="\t",
            )
            if not reader.fieldnames:
                return

            indexed = 0

            for row in reader:
                reference = self._first_value(
                    row,
                    (
                        "VerseRef",
                        "Reference",
                        "Ref",
                        "Verse",
                    ),
                )
                if not reference:
                    continue

                content = self._first_value(
                    row,
                    (
                        "Note",
                        "Content",
                        "Text",
                        "Comment",
                        "Explanation",
                        "OccurrenceNote",
                    ),
                )
                if not content:
                    # Si no hay una columna estándar, conservar las columnas
                    # no vacías como una ficha legible.
                    chunks = [
                        f"{key}: {value}"
                        for key, value in row.items()
                        if value not in (
                            None,
                            "",
                        )
                    ]
                    content = "\n".join(
                        chunks
                    )

                title = self._first_value(
                    row,
                    (
                        "Title",
                        "Quote",
                        "GLQuote",
                        "ID",
                    ),
                ) or path.stem

                self._add(
                    reference,
                    title,
                    content,
                    "text",
                    str(path),
                )
                indexed += 1

            if indexed:
                self.files_indexed += 1

    def _index_json(
        self,
        path: Path,
    ):
        data = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

        items = (
            data
            if isinstance(data, list)
            else data.get(
                "items",
                data.get(
                    "notes",
                    [],
                ),
            )
            if isinstance(data, dict)
            else []
        )

        indexed = 0

        if isinstance(items, dict):
            # Forma {"MRK.1.1": "contenido"}
            for reference, content in items.items():
                if isinstance(
                    content,
                    (str, int, float),
                ):
                    self._add(
                        str(reference),
                        path.stem,
                        str(content),
                        "text",
                        str(path),
                    )
                    indexed += 1

        elif isinstance(items, list):
            for item in items:
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                reference = self._first_value(
                    item,
                    (
                        "VerseRef",
                        "Reference",
                        "Ref",
                        "Verse",
                    ),
                )
                content = self._first_value(
                    item,
                    (
                        "Note",
                        "Content",
                        "Text",
                        "Comment",
                        "Explanation",
                    ),
                )
                if not (
                    reference
                    and content
                ):
                    continue

                title = self._first_value(
                    item,
                    (
                        "Title",
                        "Quote",
                        "ID",
                    ),
                ) or path.stem

                self._add(
                    reference,
                    title,
                    content,
                    "text",
                    str(path),
                )
                indexed += 1

        if indexed:
            self.files_indexed += 1

    def records_for(
        self,
        reference: str,
    ) -> list[dict]:
        ref = normalize_verse_ref(
            reference
        )
        return list(
            self._records.get(
                ref,
                [],
            )
        )

