from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QMenu, QTextEdit

from .sfm_parser import AnchorTarget


class AnchorTextEdit(QTextEdit):
    """
    Texto SFM legible pero seleccionable.

    Aunque es de solo lectura, permite:
    - seleccionar una palabra/frase;
    - dejar el cursor en un punto;
    - crear una nota desde el menú contextual.
    """

    activated = Signal(object)
    note_requested = Signal(object)

    def __init__(
        self,
        target: AnchorTarget,
        heading: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.anchor_target = target
        self.heading = heading

        self.setReadOnly(True)
        self.setPlainText(target.visible_text)
        self.setAcceptRichText(False)
        self.setTextInteractionFlags(
            Qt.TextSelectableByMouse
            | Qt.TextSelectableByKeyboard
        )

        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.setFrameShape(QTextEdit.NoFrame)
        self.setContentsMargins(0, 0, 0, 0)
        self.document().setDocumentMargin(3)

        if heading:
            font = QFont(self.font())
            font.setBold(True)
            font.setPointSize(
                max(font.pointSize(), 11)
            )
            self.setFont(font)
            self.setStyleSheet(
                "QTextEdit { background: transparent; "
                "font-weight: 700; padding: 2px 4px; }"
            )
        else:
            self.setStyleSheet(
                "QTextEdit { background: transparent; "
                "padding: 1px 3px; }"
            )

        self.cursorPositionChanged.connect(
            lambda: self.activated.emit(self)
        )
        self.selectionChanged.connect(
            lambda: self.activated.emit(self)
        )

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.activated.emit(self)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.activated.emit(self)

    def contextMenuEvent(self, event):
        # Si no existe selección, el clic derecho define exactamente el punto
        # donde se anclará la nota.
        cursor = self.textCursor()
        if not cursor.hasSelection():
            self.setTextCursor(
                self.cursorForPosition(event.pos())
            )

        self.activated.emit(self)

        menu = self.createStandardContextMenu()
        menu.addSeparator()

        action = QAction(
            "Nueva nota sobre la selección / punto",
            self,
        )
        action.triggered.connect(
            lambda: self.note_requested.emit(self)
        )
        menu.addAction(action)
        menu.exec(event.globalPos())


    def clear_note_highlight(self):
        self.setExtraSelections([])

    def _visible_index_for_raw(
        self,
        raw_position: int,
    ) -> int:
        mapping = self.anchor_target.char_map
        if not mapping:
            return 0

        raw_position = max(
            0,
            int(raw_position or 0),
        )

        for index, raw_index in enumerate(
            mapping
        ):
            if raw_index >= raw_position:
                return index

        return max(
            0,
            len(mapping) - 1,
        )

    def highlight_note(
        self,
        selected_text: str,
        raw_position: int,
    ) -> tuple[int, int, str]:
        """
        Resalta el anclaje histórico de una nota sobre el texto visible actual.

        Prioridad:
        1. buscar SelectedText cerca de StartPosition;
        2. buscar SelectedText en todo el texto visible;
        3. usar el mapeo raw SFM → texto visible;
        4. si es una nota de punto, resaltar un carácter cercano.
        """
        self.clear_note_highlight()

        visible = self.anchor_target.visible_text or ""
        if not visible:
            return (0, 0, "none")

        raw_position = max(
            0,
            int(raw_position or 0),
        )
        guess = self._visible_index_for_raw(
            raw_position
        )

        start = guess
        end = min(
            len(visible),
            guess + 1,
        )

        selected = (
            selected_text
            or ""
        ).strip()
        match_mode = (
            "point"
            if not selected
            else "approximate"
        )

        if selected:
            # Buscar primero alrededor de la posición histórica.
            window_start = max(
                0,
                guess - 80,
            )
            window_end = min(
                len(visible),
                guess + len(selected) + 80,
            )
            local = visible[
                window_start:window_end
            ]
            local_index = local.find(
                selected
            )

            if local_index >= 0:
                start = (
                    window_start
                    + local_index
                )
                end = (
                    start
                    + len(selected)
                )
                match_mode = "exact"
            else:
                global_index = visible.find(
                    selected
                )
                if global_index < 0:
                    global_index = (
                        visible.casefold().find(
                            selected.casefold()
                        )
                    )

                if global_index >= 0:
                    start = global_index
                    end = (
                        start
                        + len(selected)
                    )
                    match_mode = "exact"
                else:
                    # El texto pudo haber cambiado. Intentar reconstruir el
                    # rango desde StartPosition usando char_map.
                    raw_end = (
                        raw_position
                        + len(selected)
                    )
                    indices = [
                        index
                        for index, raw_index
                        in enumerate(
                            self.anchor_target.char_map
                        )
                        if (
                            raw_position
                            <= raw_index
                            < raw_end
                        )
                    ]
                    if indices:
                        start = min(indices)
                        end = max(indices) + 1

        cursor = QTextCursor(
            self.document()
        )
        cursor.setPosition(
            max(0, start)
        )
        cursor.setPosition(
            max(
                start + 1,
                end,
            ),
            QTextCursor.KeepAnchor,
        )

        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor

        fmt = QTextCharFormat()
        if selected:
            fmt.setBackground(
                Qt.GlobalColor.yellow
            )
        else:
            fmt.setBackground(
                Qt.GlobalColor.darkYellow
            )
            fmt.setFontUnderline(
                True
            )

        selection.format = fmt
        self.setExtraSelections(
            [selection]
        )

        self.ensureCursorVisible()
        return (
            start,
            end,
            match_mode,
        )

    def selection_metadata(self) -> dict:
        cursor = self.textCursor()
        return self.anchor_target.selection_metadata(
            cursor.selectionStart(),
            cursor.selectionEnd(),
        )

    def ideal_height(self, width: int) -> int:
        width = max(120, width)
        self.document().setTextWidth(
            max(80, width - 10)
        )
        h = int(
            self.document().documentLayout().documentSize().height()
        )
        return max(30, h + 8)
