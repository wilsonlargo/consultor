from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from .note_importer import ImportPreview


class ImportNotesDialog(QDialog):
    def __init__(
        self,
        preview: ImportPreview,
        consultant_name: str,
        people: list[str],
        project_refs: set[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Importar notas XML")
        self.resize(560, 330)

        layout = QVBoxLayout(self)

        unique_refs = list(dict.fromkeys(preview.verse_refs))
        ref_preview = ", ".join(unique_refs[:6])
        if len(unique_refs) > 6:
            ref_preview += ", …"

        matches = None
        if project_refs is not None:
            normalized = {
                ref.replace(" ", ".").replace(":", ".").upper()
                for ref in preview.verse_refs
            }
            matches = len(normalized & project_refs)

        summary = (
            f"<b>{preview.count} Comment(s)</b><br>"
            f"User: {', '.join(preview.users) or '—'}<br>"
            f"AssignedUser: {', '.join(preview.assigned_users) or '—'}<br>"
            f"Referencias: {ref_preview or '—'}"
        )
        if matches is not None:
            summary += (
                f"<br>Referencias encontradas en los SFM del proyecto: "
                f"<b>{matches}/{len(set(preview.verse_refs))}</b>"
            )

        label = QLabel(summary)
        label.setWordWrap(True)
        layout.addWidget(label)

        form = QFormLayout()

        self.target_combo = QComboBox()
        self.target_combo.addItem(
            "Conservar AssignedUser / ReplyToUser del XML",
            None,
        )

        unique_people = []
        seen = set()
        for person in ["Team"] + list(people):
            key = person.strip().casefold()
            if not key or key in seen:
                continue
            if consultant_name and key == consultant_name.casefold():
                continue
            seen.add(key)
            unique_people.append(person.strip())

        for person in unique_people:
            self.target_combo.addItem(
                f"Dirigir todas a: {person}",
                person,
            )

        form.addRow(
            "Destinatario:",
            self.target_combo,
        )

        self.force_user_checkbox = QCheckBox(
            f"Usar «{consultant_name}» como User en las notas importadas"
        )
        self.force_user_checkbox.setChecked(True)
        self.force_user_checkbox.setToolTip(
            "Recomendado al importar notas generadas por ChatGPT dentro "
            "del archivo Notes_*.xml del consultor."
        )
        form.addRow(
            "Autor:",
            self.force_user_checkbox,
        )

        self.skip_duplicates_checkbox = QCheckBox(
            "Saltar notas cuyo Thread ya exista en el proyecto"
        )
        self.skip_duplicates_checkbox.setChecked(True)
        form.addRow(
            "Duplicados:",
            self.skip_duplicates_checkbox,
        )

        layout.addLayout(form)

        info = QLabel(
            "La importación conserva Thread, VerseRef, Date, SelectedText, "
            "StartPosition, ContextBefore/After, Verse, Status y la estructura "
            "de Contents. Antes de modificar el XML del consultor se crea "
            "una copia de seguridad."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "font-size: 11px; color: palette(mid);"
        )
        layout.addWidget(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Importar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def override_target(self):
        return self.target_combo.currentData()

    @property
    def force_user(self) -> bool:
        return self.force_user_checkbox.isChecked()

    @property
    def skip_duplicates(self) -> bool:
        return self.skip_duplicates_checkbox.isChecked()
