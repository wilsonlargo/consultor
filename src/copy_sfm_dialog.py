from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)


class CopySfmRangeDialog(QDialog):
    def __init__(
        self,
        verses,
        current_position: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Copiar rango SFM")
        self.resize(420, 220)

        self.verses = list(verses)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Seleccione el rango del capítulo activo. "
            "Se copiarán únicamente los marcadores \\s / \\s1 / \\s2… "
            "y \\v."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()

        self.start_combo = QComboBox()
        self.end_combo = QComboBox()

        for index, verse in enumerate(self.verses):
            label = f"v. {verse.verse}"
            self.start_combo.addItem(label, index)
            self.end_combo.addItem(label, index)

        if self.verses:
            current_position = max(
                0,
                min(current_position, len(self.verses) - 1),
            )
            self.start_combo.setCurrentIndex(current_position)
            self.end_combo.setCurrentIndex(
                len(self.verses) - 1
            )

        form.addRow("Desde:", self.start_combo)
        form.addRow("Hasta:", self.end_combo)
        layout.addLayout(form)

        note = QLabel(
            "No se copiarán \\p, \\f, \\ft ni otros marcadores. "
            "Las notas al pie tampoco se incluyen."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "font-size: 11px; color: palette(mid);"
        )
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Copiar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

    @property
    def start_index(self) -> int:
        return int(
            self.start_combo.currentData() or 0
        )

    @property
    def end_index(self) -> int:
        return int(
            self.end_combo.currentData() or 0
        )
