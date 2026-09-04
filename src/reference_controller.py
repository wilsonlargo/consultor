from PySide6.QtCore import QObject, Signal


class ReferenceController(QObject):
    reference_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reference = ""

    @property
    def reference(self):
        return self._reference

    def set_reference(self, reference: str, force: bool = False):
        reference = (reference or "").strip().upper()
        if not reference:
            return
        if reference == self._reference and not force:
            return
        self._reference = reference
        self.reference_changed.emit(reference)
