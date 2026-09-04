from __future__ import annotations

import webbrowser
import difflib
import html
import re
from pathlib import Path
from datetime import datetime
import hashlib
import shutil

from PySide6.QtCore import (
    Qt,
    QFileSystemWatcher,
    QSettings,
    QSize,
    QStandardPaths,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QGroupBox,
    QInputDialog,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .anchor_text_edit import AnchorTextEdit
from .copy_sfm_dialog import CopySfmRangeDialog
from .import_notes_dialog import ImportNotesDialog
from .note_importer import (
    import_comments,
    parse_comment_file,
    parse_comment_xml,
)
from .note_tools import (
    apply_bulk_operation,
    search_documents,
)
from .browser_urls import SOURCES, build_url
from .notes_parser import normalize_verse_ref, verse_sort_key
from .notes_workspace import NotesWorkspace, InteractionMessage, InteractionThread
from .project_loader import TranslationProject, load_project
from .reference_controller import ReferenceController
from .reference_parser import parse_reference, to_spanish_reference
from .resource_panel import (
    ResourceFloatingWindow,
    ResourcePanelWidget,
)
from .spellcheck_qt import (
    SpellCheckerManager,
    SpellCheckPlainTextEdit,
    SpellReviewDialog,
    SpellDependencyInstaller,
)
from .sfm_clipboard import build_sfm_range
from .verse_diff import diff_html
from .web_cleaner import AdTrackerInterceptor, cleanup_javascript


GREEN_BUTTON_STYLE = """
QToolButton {
    background-color: #2e9d49;
    color: white;
    border: none;
    border-radius: 5px;
    min-width: 30px;
    min-height: 27px;
    font-weight: bold;
    font-size: 16px;
}
QToolButton:hover {
    background-color: #27863e;
}
QToolButton:disabled {
    background-color: #9abda1;
}
"""


def _same_name(a: str, b: str) -> bool:
    return (a or "").strip().casefold() == (b or "").strip().casefold()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Consultor App")
        self.resize(1450, 900)

        self.settings = QSettings()
        self.spell_manager = SpellCheckerManager(
            self.settings,
            self,
        )
        self.spell_manager.status_changed.connect(
            self._spell_status_changed
        )
        self.spell_dependency_installer = None

        self.reference_controller = ReferenceController(self)
        self.reference_controller.reference_changed.connect(
            self._reference_changed
        )

        self.project: TranslationProject | None = None
        self.current_text = None
        self.current_chapter = ""
        self.current_reference = ""

        # Historial de navegación bíblica del proyecto activo.
        self.reference_history: list[str] = []
        self.reference_history_index = -1
        self._reference_history_navigating = False

        self.verse_rows: list[int] = []
        self.current_verse_position = -1

        self.consultant_name = (
            self.settings.value("consultant_name", "", type=str) or ""
        ).strip()
        self.notes_workspace: NotesWorkspace | None = None
        self.current_interaction_thread: InteractionThread | None = None
        self.current_interaction_message: InteractionMessage | None = None
        self.reply_mode = False
        self.new_note_mode = False
        self.new_note_anchor = None
        self.current_anchor_widget = None
        self.anchor_widgets_by_row = {}
        self.note_reference_by_row = {}
        self.note_base_label_by_row = {}
        self._restoring_project_session = False
        self.recent_projects_menu = None
        self.bulk_search_hits = []

        # Recursos bíblicos.
        self.resource_windows = []
        self._resource_window_counter = 0
        self._closing_app = False

        # Modo Revisión.
        self.review_mode = False

        # Detección de cambios externos.
        self.file_watcher = QFileSystemWatcher(
            self
        )
        self.file_watcher.fileChanged.connect(
            self._project_file_changed
        )
        self._watched_file_stamps = {}
        self._pending_external_changes = set()

        self._build_central_editor()
        self._build_bible_dock()
        self._build_notes_dock()
        self._build_chatgpt_dock()
        self._build_note_tools_dock()
        self._build_resources_dock()
        self._build_toolbar()
        self._build_menu()
        self._restore_layout()

        for dock in (
            self.bible_dock,
            self.notes_dock,
            self.chatgpt_dock,
            self.note_tools_dock,
            self.resources_dock,
        ):
            dock.visibilityChanged.connect(
                lambda _visible:
                    self._save_project_session()
            )

        # Restaurar el último proyecto después de que la ventana ya tenga
        # todos sus paneles y menús construidos.
        QTimer.singleShot(
            0,
            self._restore_last_project,
        )
        QTimer.singleShot(
            120,
            self._restore_resource_windows,
        )

    # ------------------------------------------------------------------
    # Corrector ortográfico de notas
    # ------------------------------------------------------------------
    def _spell_status_changed(
        self,
        message: str,
    ):
        if hasattr(
            self,
            "spell_toggle_button",
        ):
            language = (
                str(
                    self.spell_manager.language
                    or ""
                ).upper()
            )
            if self.spell_manager.backend_ready():
                self.spell_toggle_button.setText(
                    f"{language} ✓"
                )
            else:
                self.spell_toggle_button.setText(
                    f"{language} !"
                )

            self.spell_toggle_button.setToolTip(
                message
                + "\n\n"
                + "Los marcadores COM:, PT:, SUG:, CONT:, IndS: y RES: "
                + "no se revisan."
            )

        if message:
            self.statusBar().showMessage(
                message,
                4500,
            )

    def _refresh_spellcheck_controls(
        self,
    ):
        if not hasattr(
            self,
            "spell_language_combo",
        ):
            return

        self.spell_toggle_button.blockSignals(
            True
        )
        self.spell_toggle_button.setChecked(
            self.spell_manager.enabled
        )
        self.spell_toggle_button.blockSignals(
            False
        )

        index = (
            self.spell_language_combo.findData(
                self.spell_manager.language
            )
        )

        self.spell_language_combo.blockSignals(
            True
        )
        if index >= 0:
            self.spell_language_combo.setCurrentIndex(
                index
            )
        self.spell_language_combo.blockSignals(
            False
        )

        self._spell_status_changed(
            self.spell_manager.status_text()
        )

    def _spellcheck_toggled(
        self,
        checked: bool,
    ):
        self.spell_manager.set_enabled(
            checked
        )

        self.statusBar().showMessage(
            (
                "Revisión ortográfica activada."
                if checked
                else "Revisión ortográfica desactivada."
            ),
            3000,
        )

    def _spell_language_changed(
        self,
        _index: int,
    ):
        language = (
            self.spell_language_combo.currentData()
        )
        if not language:
            return

        if language == "custom":
            if not self._choose_custom_spell_dictionary():
                self._refresh_spellcheck_controls()
            return

        self.spell_manager.set_language(
            str(language)
        )
        self._refresh_spellcheck_controls()

    def _show_spellcheck_menu(self):
        menu = QMenu(
            self
        )

        review_note = QAction(
            "Revisar mi nota completa…",
            menu,
        )
        review_note.triggered.connect(
            self._review_note_spelling
        )
        menu.addAction(
            review_note
        )

        review_reply = QAction(
            "Revisar respuesta/seguimiento…",
            menu,
        )
        review_reply.setEnabled(
            self.reply_editor.isVisible()
        )
        review_reply.triggered.connect(
            self._review_reply_spelling
        )
        menu.addAction(
            review_reply
        )

        if not self.spell_manager.backend_ready():
            install_dictionary = QAction(
                "Instalar diccionario integrado…",
                menu,
            )
            install_dictionary.triggered.connect(
                self._install_spell_dictionary
            )
            menu.addAction(
                install_dictionary
            )

        menu.addSeparator()

        import_words = QAction(
            "Importar vocabulario al diccionario del proyecto…",
            menu,
        )
        import_words.setToolTip(
            "Añade palabras a la lista aceptada sin reemplazar "
            "el idioma principal."
        )
        import_words.triggered.connect(
            self._import_spell_project_wordlist
        )
        menu.addAction(
            import_words
        )

        custom_dictionary = QAction(
            "Usar lista como diccionario principal…",
            menu,
        )
        custom_dictionary.setToolTip(
            "Útil para una lengua que no tiene diccionario integrado."
        )
        custom_dictionary.triggered.connect(
            self._choose_custom_spell_dictionary
        )
        menu.addAction(
            custom_dictionary
        )

        menu.addSeparator()

        clear_ignored = QAction(
            "Restablecer palabras ignoradas en esta sesión",
            menu,
        )
        clear_ignored.triggered.connect(
            self.spell_manager.clear_session_ignored
        )
        menu.addAction(
            clear_ignored
        )

        status_action = QAction(
            self.spell_manager.status_text(),
            menu,
        )
        status_action.setEnabled(
            False
        )
        menu.addAction(
            status_action
        )

        menu.exec(
            self.spell_options_button.mapToGlobal(
                self.spell_options_button.rect().bottomLeft()
            )
        )

    def _install_spell_dictionary(self):
        if (
            self.spell_dependency_installer is not None
            and self.spell_dependency_installer.isRunning()
        ):
            self.statusBar().showMessage(
                "La instalación del diccionario ya está en curso.",
                4000,
            )
            return

        answer = QMessageBox.question(
            self,
            "Instalar corrector ortográfico",
            "Consultor App instalará el paquete abierto pyspellchecker "
            "dentro del entorno virtual actual.\n\n"
            "Esto habilita los diccionarios integrados, incluido español.\n\n"
            "¿Continuar?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.statusBar().showMessage(
            "Instalando diccionarios ortográficos…",
            0,
        )

        self.spell_dependency_installer = (
            SpellDependencyInstaller(
                self
            )
        )
        self.spell_dependency_installer.finished_install.connect(
            self._spell_dictionary_install_finished
        )
        self.spell_dependency_installer.start()

    def _spell_dictionary_install_finished(
        self,
        ok: bool,
        message: str,
    ):
        if ok:
            self.spell_manager.reload_backend()
            self._refresh_spellcheck_controls()

            QMessageBox.information(
                self,
                "Corrector ortográfico",
                "El diccionario integrado se instaló correctamente.\n\n"
                "La revisión ortográfica ya está activa.",
            )

            self.statusBar().showMessage(
                self.spell_manager.status_text(),
                5000,
            )
        else:
            QMessageBox.warning(
                self,
                "Corrector ortográfico",
                "No fue posible instalar el diccionario automáticamente.\n\n"
                f"{message}\n\n"
                "Puede instalarlo manualmente con:\n"
                "pip install pyspellchecker",
            )

            self.statusBar().showMessage(
                "Corrector ortográfico sin diccionario.",
                5000,
            )

    def _review_note_spelling(self):
        dialog = SpellReviewDialog(
            self.spell_manager,
            self.note_editor.toPlainText(),
            self,
        )
        dialog.exec()

    def _review_reply_spelling(self):
        dialog = SpellReviewDialog(
            self.spell_manager,
            self.reply_editor.toPlainText(),
            self,
        )
        dialog.exec()

    def _import_spell_project_wordlist(self):
        path, _selected_filter = (
            QFileDialog.getOpenFileName(
                self,
                "Importar vocabulario del proyecto",
                str(Path.home()),
                (
                    "Listas de palabras (*.txt *.dic);;"
                    "Todos los archivos (*)"
                ),
            )
        )
        if not path:
            return

        try:
            count = (
                self.spell_manager.import_wordlist(
                    path
                )
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Corrector ortográfico",
                f"No se pudo importar el vocabulario.\n\n{exc}",
            )
            return

        if not count:
            QMessageBox.information(
                self,
                "Corrector ortográfico",
                "No se encontraron palabras utilizables en el archivo.",
            )
            return

        QMessageBox.information(
            self,
            "Corrector ortográfico",
            f"Se agregaron {count} palabra(s) al diccionario del proyecto.",
        )

    def _choose_custom_spell_dictionary(self):
        path, _selected_filter = (
            QFileDialog.getOpenFileName(
                self,
                "Elegir diccionario personalizado",
                str(Path.home()),
                (
                    "Diccionario / lista de palabras (*.txt *.dic);;"
                    "Todos los archivos (*)"
                ),
            )
        )
        if not path:
            return False

        try:
            count = (
                self.spell_manager.use_custom_dictionary(
                    path
                )
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Corrector ortográfico",
                f"No se pudo usar el diccionario.\n\n{exc}",
            )
            return False

        if not count:
            QMessageBox.information(
                self,
                "Corrector ortográfico",
                "El archivo no contiene palabras utilizables.",
            )
            return False

        self._refresh_spellcheck_controls()

        QMessageBox.information(
            self,
            "Corrector ortográfico",
            f"Diccionario personalizado activo: "
            f"{Path(path).name}\n\n"
            f"Palabras cargadas: {count}.",
        )
        return True


    def _configure_icon_button(
        self,
        button,
        size: int = 30,
    ):
        button.setFixedSize(
            QSize(size, size)
        )
        font = QFont(
            button.font()
        )
        font.setPointSize(
            12
        )
        button.setFont(
            font
        )
        button.setStyleSheet(
            button.styleSheet()
            + "QToolButton, QPushButton { padding: 0px; }"
        )
        return button

    def _configure_text_button(
        self,
        button,
        height: int = 30,
    ):
        button.setFixedHeight(
            height
        )
        return button

    # ------------------------------------------------------------------
    # Centro: capítulo activo con estructura SFM legible
    # ------------------------------------------------------------------
    def _build_central_editor(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)

        self.project_title = QLabel(
            "Abra una carpeta de proyecto para comenzar"
        )
        self.project_title.setStyleSheet(
            "font-size: 16px; font-weight: 600;"
        )

        self.verse_table = QTableWidget(0, 2)
        self.verse_table.setHorizontalHeaderLabels(
            ["Vers.", "Retrotraducción / texto"]
        )
        self.verse_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.verse_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.verse_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verse_table.setWordWrap(True)
        self.verse_table.setTextElideMode(Qt.ElideNone)
        self.verse_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.verse_table.verticalHeader().setVisible(False)
        self.verse_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.verse_table.setStyleSheet(
            "QTableWidget::item { padding: 5px; }"
        )

        self.verse_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.verse_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.verse_table.horizontalHeader().sectionResized.connect(
            lambda *_: QTimer.singleShot(
                0,
                self._resize_anchor_rows,
            )
        )
        self.verse_table.itemSelectionChanged.connect(
            self._verse_selection_changed
        )

        self.external_change_bar = QWidget()
        external_layout = QHBoxLayout(
            self.external_change_bar
        )
        external_layout.setContentsMargins(
            6, 3, 6, 3
        )
        external_layout.setSpacing(6)

        self.external_change_label = QLabel(
            ""
        )
        self.external_change_label.setWordWrap(
            True
        )
        self.external_change_label.setStyleSheet(
            "font-weight: 600;"
        )

        self.external_reload_button = QPushButton(
            "Recargar"
        )
        self._configure_text_button(
            self.external_reload_button
        )
        self.external_reload_button.clicked.connect(
            self._reload_external_changes
        )

        self.external_ignore_button = QToolButton()
        self.external_ignore_button.setText(
            "✕"
        )
        self.external_ignore_button.setToolTip(
            "Ignorar este aviso."
        )
        self._configure_icon_button(
            self.external_ignore_button
        )
        self.external_ignore_button.clicked.connect(
            self._dismiss_external_change_notice
        )

        external_layout.addWidget(
            self.external_change_label,
            1,
        )
        external_layout.addWidget(
            self.external_reload_button
        )
        external_layout.addWidget(
            self.external_ignore_button
        )

        self.external_change_bar.setStyleSheet(
            "QWidget { background: #fff0c9; "
            "border: 1px solid #e3c574; border-radius: 5px; }"
        )
        self.external_change_bar.hide()

        self.selection_status_label = QLabel(
            "Para crear una nota: seleccione texto o coloque el cursor en un punto."
        )
        self.selection_status_label.setWordWrap(True)
        self.selection_status_label.setStyleSheet(
            "font-size: 11px; color: palette(mid);"
        )

        layout.addWidget(self.project_title)
        layout.addWidget(self.external_change_bar)
        layout.addWidget(self.selection_status_label)
        layout.addWidget(self.verse_table, 1)
        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    # Panel derecho: navegador bíblico
    # ------------------------------------------------------------------
    def _build_bible_dock(self):
        self.bible_dock = QDockWidget("Consulta bíblica", self)
        self.bible_dock.setObjectName("BibleDock")
        self.bible_dock.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
        )

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Línea 1: fuente + sincronización.
        source_row = QHBoxLayout()
        source_row.setSpacing(4)

        self.source_combo = QComboBox()
        for label, _, _ in SOURCES:
            self.source_combo.addItem(label)
        self.source_combo.setCurrentIndex(3)
        self.source_combo.currentIndexChanged.connect(
            self._source_changed
        )

        self.sync_checkbox = QCheckBox("Sincronizar")
        self.sync_checkbox.setChecked(True)
        self.sync_checkbox.setToolTip(
            "Mantener la consulta bíblica sincronizada "
            "con el versículo seleccionado en el SFM."
        )

        source_row.addWidget(self.source_combo, 1)
        source_row.addWidget(self.sync_checkbox)

        # Línea 2: referencia y navegación compacta.
        ref_row = QHBoxLayout()
        ref_row.setSpacing(3)

        self.reference_edit = QComboBox()
        self.reference_edit.setEditable(True)
        self.reference_edit.lineEdit().setPlaceholderText("Marcos 8:31")
        self.reference_edit.lineEdit().returnPressed.connect(
            self.search_reference
        )

        go = QToolButton()
        go.setText("Ir")
        go.setToolTip("Ir a la referencia")
        go.clicked.connect(self.search_reference)

        back = QToolButton()
        back.setText("←")
        back.setToolTip("Atrás")
        back.clicked.connect(self.browser_back)

        forward = QToolButton()
        forward.setText("→")
        forward.setToolTip("Adelante")
        forward.clicked.connect(self.browser_forward)

        reload_button = QToolButton()
        reload_button.setText("↻")
        reload_button.setToolTip("Recargar")
        reload_button.clicked.connect(self.browser_reload)

        external = QToolButton()
        external.setText("↗")
        external.setToolTip("Abrir en navegador externo")
        external.clicked.connect(self.open_external)

        for button in (
            go,
            back,
            forward,
            reload_button,
            external,
        ):
            self._configure_icon_button(
                button
            )

        ref_row.addWidget(self.reference_edit, 1)
        ref_row.addWidget(go)
        ref_row.addWidget(back)
        ref_row.addWidget(forward)
        ref_row.addWidget(reload_button)
        ref_row.addWidget(external)

        self.browser = QWebEngineView()
        self.browser.settings().setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
            False,
        )

        # El modo limpio queda activo permanentemente.
        self.ad_interceptor = AdTrackerInterceptor(self)
        self.browser.page().profile().setUrlRequestInterceptor(
            self.ad_interceptor
        )
        self.browser.loadFinished.connect(
            self._browser_load_finished
        )

        layout.addLayout(source_row)
        layout.addLayout(ref_row)
        layout.addWidget(self.browser, 1)

        self.bible_dock.setWidget(panel)
        self.addDockWidget(
            Qt.RightDockWidgetArea,
            self.bible_dock,
        )

    # ------------------------------------------------------------------
    # Panel de notas: interacción real entre archivos Notes_*.xml
    # ------------------------------------------------------------------
    def _build_notes_dock(self):
        self.notes_dock = QDockWidget(
            "Panel de consultor",
            self,
        )
        self.notes_dock.setObjectName("NotesDock")
        self.notes_dock.setAllowedAreas(
            Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea
        )
    
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)
    
        # --------------------------------------------------------------
        # Encabezado compacto del hilo
        # --------------------------------------------------------------
        header_row = QHBoxLayout()
        header_row.setSpacing(6)
    
        self.consultant_label = QLabel("Consultor: —")
        self.consultant_label.setStyleSheet(
            "font-weight: 700;"
        )
        header_row.addWidget(self.consultant_label)
    
        self.note_verse_ref_label = QLabel(
            "VerseRef: —"
        )
        self.note_verse_ref_label.setStyleSheet(
            "font-weight: 700;"
        )
        header_row.addWidget(
            self.note_verse_ref_label
        )
    
        header_row.addWidget(QLabel("Nota:"))

        self.prev_note_button = QToolButton()
        self.prev_note_button.setText("◀")
        self.prev_note_button.setToolTip(
            "Nota anterior del consultor en todo el proyecto."
        )
        self._configure_icon_button(
            self.prev_note_button
        )
        self.prev_note_button.clicked.connect(
            lambda: self.move_consultant_note(-1)
        )
        self.prev_note_button.setEnabled(
            False
        )
        header_row.addWidget(
            self.prev_note_button
        )
    
        self.thread_combo = QComboBox()
        self.thread_combo.setMinimumWidth(300)
        self.thread_combo.currentIndexChanged.connect(
            self._thread_changed
        )
        header_row.addWidget(
            self.thread_combo,
            1,
        )

        self.next_note_button = QToolButton()
        self.next_note_button.setText("▶")
        self.next_note_button.setToolTip(
            "Nota siguiente del consultor en todo el proyecto."
        )
        self._configure_icon_button(
            self.next_note_button
        )
        self.next_note_button.clicked.connect(
            lambda: self.move_consultant_note(1)
        )
        self.next_note_button.setEnabled(
            False
        )
        header_row.addWidget(
            self.next_note_button
        )
    
        self.thread_status_label = QLabel("")
        self.thread_status_label.setStyleSheet(
            "font-weight: 700;"
        )
        header_row.addWidget(
            self.thread_status_label
        )
    
        self.show_resolved_checkbox = QCheckBox(
            "Resueltas"
        )
        self.show_resolved_checkbox.setToolTip(
            "Mostrar también notas resueltas."
        )
        self.show_resolved_checkbox.toggled.connect(
            lambda _: self._refresh_threads_for_reference()
        )
        header_row.addWidget(
            self.show_resolved_checkbox
        )

        self.review_mode_button = QPushButton(
            "▶ Revisión"
        )
        self.review_mode_button.setCheckable(
            True
        )
        self.review_mode_button.setToolTip(
            "Recorrer notas como una cola de revisión continua."
        )
        self._configure_text_button(
            self.review_mode_button
        )
        self.review_mode_button.toggled.connect(
            self._review_mode_toggled
        )
        header_row.addWidget(
            self.review_mode_button
        )

        self.review_filter_combo = QComboBox()
        self.review_filter_combo.addItem(
            "Pendientes",
            "pending",
        )
        self.review_filter_combo.addItem(
            "Respondidas",
            "responded",
        )
        self.review_filter_combo.addItem(
            "Resueltas",
            "resolved",
        )
        self.review_filter_combo.addItem(
            "Todas",
            "all",
        )
        self.review_filter_combo.currentIndexChanged.connect(
            self._review_filter_changed
        )
        self.review_filter_combo.hide()
        header_row.addWidget(
            self.review_filter_combo
        )

        self.review_progress_label = QLabel(
            ""
        )
        self.review_progress_label.setStyleSheet(
            "font-weight: 700;"
        )
        self.review_progress_label.hide()
        header_row.addWidget(
            self.review_progress_label
        )
    
        # --------------------------------------------------------------
        # Área principal cara a cara
        # --------------------------------------------------------------
        work_splitter = QSplitter(
            Qt.Horizontal
        )
        work_splitter.setChildrenCollapsible(
            False
        )
    
        # IZQUIERDA: la nota del consultor es la prioridad.
        note_group = QGroupBox(
            "Mi nota"
        )
        note_layout = QVBoxLayout(
            note_group
        )
        note_layout.setContentsMargins(
            7, 6, 7, 7
        )
        note_layout.setSpacing(4)
    
        self.my_message_combo = QComboBox()
        self.my_message_combo.setToolTip(
            "Si el hilo tiene más de una intervención propia, "
            "permite elegir cuál editar."
        )
        self.my_message_combo.currentIndexChanged.connect(
            self._my_message_changed
        )
        self.my_message_combo.hide()
        note_layout.addWidget(
            self.my_message_combo
        )
    
        self.note_metadata = QLabel(
            "Sin nota seleccionada"
        )
        self.note_metadata.setWordWrap(True)
        self.note_metadata.setStyleSheet(
            "font-size: 11px; color: palette(mid);"
        )
        note_layout.addWidget(
            self.note_metadata
        )
    
        snippet_row = QHBoxLayout()
        snippet_row.setSpacing(4)
    
        self.note_marker_combo = QComboBox()
        self.note_marker_combo.addItem(
            "Insertar marcador…",
            None,
        )
        self.note_marker_combo.addItem(
            "COM:",
            "COM:",
        )
        self.note_marker_combo.addItem(
            "PT:",
            "PT:",
        )
        self.note_marker_combo.addItem(
            "SUG:",
            "SUG:",
        )
        self.note_marker_combo.addItem(
            "CONT:",
            "CONT:",
        )
        self.note_marker_combo.addItem(
            "IndS:",
            "IndS: %",
        )
        self.note_marker_combo.addItem(
            "RES:",
            "RES:",
        )
        self.note_marker_combo.addItem(
            "Plantilla completa",
            "__template__",
        )
        self.note_marker_combo.currentIndexChanged.connect(
            self._insert_note_marker_from_combo
        )
        snippet_row.addWidget(
            self.note_marker_combo,
            1,
        )

        self.spell_toggle_button = QToolButton()
        self.spell_toggle_button.setText(
            "ABC✓"
        )
        self.spell_toggle_button.setCheckable(
            True
        )
        self.spell_toggle_button.setChecked(
            self.spell_manager.enabled
        )
        self.spell_toggle_button.setToolTip(
            "Activar o desactivar la revisión ortográfica mientras escribe."
        )
        self.spell_toggle_button.toggled.connect(
            self._spellcheck_toggled
        )
        self.spell_toggle_button.setFixedHeight(
            30
        )
        snippet_row.addWidget(
            self.spell_toggle_button
        )

        self.spell_language_combo = QComboBox()
        self.spell_language_combo.setMinimumWidth(
            145
        )
        self.spell_language_combo.setMaximumWidth(
            190
        )
        self.spell_language_combo.setToolTip(
            "Idioma del corrector ortográfico para este proyecto."
        )
        for code, label in self.spell_manager.language_options():
            self.spell_language_combo.addItem(
                label,
                code,
            )
        spell_index = self.spell_language_combo.findData(
            self.spell_manager.language
        )
        if spell_index >= 0:
            self.spell_language_combo.setCurrentIndex(
                spell_index
            )
        self.spell_language_combo.currentIndexChanged.connect(
            self._spell_language_changed
        )
        snippet_row.addWidget(
            self.spell_language_combo
        )

        self.spell_options_button = QToolButton()
        self.spell_options_button.setText(
            "⚙"
        )
        self.spell_options_button.setToolTip(
            "Opciones del corrector ortográfico."
        )
        self.spell_options_button.setFixedSize(
            30,
            30,
        )
        self.spell_options_button.clicked.connect(
            self._show_spellcheck_menu
        )
        snippet_row.addWidget(
            self.spell_options_button
        )
    
        self.recipient_label = QLabel(
            "Dirigir a:"
        )
        self.recipient_combo = QComboBox()
        self.recipient_combo.setEditable(True)
        self.recipient_label.hide()
        self.recipient_combo.hide()
        snippet_row.addWidget(
            self.recipient_label
        )
        snippet_row.addWidget(
            self.recipient_combo
        )
    
        note_layout.addLayout(
            snippet_row
        )
    
        self.note_editor = SpellCheckPlainTextEdit(
            self.spell_manager
        )
        self.note_editor.setPlaceholderText(
            "COM: ...\n\n"
            "PT: ...\n\n"
            "SUG:\n"
            "A) ...\n"
            "B) ...\n\n"
            "CONT: ...\n\n"
            "IndS: %"
        )
        note_layout.addWidget(
            self.note_editor,
            1,
        )
    
        self.editability_label = QLabel("")
        self.editability_label.setStyleSheet(
            "font-size: 11px; font-weight: 600;"
        )
        note_layout.addWidget(
            self.editability_label
        )
    
        note_actions = QHBoxLayout()
        note_actions.setSpacing(4)
    
        self.new_note_button = QPushButton("＋")
        self.new_note_button.setToolTip(
            "Nueva nota sobre el texto o punto seleccionado."
        )
        self.new_note_button.clicked.connect(
            self.begin_new_note_from_current_anchor
        )
    
        self.save_note_button = QPushButton("💾")
        self.save_note_button.setToolTip(
            "Guardar cambios de mi nota."
        )
        self.save_note_button.clicked.connect(
            self.save_my_message
        )
    
        self.resolve_button = QPushButton("✓")
        self.resolve_button.setToolTip(
            "Resolver la nota conservando el historial."
        )
        self.resolve_button.setStyleSheet(
            "QPushButton { background-color: #2e9d49; color: white; "
            "font-weight: 700; padding: 5px 10px; border-radius: 4px; } "
            "QPushButton:disabled { background-color: #9abda1; }"
        )
        self.resolve_button.clicked.connect(
            self.resolve_current_thread
        )
    
        self.delete_note_button = QPushButton("🗑")
        self.delete_note_button.setToolTip(
            "Borrar físicamente la intervención propia seleccionada."
        )
        self.delete_note_button.setStyleSheet(
            "QPushButton { background-color: #b33a3a; color: white; "
            "font-weight: 700; padding: 5px 10px; border-radius: 4px; } "
            "QPushButton:disabled { background-color: #c9a3a3; }"
        )
        self.delete_note_button.clicked.connect(
            self.delete_current_message
        )
    
        self.save_new_note_button = QPushButton(
            "✓ Crear"
        )
        self.save_new_note_button.clicked.connect(
            self.save_new_note
        )
        self.save_new_note_button.hide()
    
        self.cancel_new_note_button = QPushButton(
            "✕"
        )
        self.cancel_new_note_button.setToolTip(
            "Cancelar nueva nota."
        )
        self.cancel_new_note_button.clicked.connect(
            self.cancel_new_note
        )
        self.cancel_new_note_button.hide()

        for button in (
            self.new_note_button,
            self.save_note_button,
            self.resolve_button,
            self.delete_note_button,
            self.cancel_new_note_button,
        ):
            self._configure_icon_button(
                button
            )

        self._configure_text_button(
            self.save_new_note_button
        )
    
        note_actions.addWidget(
            self.new_note_button
        )
        note_actions.addWidget(
            self.save_note_button
        )
        note_actions.addWidget(
            self.resolve_button
        )
        note_actions.addWidget(
            self.delete_note_button
        )
        note_actions.addWidget(
            self.save_new_note_button
        )
        note_actions.addWidget(
            self.cancel_new_note_button
        )
        note_actions.addStretch()
    
        note_layout.addLayout(
            note_actions
        )
    
        # DERECHA: solamente respuestas del interlocutor.
        interaction_group = QGroupBox(
            "Respuesta del interlocutor"
        )
        interaction_layout = QVBoxLayout(
            interaction_group
        )
        interaction_layout.setContentsMargins(
            7, 6, 7, 7
        )
        interaction_layout.setSpacing(4)
    
        self.interaction_label = QLabel(
            "Interacción: —"
        )
        self.interaction_label.setStyleSheet(
            "font-weight: 700;"
        )
        interaction_layout.addWidget(
            self.interaction_label
        )
    
        self.message_tree = QTreeWidget()
        self.message_tree.setHeaderLabels(
            ["Usuario", "Respuesta", "Fecha"]
        )
        self.message_tree.setRootIsDecorated(False)
        self.message_tree.setAlternatingRowColors(True)
        self.message_tree.setWordWrap(True)
        self.message_tree.setTextElideMode(
            Qt.ElideNone
        )
        self.message_tree.setUniformRowHeights(
            False
        )
        self.message_tree.header().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents,
        )
        self.message_tree.header().setSectionResizeMode(
            1,
            QHeaderView.Stretch,
        )
        self.message_tree.header().setSectionResizeMode(
            2,
            QHeaderView.ResizeToContents,
        )
        self.message_tree.currentItemChanged.connect(
            self._response_item_changed
        )
        interaction_layout.addWidget(
            self.message_tree,
            1,
        )
    
        self.reply_button = QPushButton(
            "↩ Responder"
        )
        self.reply_button.clicked.connect(
            self.begin_reply
        )
        interaction_layout.addWidget(
            self.reply_button
        )
    
        self.reply_recipient_label = QLabel(
            "Responder a:"
        )
        self.reply_recipient_combo = QComboBox()
        self.reply_recipient_combo.setEditable(
            True
        )
        self.reply_recipient_label.hide()
        self.reply_recipient_combo.hide()
    
        reply_target_row = QHBoxLayout()
        reply_target_row.addWidget(
            self.reply_recipient_label
        )
        reply_target_row.addWidget(
            self.reply_recipient_combo,
            1,
        )
        interaction_layout.addLayout(
            reply_target_row
        )
    
        self.reply_editor = SpellCheckPlainTextEdit(
            self.spell_manager
        )
        self.reply_editor.setPlaceholderText(
            "Escriba una respuesta o seguimiento para el interlocutor."
        )
        self.reply_editor.setMaximumHeight(110)
        self.reply_editor.hide()
        interaction_layout.addWidget(
            self.reply_editor
        )
    
        reply_actions = QHBoxLayout()
    
        self.save_reply_button = QPushButton(
            "✓ Enviar"
        )
        self.save_reply_button.clicked.connect(
            self.save_reply
        )
        self.save_reply_button.hide()
    
        self.cancel_reply_button = QPushButton(
            "✕"
        )
        self.cancel_reply_button.setToolTip(
            "Cancelar respuesta."
        )
        self.cancel_reply_button.clicked.connect(
            self.cancel_reply
        )
        self.cancel_reply_button.hide()

        self._configure_text_button(
            self.reply_button
        )
        self._configure_text_button(
            self.save_reply_button
        )
        self._configure_icon_button(
            self.cancel_reply_button
        )
    
        reply_actions.addStretch()
        reply_actions.addWidget(
            self.save_reply_button
        )
        reply_actions.addWidget(
            self.cancel_reply_button
        )
        interaction_layout.addLayout(
            reply_actions
        )
    
        work_splitter.addWidget(
            note_group
        )
        work_splitter.addWidget(
            interaction_group
        )
        work_splitter.setSizes(
            [620, 500]
        )
    
        # --------------------------------------------------------------
        # Comparación compacta de versiones, debajo del trabajo principal
        # --------------------------------------------------------------
        compare_header = QHBoxLayout()
    
        compare_title = QLabel(
            "Comparación del texto"
        )
        compare_title.setStyleSheet(
            "font-weight: 700;"
        )
        compare_header.addWidget(
            compare_title
        )
        compare_header.addStretch()
    
        self.verse_change_label = QLabel(
            "Cambio textual: —"
        )
        self.verse_change_label.setStyleSheet(
            "font-weight: 700; padding: 3px 8px; "
            "border-radius: 8px; background: #e6e6e6;"
        )
        compare_header.addWidget(
            self.verse_change_label
        )
    
        self.note_old_verse = QLabel(
            "Verso anterior: —"
        )
        self.note_old_verse.setWordWrap(True)
        self.note_old_verse.setTextFormat(
            Qt.RichText
        )
        self.note_old_verse.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.note_old_verse.setStyleSheet(
            "QLabel { background: #fff5d9; border: 1px solid #ead6a2; "
            "border-radius: 5px; padding: 6px 8px; }"
        )
    
        self.note_current_verse = QLabel(
            "Verso actual: —"
        )
        self.note_current_verse.setWordWrap(True)
        self.note_current_verse.setTextFormat(
            Qt.RichText
        )
        self.note_current_verse.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.note_current_verse.setStyleSheet(
            "QLabel { background: #e8f4ea; border: 1px solid #b9d7bf; "
            "border-radius: 5px; padding: 6px 8px; }"
        )
    
        layout.addLayout(
            header_row
        )
        layout.addWidget(
            work_splitter,
            1,
        )
        layout.addLayout(
            compare_header
        )
        layout.addWidget(
            self.note_old_verse
        )
        layout.addWidget(
            self.note_current_verse
        )
    
        self.notes_dock.setWidget(
            panel
        )
        self.addDockWidget(
            Qt.BottomDockWidgetArea,
            self.notes_dock,
        )
    
        self._set_notes_disabled()
    
        # ------------------------------------------------------------------
        # Panel ChatGPT: navegador opcional y ocultable
        # ------------------------------------------------------------------
    def _build_chatgpt_dock(self):
        self.chatgpt_dock = QDockWidget("ChatGPT", self)
        self.chatgpt_dock.setObjectName("ChatGPTDock")
        self.chatgpt_dock.setAllowedAreas(
            Qt.LeftDockWidgetArea
            | Qt.RightDockWidgetArea
            | Qt.BottomDockWidgetArea
        )

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        nav = QHBoxLayout()

        home = QToolButton()
        home.setText("⌂")
        home.setToolTip("Abrir ChatGPT")
        home.clicked.connect(
            lambda: self.chatgpt_browser.setUrl(
                QUrl("https://chatgpt.com")
            )
        )

        back = QToolButton()
        back.setText("←")
        back.setToolTip("Atrás")
        back.clicked.connect(
            self.chatgpt_browser_back
        )

        forward = QToolButton()
        forward.setText("→")
        forward.setToolTip("Adelante")
        forward.clicked.connect(
            self.chatgpt_browser_forward
        )

        reload_button = QToolButton()
        reload_button.setText("↻")
        reload_button.setToolTip("Recargar")
        reload_button.clicked.connect(
            self.chatgpt_browser_reload
        )

        external = QToolButton()
        external.setText("↗")
        external.setToolTip(
            "Abrir ChatGPT en el navegador externo"
        )
        external.clicked.connect(
            self.open_chatgpt_external
        )

        paste_xml = QPushButton(
            "Importar XML del portapapeles"
        )
        paste_xml.setToolTip(
            "Pega el XML copiado desde un bloque de código de ChatGPT "
            "e importa sus Comment al archivo de notas del consultor."
        )
        paste_xml.clicked.connect(
            self.import_notes_from_clipboard
        )

        for button in (
            home,
            back,
            forward,
            reload_button,
            external,
        ):
            self._configure_icon_button(
                button
            )
        self._configure_text_button(
            paste_xml
        )

        nav.addWidget(home)
        nav.addWidget(back)
        nav.addWidget(forward)
        nav.addWidget(reload_button)
        nav.addWidget(external)
        nav.addStretch()
        nav.addWidget(paste_xml)

        # Perfil persistente dedicado a ChatGPT.
        #
        # QWebEngineProfile(storageName, parent) crea un perfil basado en
        # disco. Además fijamos rutas explícitas para no depender de un
        # perfil temporal/off-the-record.
        data_root = Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppDataLocation
            )
        )
        profile_root = data_root / "webprofiles" / "chatgpt"
        storage_path = profile_root / "storage"
        cache_path = profile_root / "cache"

        storage_path.mkdir(parents=True, exist_ok=True)
        cache_path.mkdir(parents=True, exist_ok=True)

        self.chatgpt_profile = QWebEngineProfile(
            "ChatGPTPersistent",
            self,
        )
        self.chatgpt_profile.setPersistentStoragePath(
            str(storage_path)
        )
        self.chatgpt_profile.setCachePath(
            str(cache_path)
        )
        self.chatgpt_profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        self.chatgpt_profile.setHttpCacheType(
            QWebEngineProfile.HttpCacheType.DiskHttpCache
        )

        # Qt >= 6.8 puede guardar también permisos web en disco.
        try:
            self.chatgpt_profile.setPersistentPermissionsPolicy(
                QWebEngineProfile.PersistentPermissionsPolicy.StoreOnDisk
            )
        except (AttributeError, TypeError):
            pass

        self.chatgpt_browser = QWebEngineView()
        self.chatgpt_page = QWebEnginePage(
            self.chatgpt_profile,
            self.chatgpt_browser,
        )
        self.chatgpt_browser.setPage(
            self.chatgpt_page
        )

        self.chatgpt_browser.settings().setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
            True,
        )
        self.chatgpt_browser.setUrl(
            QUrl("https://chatgpt.com")
        )

        layout.addLayout(nav)
        layout.addWidget(self.chatgpt_browser, 1)

        self.chatgpt_dock.setWidget(panel)
        self.addDockWidget(
            Qt.RightDockWidgetArea,
            self.chatgpt_dock,
        )

        # No ocupa espacio al iniciar. El usuario lo muestra desde Ver o
        # desde la barra principal cuando lo necesita.
        self.chatgpt_dock.hide()

    def chatgpt_browser_back(self):
        self.chatgpt_browser.back()

    def chatgpt_browser_forward(self):
        self.chatgpt_browser.forward()

    def chatgpt_browser_reload(self):
        self.chatgpt_browser.reload()

    def open_chatgpt_external(self):
        webbrowser.open("https://chatgpt.com")

    def clear_chatgpt_session(self):
        answer = QMessageBox.question(
            self,
            "Cerrar sesión de ChatGPT",
            "¿Borrar las cookies guardadas del panel ChatGPT?\n\n"
            "La próxima vez tendrá que iniciar sesión nuevamente.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        # Limpiar cookies y caché del perfil dedicado.
        self.chatgpt_profile.cookieStore().deleteAllCookies()
        self.chatgpt_profile.clearHttpCache()

        self.chatgpt_browser.setUrl(
            QUrl("https://chatgpt.com")
        )

        QMessageBox.information(
            self,
            "ChatGPT",
            "Se borraron las cookies del panel ChatGPT. "
            "Cuando vuelva a entrar deberá iniciar sesión.",
        )

    def show_chatgpt_panel(self):
        if self.chatgpt_dock.isVisible():
            self.chatgpt_dock.hide()
        else:
            self.chatgpt_dock.show()
            self.chatgpt_dock.raise_()


# ------------------------------------------------------------------
# Panel lateral: búsqueda y edición masiva de notas
# ------------------------------------------------------------------


    def _build_note_tools_dock(self):
        self.note_tools_dock = QDockWidget(
            "Buscar / editar notas",
            self,
        )
        self.note_tools_dock.setObjectName(
            "NoteToolsDock"
        )
        self.note_tools_dock.setAllowedAreas(
            Qt.LeftDockWidgetArea
            | Qt.RightDockWidgetArea
        )
        self.note_tools_dock.setMinimumWidth(
            420
        )

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(
            6, 6, 6, 6
        )
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        self.note_tools_scope_combo = QComboBox()
        self.note_tools_scope_combo.addItem(
            "Capítulo actual",
            "chapter",
        )
        self.note_tools_scope_combo.addItem(
            "Todo el proyecto",
            "project",
        )
        self.note_tools_scope_combo.setToolTip(
            "La búsqueda siempre se limita al proyecto abierto."
        )
        self.note_tools_scope_combo.currentIndexChanged.connect(
            self._note_tools_scope_changed
        )

        self.note_tools_preset_combo = QComboBox()
        self.note_tools_preset_combo.addItem(
            "Criterio rápido…",
            None,
        )
        self.note_tools_preset_combo.addItem(
            "Encontrar notas con IndS 90 %",
            "inds90",
        )
        self.note_tools_preset_combo.addItem(
            "Eliminar notas completas con IndS 90 %",
            "delete_note_inds90",
        )
        self.note_tools_preset_combo.addItem(
            "Eliminar párrafos IndS (cualquier %)",
            "delete_inds",
        )
        self.note_tools_preset_combo.addItem(
            "Eliminar párrafos que terminan en porcentaje",
            "delete_percent_paragraph",
        )
        self.note_tools_preset_combo.addItem(
            "Borrar desde una frase hasta el próximo punto…",
            "phrase_to_period",
        )
        self.note_tools_preset_combo.currentIndexChanged.connect(
            self._note_tools_preset_changed
        )

        top_row.addWidget(
            self.note_tools_scope_combo
        )
        top_row.addWidget(
            self.note_tools_preset_combo,
            1,
        )

        search_row = QHBoxLayout()
        search_row.setSpacing(4)

        self.note_tools_pattern_edit = QLineEdit()
        self.note_tools_pattern_edit.setPlaceholderText(
            r"Buscar texto o regex: \bIndS:\s*90\s*%"
        )
        self.note_tools_pattern_edit.returnPressed.connect(
            self.preview_note_tool_search
        )

        self.note_tools_preview_button = QPushButton(
            "Buscar"
        )
        self._configure_text_button(
            self.note_tools_preview_button
        )
        self.note_tools_preview_button.clicked.connect(
            self.preview_note_tool_search
        )

        search_row.addWidget(
            self.note_tools_pattern_edit,
            1,
        )
        search_row.addWidget(
            self.note_tools_preview_button
        )

        options_row = QHBoxLayout()
        options_row.setSpacing(4)

        self.note_tools_regex_checkbox = QCheckBox(
            "Regex"
        )
        self.note_tools_regex_checkbox.setChecked(
            True
        )

        self.note_tools_case_checkbox = QCheckBox(
            "Aa"
        )
        self.note_tools_case_checkbox.setToolTip(
            "Distinguir mayúsculas y minúsculas."
        )

        self.note_tools_operation_combo = QComboBox()
        self.note_tools_operation_combo.addItem(
            "Solo buscar",
            "search",
        )
        self.note_tools_operation_combo.addItem(
            "Eliminar nota completa",
            "delete_comment",
        )
        self.note_tools_operation_combo.addItem(
            "Eliminar párrafo <p>",
            "delete_paragraph",
        )
        self.note_tools_operation_combo.addItem(
            "Buscar / reemplazar",
            "replace",
        )
        self.note_tools_operation_combo.currentIndexChanged.connect(
            self._note_tools_operation_changed
        )

        options_row.addWidget(
            self.note_tools_regex_checkbox
        )
        options_row.addWidget(
            self.note_tools_case_checkbox
        )
        options_row.addWidget(
            self.note_tools_operation_combo,
            1,
        )

        self.note_tools_replacement_edit = QLineEdit()
        self.note_tools_replacement_edit.setPlaceholderText(
            "Reemplazo; vacío = borrar solo la coincidencia."
        )
        self.note_tools_replacement_edit.hide()

        action_row = QHBoxLayout()
        action_row.setSpacing(4)

        self.note_tools_check_all_button = QToolButton()
        self.note_tools_check_all_button.setText(
            "☑"
        )
        self.note_tools_check_all_button.setToolTip(
            "Seleccionar todos los resultados."
        )
        self._configure_icon_button(
            self.note_tools_check_all_button
        )
        self.note_tools_check_all_button.clicked.connect(
            lambda: self._set_note_tool_results_checked(
                True
            )
        )

        self.note_tools_uncheck_all_button = QToolButton()
        self.note_tools_uncheck_all_button.setText(
            "☐"
        )
        self.note_tools_uncheck_all_button.setToolTip(
            "Quitar selección de todos los resultados."
        )
        self._configure_icon_button(
            self.note_tools_uncheck_all_button
        )
        self.note_tools_uncheck_all_button.clicked.connect(
            lambda: self._set_note_tool_results_checked(
                False
            )
        )

        self.note_tools_apply_button = QPushButton(
            "Aplicar"
        )
        self.note_tools_apply_button.setToolTip(
            "Aplicar la operación a los resultados marcados."
        )
        self._configure_text_button(
            self.note_tools_apply_button
        )
        self.note_tools_apply_button.setEnabled(
            False
        )
        self.note_tools_apply_button.clicked.connect(
            self.apply_note_tool_changes
        )

        self.note_tools_summary_label = QLabel(
            "Capítulo actual · escriba un criterio y pulse Buscar."
        )
        self.note_tools_summary_label.setWordWrap(
            True
        )
        self.note_tools_summary_label.setStyleSheet(
            "font-size: 11px; color: palette(mid);"
        )

        action_row.addWidget(
            self.note_tools_check_all_button
        )
        action_row.addWidget(
            self.note_tools_uncheck_all_button
        )
        action_row.addWidget(
            self.note_tools_summary_label,
            1,
        )
        action_row.addWidget(
            self.note_tools_apply_button
        )

        self.note_tools_results = QTreeWidget()
        self.note_tools_results.setHeaderLabels(
            [
                "",
                "VerseRef",
                "Fecha",
                "Coincidencia",
            ]
        )
        self.note_tools_results.setRootIsDecorated(
            False
        )
        self.note_tools_results.setAlternatingRowColors(
            True
        )
        self.note_tools_results.setWordWrap(
            True
        )
        self.note_tools_results.setTextElideMode(
            Qt.ElideRight
        )
        self.note_tools_results.header().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents,
        )
        self.note_tools_results.header().setSectionResizeMode(
            1,
            QHeaderView.ResizeToContents,
        )
        self.note_tools_results.header().setSectionResizeMode(
            2,
            QHeaderView.ResizeToContents,
        )
        self.note_tools_results.header().setSectionResizeMode(
            3,
            QHeaderView.Stretch,
        )
        self.note_tools_results.itemClicked.connect(
            self._note_tool_result_clicked
        )

        layout.addLayout(
            top_row
        )
        layout.addLayout(
            search_row
        )
        layout.addLayout(
            options_row
        )
        layout.addWidget(
            self.note_tools_replacement_edit
        )
        layout.addLayout(
            action_row
        )
        layout.addWidget(
            self.note_tools_results,
            1,
        )

        self.note_tools_dock.setWidget(
            panel
        )
        self.addDockWidget(
            Qt.RightDockWidgetArea,
            self.note_tools_dock,
        )
        self.note_tools_dock.hide()

        self.note_tools_dock.visibilityChanged.connect(
            self._note_tools_visibility_changed
        )


    def _note_tools_visibility_changed(
        self,
        visible: bool,
    ):
        if not visible:
            return

        # Herramientas de notas tiene prioridad de espacio frente a Biblia.
        if self.bible_dock.isVisible():
            self.bible_dock.hide()

        self.note_tools_dock.raise_()

        # Cada apertura comienza en el ámbito más seguro y frecuente.
        self.note_tools_scope_combo.blockSignals(
            True
        )
        self.note_tools_scope_combo.setCurrentIndex(
            0
        )
        self.note_tools_scope_combo.blockSignals(
            False
        )

        self._clear_note_tool_results(
            self._note_tools_scope_description()
        )


    def _note_tools_scope_description(
        self,
    ) -> str:
        if (
            self.note_tools_scope_combo.currentData()
            == "project"
        ):
            return "Todo el proyecto"

        if (
            self.current_text is not None
            and self.current_chapter
        ):
            return (
                f"Capítulo actual: "
                f"{self.current_text.document.title} "
                f"{self.current_chapter}"
            )

        return "Capítulo actual"


    def _clear_note_tool_results(
        self,
        message: str | None = None,
    ):
        if not hasattr(
            self,
            "note_tools_results",
        ):
            return

        self.bulk_search_hits = []
        self.note_tools_results.clear()
        self.note_tools_apply_button.setEnabled(
            False
        )
        self.note_tools_summary_label.setText(
            message
            or self._note_tools_scope_description()
        )


    def _note_tools_preset_changed(
        self,
        index,
    ):
        preset = self.note_tools_preset_combo.itemData(
            index
        )

        self.note_tools_preset_combo.blockSignals(
            True
        )
        self.note_tools_preset_combo.setCurrentIndex(
            0
        )
        self.note_tools_preset_combo.blockSignals(
            False
        )

        if not preset:
            return

        self.note_tools_regex_checkbox.setChecked(
            True
        )
        self.note_tools_case_checkbox.setChecked(
            False
        )

        if preset == "inds90":
            self.note_tools_pattern_edit.setText(
                r"\bIndS:\s*90\s*%"
            )
            operation = "search"

        elif preset == "delete_note_inds90":
            self.note_tools_pattern_edit.setText(
                r"\bIndS:\s*90\s*%"
            )
            operation = "delete_comment"

        elif preset == "delete_inds":
            self.note_tools_pattern_edit.setText(
                r"^\s*IndS:\s*\d{1,3}(?:[.,]\d+)?\s*%\s*$"
            )
            operation = "delete_paragraph"

        elif preset == "delete_percent_paragraph":
            self.note_tools_pattern_edit.setText(
                r"^\s*.*?\d{1,3}(?:[.,]\d+)?\s*%\s*$"
            )
            operation = "delete_paragraph"

        elif preset == "phrase_to_period":
            phrase, ok = QInputDialog.getText(
                self,
                "Borrar desde una frase hasta el punto",
                "Texto con el que inicia el fragmento:",
            )
            if (
                not ok
                or not phrase.strip()
            ):
                return

            self.note_tools_pattern_edit.setText(
                re.escape(
                    phrase.strip()
                )
                + r"[^.]*\."
            )
            self.note_tools_replacement_edit.clear()
            operation = "replace"

        else:
            return

        idx = self.note_tools_operation_combo.findData(
            operation
        )
        if idx >= 0:
            self.note_tools_operation_combo.setCurrentIndex(
                idx
            )


    def _note_tools_scope_changed(
        self,
        index,
    ):
        self._clear_note_tool_results(
            self._note_tools_scope_description()
        )


    def _note_tools_operation_changed(
        self,
        index,
    ):
        operation = (
            self.note_tools_operation_combo.itemData(
                index
            )
        )

        self.note_tools_replacement_edit.setVisible(
            operation == "replace"
        )
        self._clear_note_tool_results(
            self._note_tools_scope_description()
        )


    def _note_tool_documents(
        self,
        operation,
    ):
        if not self.notes_workspace:
            return []

        document = (
            self.notes_workspace.consultant_document()
        )
        return [
            document
        ] if document is not None else []


    def _note_tool_hit_in_scope(
        self,
        hit,
    ) -> bool:
        if (
            self.note_tools_scope_combo.currentData()
            == "project"
        ):
            return True

        if (
            self.current_text is None
            or not self.current_chapter
        ):
            return False

        ref = normalize_verse_ref(
            hit.verse_ref
        )
        parts = ref.split(".")
        if len(parts) < 2:
            return False

        current_book = (
            self.current_text.document.book
            or ""
        ).upper()

        return (
            parts[0] == current_book
            and parts[1] == str(
                self.current_chapter
            )
        )


    def preview_note_tool_search(self):
        if not self.notes_workspace:
            QMessageBox.information(
                self,
                "Buscar notas",
                "Abra primero un proyecto con archivos Notes_*.xml.",
            )
            return

        if (
            self.note_tools_scope_combo.currentData()
            == "chapter"
            and (
                self.current_text is None
                or not self.current_chapter
            )
        ):
            QMessageBox.information(
                self,
                "Buscar notas",
                "No hay un capítulo activo.",
            )
            return

        pattern = (
            self.note_tools_pattern_edit.text()
        )
        operation = (
            self.note_tools_operation_combo.currentData()
        )

        try:
            hits = search_documents(
                self._note_tool_documents(
                    operation
                ),
                pattern,
                use_regex=self.note_tools_regex_checkbox.isChecked(),
                case_sensitive=self.note_tools_case_checkbox.isChecked(),
                operation=operation,
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Criterio de búsqueda",
                str(exc),
            )
            return

        hits = [
            hit
            for hit in hits
            if self._note_tool_hit_in_scope(
                hit
            )
        ]

        self.bulk_search_hits = hits
        self.note_tools_results.clear()

        unique_comments = set()

        for hit in hits:
            unique_comments.add(
                (
                    hit.thread,
                    hit.message.source_index,
                )
            )

            item = QTreeWidgetItem(
                [
                    "",
                    hit.verse_ref,
                    (
                        hit.date[:16].replace(
                            "T",
                            " ",
                        )
                        if hit.date
                        else ""
                    ),
                    hit.preview,
                ]
            )
            item.setData(
                0,
                Qt.UserRole,
                hit,
            )

            ref_font = QFont(
                item.font(1)
            )
            ref_font.setUnderline(
                True
            )
            item.setFont(
                1,
                ref_font,
            )
            item.setToolTip(
                1,
                "Clic para ir a esta nota y a su versículo."
            )

            if operation != "search":
                item.setFlags(
                    item.flags()
                    | Qt.ItemIsUserCheckable
                )
                item.setCheckState(
                    0,
                    Qt.Checked,
                )

            self.note_tools_results.addTopLevelItem(
                item
            )

        scope_text = (
            self._note_tools_scope_description()
        )

        if hits:
            self.note_tools_summary_label.setText(
                f"{scope_text} · "
                f"{len(hits)} coincidencia(s) en "
                f"{len(unique_comments)} nota(s). "
                "Clic en VerseRef para ir a la nota."
            )
        else:
            self.note_tools_summary_label.setText(
                f"{scope_text} · sin coincidencias."
            )

        self.note_tools_apply_button.setEnabled(
            operation != "search"
            and bool(hits)
        )


    def _set_note_tool_results_checked(
        self,
        checked,
    ):
        state = (
            Qt.Checked
            if checked
            else Qt.Unchecked
        )

        for index in range(
            self.note_tools_results.topLevelItemCount()
        ):
            item = self.note_tools_results.topLevelItem(
                index
            )
            if (
                item.flags()
                & Qt.ItemIsUserCheckable
            ):
                item.setCheckState(
                    0,
                    state,
                )


    def _selected_note_tool_hits(self):
        selected = []

        for index in range(
            self.note_tools_results.topLevelItemCount()
        ):
            item = self.note_tools_results.topLevelItem(
                index
            )
            if not (
                item.flags()
                & Qt.ItemIsUserCheckable
            ):
                continue

            if item.checkState(0) != Qt.Checked:
                continue

            hit = item.data(
                0,
                Qt.UserRole,
            )
            if hit is not None:
                selected.append(
                    hit
                )

        return selected


    def apply_note_tool_changes(self):
        if not self.notes_workspace:
            return

        operation = (
            self.note_tools_operation_combo.currentData()
        )
        if operation == "search":
            return

        selected = self._selected_note_tool_hits()
        if not selected:
            QMessageBox.information(
                self,
                "Herramientas de notas",
                "Seleccione al menos un resultado para modificar.",
            )
            return

        document = (
            self.notes_workspace.consultant_document()
        )
        if document is None:
            return

        selected = [
            hit
            for hit in selected
            if hit.document.path == document.path
        ]
        if not selected:
            return

        pattern = (
            self.note_tools_pattern_edit.text()
        )
        replacement = (
            self.note_tools_replacement_edit.text()
        )

        unique_comments = {
            (
                hit.thread,
                hit.message.source_index,
            )
            for hit in selected
        }

        if operation == "delete_comment":
            response_threads = 0

            for thread_id, _source_index in unique_comments:
                thread = self.notes_workspace.thread(
                    thread_id
                )
                if (
                    thread
                    and any(
                        not wrapped.deleted
                        for wrapped in thread.other_messages()
                    )
                ):
                    response_threads += 1

            effect = (
                f"Se eliminarán {len(unique_comments)} <Comment> completos."
            )

            if response_threads:
                effect += (
                    f"\n\nAtención: {response_threads} nota(s) "
                    "tienen respuestas de otro usuario. "
                    "Las respuestas externas no se borrarán."
                )

        elif operation == "delete_paragraph":
            effect = (
                f"Se eliminarán hasta {len(selected)} párrafos <p>."
            )

        else:
            effect = (
                f"Se reemplazará texto en hasta {len(selected)} párrafos. "
                + (
                    f"Reemplazo: «{replacement}»."
                    if replacement
                    else "El reemplazo está vacío: se borrará solo la coincidencia."
                )
            )

        answer = QMessageBox.warning(
            self,
            "Confirmar edición masiva",
            "Esta operación modificará:\n"
            f"{document.path.name}\n\n"
            f"Ámbito: {self._note_tools_scope_description()}\n\n"
            f"Criterio:\n{pattern}\n\n"
            f"{effect}\n\n"
            "Se creará un backup antes de guardar.\n\n"
            "¿Desea continuar?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            result = apply_bulk_operation(
                document,
                selected,
                pattern,
                operation,
                replacement=replacement,
                use_regex=self.note_tools_regex_checkbox.isChecked(),
                case_sensitive=self.note_tools_case_checkbox.isChecked(),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Edición masiva",
                str(exc),
            )
            return

        self.notes_workspace.reload()
        self._after_internal_file_write()
        self._refresh_note_markers()
        self._refresh_threads_for_reference()

        backup_text = (
            str(result.backup_path)
            if result.backup_path
            else "No hubo cambios."
        )

        QMessageBox.information(
            self,
            "Edición masiva terminada",
            f"Notas afectadas: {result.changed_comments}\n"
            f"Párrafos afectados: {result.changed_paragraphs}\n"
            f"Notas eliminadas: {result.deleted_comments}\n\n"
            f"Backup:\n{backup_text}",
        )

        self.preview_note_tool_search()


    def _note_tool_result_clicked(
        self,
        item,
        column,
    ):
        if column != 1:
            return

        self._note_tool_result_activated(
            item,
            column,
        )


    def _note_tool_result_activated(
        self,
        item,
        column,
    ):
        hit = item.data(
            0,
            Qt.UserRole,
        )
        if hit is None:
            return

        self._navigate_to_note_reference(
            hit.verse_ref,
            hit.thread,
        )


    def _build_resources_dock(self):
        self.resources_dock = QDockWidget(
            "📚 Recursos bíblicos",
            self,
        )
        self.resources_dock.setObjectName(
            "ResourcesDock"
        )
        self.resources_dock.setAllowedAreas(
            Qt.LeftDockWidgetArea
            | Qt.RightDockWidgetArea
        )
        self.resources_dock.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )
        self.resources_dock.setMinimumWidth(
            520
        )

        self.resources_panel = ResourcePanelWidget(
            self.settings,
            "resources/main",
            self.resources_dock,
            allow_dock_actions=True,
        )

        self.resources_panel.toggle_floating_requested.connect(
            self._toggle_resources_floating
        )
        self.resources_panel.move_screen_requested.connect(
            self._move_resources_to_next_screen
        )
        self.resources_panel.new_window_requested.connect(
            self._new_resource_window
        )
        self.resources_panel.local_folder_requested.connect(
            lambda:
                self.resources_panel.choose_local_folder(
                    self
                )
        )
        self.resources_panel.use_chatgpt_requested.connect(
            self._use_resource_with_chatgpt
        )
        self.resources_panel.navigate_reference_requested.connect(
            self._navigate_to_resource_reference
        )

        self.resources_dock.setWidget(
            self.resources_panel
        )
        self.addDockWidget(
            Qt.RightDockWidgetArea,
            self.resources_dock,
        )
        self.resources_dock.hide()

        self.resources_dock.visibilityChanged.connect(
            self._resources_visibility_changed
        )
        self.resources_dock.topLevelChanged.connect(
            lambda _floating:
                self._save_project_session()
        )


    def _resources_visibility_changed(
        self,
        visible: bool,
    ):
        if visible:
            # Comportamiento tipo offcanvas: Recursos tiene prioridad sobre el
            # navegador bíblico para liberar espacio horizontal.
            if self.bible_dock.isVisible():
                self.bible_dock.hide()

            self.resources_dock.raise_()
            self._sync_resource_reference(
                self.current_reference
                or self.reference_controller.reference
            )

        self._save_project_session()


    def toggle_resources_panel(self):
        visible = (
            self.resources_dock.isVisible()
        )
        self.resources_dock.setVisible(
            not visible
        )
        if not visible:
            self.resources_dock.raise_()


    def _toggle_resources_floating(self):
        self.resources_dock.setFloating(
            not self.resources_dock.isFloating()
        )
        self.resources_dock.show()
        self.resources_dock.raise_()


    def _ensure_widget_on_available_screen(
        self,
        widget,
    ):
        screens = QApplication.screens()
        if not screens:
            return

        frame = widget.frameGeometry()
        if any(
            screen.availableGeometry().intersects(
                frame
            )
            for screen in screens
        ):
            return

        target = QApplication.primaryScreen()
        available = target.availableGeometry()

        width = min(
            max(
                widget.width(),
                420,
            ),
            max(
                420,
                available.width() - 60,
            ),
        )
        height = min(
            max(
                widget.height(),
                520,
            ),
            max(
                520,
                available.height() - 60,
            ),
        )

        widget.setGeometry(
            available.x()
            + (
                available.width()
                - width
            )
            // 2,
            available.y()
            + (
                available.height()
                - height
            )
            // 2,
            width,
            height,
        )

    def _move_widget_to_next_screen(
        self,
        widget,
    ):
        screens = QApplication.screens()
        if len(screens) < 2:
            self.statusBar().showMessage(
                "Solo se detecta una pantalla.",
                3500,
            )
            return

        current_screen = (
            widget.screen()
            if hasattr(
                widget,
                "screen",
            )
            else None
        )
        if current_screen not in screens:
            current_screen = (
                QApplication.primaryScreen()
            )

        try:
            current_index = screens.index(
                current_screen
            )
        except ValueError:
            current_index = 0

        target = screens[
            (current_index + 1)
            % len(screens)
        ]
        available = target.availableGeometry()

        size = widget.size()
        width = min(
            max(
                size.width(),
                420,
            ),
            max(
                420,
                available.width() - 60,
            ),
        )
        height = min(
            max(
                size.height(),
                520,
            ),
            max(
                520,
                available.height() - 60,
            ),
        )

        x = (
            available.x()
            + max(
                20,
                (
                    available.width()
                    - width
                )
                // 2,
            )
        )
        y = (
            available.y()
            + max(
                20,
                (
                    available.height()
                    - height
                )
                // 2,
            )
        )

        widget.setGeometry(
            x,
            y,
            width,
            height,
        )
        widget.show()
        widget.raise_()
        widget.activateWindow()

        self.statusBar().showMessage(
            f"Recursos movidos a: "
            f"{target.name() or 'otra pantalla'}.",
            3500,
        )


    def _move_resources_to_next_screen(self):
        if not self.resources_dock.isFloating():
            self.resources_dock.setFloating(
                True
            )

        QTimer.singleShot(
            50,
            lambda:
                self._move_widget_to_next_screen(
                    self.resources_dock
                ),
        )


    def _resource_window_prefix(
        self,
        resource_id: int,
    ) -> str:
        return (
            f"resources/extra/{resource_id}"
        )


    def _configure_resource_window(
        self,
        window,
    ):
        panel = window.panel

        panel.new_window_requested.connect(
            self._new_resource_window
        )
        panel.move_screen_requested.connect(
            lambda w=window:
                self._move_widget_to_next_screen(
                    w
                )
        )
        panel.local_folder_requested.connect(
            lambda p=panel:
                p.choose_local_folder(
                    window
                )
        )
        panel.use_chatgpt_requested.connect(
            self._use_resource_with_chatgpt
        )
        panel.navigate_reference_requested.connect(
            self._navigate_to_resource_reference
        )
        window.closed.connect(
            self._resource_window_closed
        )


    def _new_resource_window(
        self,
        checked=False,
        *,
        resource_id=None,
        geometry=None,
        show_window=True,
    ):
        if resource_id is None:
            self._resource_window_counter += 1
            resource_id = (
                self._resource_window_counter
            )
        else:
            self._resource_window_counter = max(
                self._resource_window_counter,
                int(resource_id),
            )

        prefix = self._resource_window_prefix(
            int(resource_id)
        )

        source_panel = None
        sender = self.sender()
        if isinstance(
            sender,
            ResourcePanelWidget,
        ):
            source_panel = sender
        elif (
            geometry is None
            and hasattr(
                self,
                "resources_panel",
            )
        ):
            source_panel = self.resources_panel

        window = ResourceFloatingWindow(
            self.settings,
            prefix,
            None,
        )
        window.resource_id = int(
            resource_id
        )
        self._configure_resource_window(
            window
        )

        if source_panel is not None:
            window.panel.set_source(
                source_panel.source_key()
            )

            window.panel.follow_checkbox.setChecked(
                source_panel.follow_checkbox.isChecked()
            )
            if not source_panel.follow_checkbox.isChecked():
                window.panel.fixed_reference = (
                    source_panel.effective_reference()
                )
                window.panel.refresh()

        self.resource_windows.append(
            window
        )

        reference = (
            self.current_reference
            or self.reference_controller.reference
        )
        if reference:
            window.panel.set_reference(
                reference
            )

        if geometry is not None:
            try:
                window.restoreGeometry(
                    geometry
                )
            except Exception:
                pass

        if show_window:
            window.show()
            QTimer.singleShot(
                30,
                lambda w=window:
                    self._ensure_widget_on_available_screen(
                        w
                    ),
            )
            window.raise_()

        self._save_resource_windows()
        return window


    def _resource_window_closed(
        self,
        window,
    ):
        if self._closing_app:
            return

        self.resource_windows = [
            item
            for item in self.resource_windows
            if item is not window
        ]
        self._save_resource_windows()


    def _save_resource_windows(self):
        self.settings.beginWriteArray(
            "resource_windows",
            len(self.resource_windows),
        )

        for index, window in enumerate(
            self.resource_windows
        ):
            self.settings.setArrayIndex(
                index
            )
            self.settings.setValue(
                "resource_id",
                int(
                    getattr(
                        window,
                        "resource_id",
                        index + 1,
                    )
                ),
            )
            self.settings.setValue(
                "geometry",
                window.saveGeometry(),
            )
            self.settings.setValue(
                "visible",
                window.isVisible(),
            )

        self.settings.endArray()
        self.settings.sync()


    def _restore_resource_windows(self):
        count = self.settings.beginReadArray(
            "resource_windows"
        )
        saved = []

        for index in range(count):
            self.settings.setArrayIndex(
                index
            )
            resource_id = int(
                self.settings.value(
                    "resource_id",
                    index + 1,
                )
            )
            geometry = self.settings.value(
                "geometry"
            )
            visible = self.settings.value(
                "visible",
                True,
                type=bool,
            )
            saved.append(
                (
                    resource_id,
                    geometry,
                    visible,
                )
            )

        self.settings.endArray()

        for (
            resource_id,
            geometry,
            visible,
        ) in saved:
            self._new_resource_window(
                resource_id=resource_id,
                geometry=geometry,
                show_window=visible,
            )


    def _sync_resource_reference(
        self,
        reference: str,
    ):
        reference = normalize_verse_ref(
            reference
        )
        if not reference:
            return

        if hasattr(
            self,
            "resources_panel",
        ):
            self.resources_panel.set_reference(
                reference
            )

        for window in list(
            self.resource_windows
        ):
            try:
                window.panel.set_reference(
                    reference
                )
            except RuntimeError:
                # La ventana pudo ser cerrada entre señales.
                pass


    def _current_sfm_for_resource_context(self):
        if (
            not self.current_text
            or not self.current_reference
        ):
            return ""

        reference = normalize_verse_ref(
            self.current_reference
        )

        for verse in self.current_text.document.verses:
            if (
                normalize_verse_ref(
                    verse.reference
                )
                == reference
            ):
                return (
                    verse.source_text
                    or verse.text
                    or ""
                )

        return ""


    def _current_note_context(self):
        thread = (
            self.current_interaction_thread
        )
        if thread is None:
            return (
                "",
                "",
            )

        own = (
            thread.original_consultant_message()
        )
        own_text = (
            own.message.contents
            if own
            else ""
        )

        external = []
        for wrapped in thread.other_messages():
            if wrapped.deleted:
                continue
            content = (
                wrapped.message.contents
                or ""
            ).strip()
            if content:
                external.append(
                    f"{wrapped.owner}: {content}"
                )

        return (
            own_text,
            "\n\n".join(
                external
            ),
        )


    def _navigate_to_resource_reference(
        self,
        reference: str,
    ):
        reference = normalize_verse_ref(
            reference
        )
        if not reference:
            return

        self._navigate_to_note_reference(
            reference,
            None,
        )


    def _use_resource_with_chatgpt(
        self,
        resource_text: str,
    ):
        sfm = (
            self._current_sfm_for_resource_context()
        )
        note_text, response_text = (
            self._current_note_context()
        )

        parts = [
            "CONTEXTO DE CONSULTOR APP",
            f"Referencia: "
            f"{self.current_reference or self.reference_controller.reference or '—'}",
        ]

        if sfm:
            parts.extend(
                [
                    "",
                    "SFM ACTUAL",
                    sfm,
                ]
            )

        if note_text:
            parts.extend(
                [
                    "",
                    "NOTA DEL CONSULTOR",
                    note_text,
                ]
            )

        if response_text:
            parts.extend(
                [
                    "",
                    "RESPUESTA / INTERACCIÓN",
                    response_text,
                ]
            )

        parts.extend(
            [
                "",
                resource_text,
            ]
        )

        payload = "\n".join(
            parts
        ).strip()

        QApplication.clipboard().setText(
            payload
        )
        self.show_chatgpt_panel()

        self.statusBar().showMessage(
            "Contexto del recurso copiado. "
            "Péguelo en ChatGPT con Ctrl+V.",
            5000,
        )

    def _build_toolbar(self):
        toolbar = QToolBar(
            "Herramientas",
            self,
        )
        toolbar.setObjectName(
            "MainToolbar"
        )
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(
            Qt.ToolButtonTextOnly
        )
        self.addToolBar(
            Qt.TopToolBarArea,
            toolbar,
        )

        def add_icon_button(
            symbol,
            tooltip,
            callback,
            shortcut=None,
        ):
            button = QToolButton()
            button.setText(symbol)
            button.setToolTip(tooltip)
            button.setAutoRaise(True)
            self._configure_icon_button(
                button
            )
            if shortcut:
                button.setShortcut(
                    shortcut
                )
            button.clicked.connect(
                callback
            )
            toolbar.addWidget(
                button
            )
            return button

        add_icon_button(
            "📂",
            "Abrir proyecto (Ctrl+O)",
            self.open_project,
            QKeySequence.Open,
        )
        add_icon_button(
            "📖",
            "Mostrar u ocultar Biblia",
            lambda: self.bible_dock.setVisible(
                not self.bible_dock.isVisible()
            ),
        )
        add_icon_button(
            "💬",
            "Mostrar u ocultar ChatGPT",
            self.show_chatgpt_panel,
        )
        add_icon_button(
            "📚",
            "Mostrar u ocultar Recursos bíblicos",
            self.toggle_resources_panel,
        )
        add_icon_button(
            "⧉",
            "Copiar rango SFM al portapapeles",
            self.copy_sfm_range_to_clipboard,
        )
        add_icon_button(
            "✚",
            "Nueva nota sobre selección o cursor (Ctrl+Shift+N)",
            self.begin_new_note_from_current_anchor,
            "Ctrl+Shift+N",
        )

        toolbar.addSeparator()

        self.text_combo = QComboBox()
        self.text_combo.setMinimumWidth(
            175
        )
        self.text_combo.setToolTip(
            "Libro / archivo SFM activo"
        )
        self.text_combo.currentIndexChanged.connect(
            self._text_changed
        )
        toolbar.addWidget(
            self.text_combo
        )

        self.prev_chapter_button = QToolButton()
        self.prev_chapter_button.setText("◀")
        self.prev_chapter_button.setToolTip(
            "Capítulo anterior"
        )
        self.prev_chapter_button.setStyleSheet(
            GREEN_BUTTON_STYLE
        )
        self._configure_icon_button(
            self.prev_chapter_button
        )
        self.prev_chapter_button.clicked.connect(
            lambda: self.move_chapter(-1)
        )
        toolbar.addWidget(
            self.prev_chapter_button
        )

        self.chapter_combo = QComboBox()
        self.chapter_combo.setMinimumWidth(
            88
        )
        self.chapter_combo.setToolTip(
            "Capítulo activo"
        )
        self.chapter_combo.currentIndexChanged.connect(
            self._chapter_changed
        )
        toolbar.addWidget(
            self.chapter_combo
        )

        self.next_chapter_button = QToolButton()
        self.next_chapter_button.setText("▶")
        self.next_chapter_button.setToolTip(
            "Capítulo siguiente"
        )
        self.next_chapter_button.setStyleSheet(
            GREEN_BUTTON_STYLE
        )
        self._configure_icon_button(
            self.next_chapter_button
        )
        self.next_chapter_button.clicked.connect(
            lambda: self.move_chapter(1)
        )
        toolbar.addWidget(
            self.next_chapter_button
        )

        # Historial de referencias visitadas.
        self.prev_reference_button = QToolButton()
        self.prev_reference_button.setText("↶")
        self.prev_reference_button.setToolTip(
            "Volver a la referencia anterior visitada"
        )
        self.prev_reference_button.setStyleSheet(
            GREEN_BUTTON_STYLE
        )
        self._configure_icon_button(
            self.prev_reference_button
        )
        self.prev_reference_button.clicked.connect(
            lambda: self.move_reference_history(-1)
        )
        toolbar.addWidget(
            self.prev_reference_button
        )

        self.reference_history_combo = QComboBox()
        self.reference_history_combo.setMinimumWidth(
            150
        )
        self.reference_history_combo.setMaximumWidth(
            230
        )
        self.reference_history_combo.setToolTip(
            "Historial de referencias visitadas"
        )
        self.reference_history_combo.currentIndexChanged.connect(
            self._reference_history_combo_changed
        )
        toolbar.addWidget(
            self.reference_history_combo
        )

        self.next_reference_button = QToolButton()
        self.next_reference_button.setText("↷")
        self.next_reference_button.setToolTip(
            "Ir a la referencia siguiente del historial"
        )
        self.next_reference_button.setStyleSheet(
            GREEN_BUTTON_STYLE
        )
        self._configure_icon_button(
            self.next_reference_button
        )
        self.next_reference_button.clicked.connect(
            lambda: self.move_reference_history(1)
        )
        toolbar.addWidget(
            self.next_reference_button
        )

        self._update_reference_history_controls()

        toolbar.addSeparator()

        self.prev_verse_button = QToolButton()
        self.prev_verse_button.setText("▲")
        self.prev_verse_button.setToolTip(
            "Versículo anterior"
        )
        self.prev_verse_button.setStyleSheet(
            GREEN_BUTTON_STYLE
        )
        self._configure_icon_button(
            self.prev_verse_button
        )
        self.prev_verse_button.clicked.connect(
            lambda: self.move_verse(-1)
        )
        toolbar.addWidget(
            self.prev_verse_button
        )

        self.next_verse_button = QToolButton()
        self.next_verse_button.setText("▼")
        self.next_verse_button.setToolTip(
            "Versículo siguiente"
        )
        self.next_verse_button.setStyleSheet(
            GREEN_BUTTON_STYLE
        )
        self._configure_icon_button(
            self.next_verse_button
        )
        self.next_verse_button.clicked.connect(
            lambda: self.move_verse(1)
        )
        toolbar.addWidget(
            self.next_verse_button
        )

        self._update_nav_buttons()

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("Archivo")

        open_action = QAction(
            "Abrir proyecto…",
            self,
        )
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(
            self.open_project
        )
        file_menu.addAction(open_action)

        self.recent_projects_menu = file_menu.addMenu(
            "Proyectos recientes"
        )
        self._refresh_recent_projects_menu()

        file_menu.addSeparator()

        import_file_action = QAction(
            "Importar notas desde XML…",
            self,
        )
        import_file_action.triggered.connect(
            self.import_notes_from_file
        )
        file_menu.addAction(import_file_action)

        import_clipboard_action = QAction(
            "Importar notas desde portapapeles",
            self,
        )
        import_clipboard_action.setShortcut("Ctrl+Shift+V")
        import_clipboard_action.triggered.connect(
            self.import_notes_from_clipboard
        )
        file_menu.addAction(import_clipboard_action)

        file_menu.addSeparator()

        backup_notes_action = QAction(
            "Crear backup de mis notas ahora…",
            self,
        )
        backup_notes_action.setToolTip(
            "Crea una copia manual de Notes_<consultor>.xml "
            "sin modificar el archivo de trabajo."
        )
        backup_notes_action.triggered.connect(
            self.create_manual_notes_backup
        )
        file_menu.addAction(
            backup_notes_action
        )

        config_menu = self.menuBar().addMenu(
            "Configuración"
        )
        consultant_action = QAction(
            "Usuario consultor…",
            self,
        )
        consultant_action.triggered.connect(
            self.choose_consultant
        )
        config_menu.addAction(consultant_action)

        clear_chatgpt_action = QAction(
            "Borrar cookies de ChatGPT en este panel…",
            self,
        )
        clear_chatgpt_action.setToolTip(
            "Borra las cookies guardadas solamente del navegador "
            "ChatGPT integrado."
        )
        clear_chatgpt_action.triggered.connect(
            self.clear_chatgpt_session
        )
        config_menu.addAction(clear_chatgpt_action)

        tools_menu = self.menuBar().addMenu(
            "Herramientas"
        )

        note_tools_action = (
            self.note_tools_dock.toggleViewAction()
        )
        note_tools_action.setText(
            "Buscar y editar notas…"
        )
        note_tools_action.setToolTip(
            "Abrir el panel lateral para búsquedas, expresiones regulares "
            "y ediciones masivas de notas."
        )
        tools_menu.addAction(
            note_tools_action
        )

        resources_menu = self.menuBar().addMenu(
            "Recursos"
        )

        resource_toggle_action = (
            self.resources_dock.toggleViewAction()
        )
        resource_toggle_action.setText(
            "Mostrar / ocultar Recursos bíblicos"
        )
        resources_menu.addAction(
            resource_toggle_action
        )

        resource_float_action = QAction(
            "Acoplar / hacer flotante",
            self,
        )
        resource_float_action.triggered.connect(
            self._toggle_resources_floating
        )
        resources_menu.addAction(
            resource_float_action
        )

        resource_screen_action = QAction(
            "Mover Recursos a otra pantalla",
            self,
        )
        resource_screen_action.triggered.connect(
            self._move_resources_to_next_screen
        )
        resources_menu.addAction(
            resource_screen_action
        )

        resources_menu.addSeparator()

        resource_new_window_action = QAction(
            "Nueva ventana de recurso",
            self,
        )
        resource_new_window_action.triggered.connect(
            self._new_resource_window
        )
        resources_menu.addAction(
            resource_new_window_action
        )

        resources_menu.addSeparator()

        install_nt_resource_action = QAction(
            "Instalar / actualizar recursos NT",
            self,
        )
        install_nt_resource_action.triggered.connect(
            self.resources_panel.install_nt
        )
        resources_menu.addAction(
            install_nt_resource_action
        )

        install_all_resource_action = QAction(
            "Instalar / actualizar todos los recursos",
            self,
        )
        install_all_resource_action.triggered.connect(
            self.resources_panel.install_all
        )
        resources_menu.addAction(
            install_all_resource_action
        )

        install_extra_resource_action = QAction(
            "Instalar / actualizar Temas y Lugares",
            self,
        )
        install_extra_resource_action.triggered.connect(
            self.resources_panel.install_extras
        )
        resources_menu.addAction(
            install_extra_resource_action
        )

        local_resource_action = QAction(
            "Importar notas privadas JSON…",
            self,
        )
        local_resource_action.triggered.connect(
            lambda:
                self.resources_panel.choose_local_folder(
                    self
                )
        )
        resources_menu.addAction(
            local_resource_action
        )

        view_menu = self.menuBar().addMenu("Ver")
        view_menu.addAction(
            self.bible_dock.toggleViewAction()
        )
        view_menu.addAction(
            self.notes_dock.toggleViewAction()
        )
        view_menu.addAction(
            self.chatgpt_dock.toggleViewAction()
        )
        reset_action = QAction(
            "Restablecer distribución",
            self,
        )
        reset_action.triggered.connect(
            self.reset_layout
        )
        view_menu.addSeparator()
        view_menu.addAction(reset_action)

    # ------------------------------------------------------------------
    # Proyectos recientes y restauración de sesión
    # ------------------------------------------------------------------
    def _project_settings_key(
        self,
        project_path: str | Path,
    ) -> str:
        normalized = str(
            Path(project_path).expanduser().resolve()
        )
        digest = hashlib.sha1(
            normalized.encode("utf-8")
        ).hexdigest()
        return f"projects/{digest}"

    def _recent_project_paths(self) -> list[str]:
        value = self.settings.value(
            "recent_projects",
            [],
        )

        if isinstance(value, str):
            paths = [value]
        elif value is None:
            paths = []
        else:
            paths = list(value)

        cleaned = []
        seen = set()
        for path in paths:
            text = str(path).strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)

        return cleaned[:5]

    def _add_recent_project(
        self,
        project_path: str | Path,
    ):
        path = str(
            Path(project_path).expanduser().resolve()
        )

        current = [
            item
            for item in self._recent_project_paths()
            if Path(item) != Path(path)
        ]
        current.insert(0, path)
        current = current[:5]

        self.settings.setValue(
            "recent_projects",
            current,
        )
        self._refresh_recent_projects_menu()

    def _refresh_recent_projects_menu(self):
        if self.recent_projects_menu is None:
            return

        self.recent_projects_menu.clear()
        paths = self._recent_project_paths()

        if not paths:
            empty_action = QAction(
                "Sin proyectos recientes",
                self,
            )
            empty_action.setEnabled(False)
            self.recent_projects_menu.addAction(
                empty_action
            )
            return

        for index, path in enumerate(
            paths,
            start=1,
        ):
            folder = Path(path)
            label = (
                f"{index}. {folder.name}"
                if folder.name
                else f"{index}. {path}"
            )

            if not folder.exists():
                label += "  (no disponible)"

            action = QAction(
                label,
                self,
            )
            action.setToolTip(path)
            action.setEnabled(
                folder.exists()
            )
            action.triggered.connect(
                lambda checked=False, p=path:
                    self._open_project_path(p)
            )
            self.recent_projects_menu.addAction(
                action
            )

    def _save_project_session(self):
        if (
            self._restoring_project_session
            or not self.project
        ):
            return

        base = self._project_settings_key(
            self.project.folder
        )

        self.settings.setValue(
            f"{base}/path",
            str(self.project.folder),
        )

        current_text_path = ""
        if self.current_text is not None:
            current_text_path = str(
                self.current_text.path
            )

        self.settings.setValue(
            f"{base}/text_path",
            current_text_path,
        )
        self.settings.setValue(
            f"{base}/chapter",
            self.current_chapter or "",
        )
        self.settings.setValue(
            f"{base}/reference",
            self.current_reference or "",
        )
        self.settings.setValue(
            f"{base}/verse_position",
            int(self.current_verse_position),
        )
        self.settings.setValue(
            f"{base}/reference_history",
            list(self.reference_history),
        )
        self.settings.setValue(
            f"{base}/reference_history_index",
            int(self.reference_history_index),
        )
        self.settings.setValue(
            f"{base}/bible_source_index",
            int(self.source_combo.currentIndex()),
        )

        # saveState conserva posición/tamaño/visibilidad de docks.
        self.settings.setValue(
            f"{base}/window_state",
            self.saveState(),
        )
        self.settings.setValue(
            f"{base}/geometry",
            self.saveGeometry(),
        )

        self.settings.sync()

    def _restore_project_session(
        self,
        project_path: str | Path,
    ):
        if not self.project:
            return

        base = self._project_settings_key(
            project_path
        )

        saved_text_path = str(
            self.settings.value(
                f"{base}/text_path",
                "",
            )
            or ""
        )
        saved_chapter = str(
            self.settings.value(
                f"{base}/chapter",
                "",
            )
            or ""
        )
        saved_reference = str(
            self.settings.value(
                f"{base}/reference",
                "",
            )
            or ""
        )

        raw_history = self.settings.value(
            f"{base}/reference_history",
            [],
        )
        if isinstance(
            raw_history,
            str,
        ):
            raw_history = [
                raw_history
            ] if raw_history else []

        saved_history = []
        for value in (
            raw_history
            if isinstance(raw_history, (list, tuple))
            else []
        ):
            normalized = normalize_verse_ref(
                str(value or "")
            )
            if normalized:
                saved_history.append(
                    normalized
                )

        try:
            saved_history_index = int(
                self.settings.value(
                    f"{base}/reference_history_index",
                    len(saved_history) - 1,
                )
            )
        except (TypeError, ValueError):
            saved_history_index = (
                len(saved_history) - 1
            )

        self.reference_history = (
            saved_history[-40:]
        )
        if self.reference_history:
            self.reference_history_index = max(
                0,
                min(
                    saved_history_index,
                    len(self.reference_history) - 1,
                ),
            )
        else:
            self.reference_history_index = -1

        try:
            saved_position = int(
                self.settings.value(
                    f"{base}/verse_position",
                    -1,
                )
            )
        except (TypeError, ValueError):
            saved_position = -1

        try:
            source_index = int(
                self.settings.value(
                    f"{base}/bible_source_index",
                    self.source_combo.currentIndex(),
                )
            )
        except (TypeError, ValueError):
            source_index = (
                self.source_combo.currentIndex()
            )

        # Libro/texto.
        text_index = 0
        if saved_text_path:
            for index in range(
                self.text_combo.count()
            ):
                item = self.text_combo.itemData(
                    index
                )
                if (
                    item
                    and str(item.path)
                    == saved_text_path
                ):
                    text_index = index
                    break

        if self.text_combo.count():
            self.text_combo.blockSignals(
                True
            )
            self.text_combo.setCurrentIndex(
                text_index
            )
            self.text_combo.blockSignals(
                False
            )
            self._text_changed(
                text_index
            )

        # Capítulo.
        if saved_chapter:
            chapter_index = (
                self.chapter_combo.findData(
                    saved_chapter
                )
            )
            if chapter_index >= 0:
                self.chapter_combo.blockSignals(
                    True
                )
                self.chapter_combo.setCurrentIndex(
                    chapter_index
                )
                self.chapter_combo.blockSignals(
                    False
                )
                self._load_chapter(
                    saved_chapter
                )

        # Versículo: primero por referencia, después por posición.
        restored_verse = False
        if saved_reference:
            normalized_saved = (
                normalize_verse_ref(
                    saved_reference
                )
            )
            for position, row in enumerate(
                self.verse_rows
            ):
                item = self.verse_table.item(
                    row,
                    0,
                )
                if not item:
                    continue
                row_reference = item.data(
                    Qt.UserRole
                )
                if (
                    row_reference
                    and normalize_verse_ref(
                        row_reference
                    )
                    == normalized_saved
                ):
                    self._select_verse_position(
                        position
                    )
                    restored_verse = True
                    break

        if (
            not restored_verse
            and 0 <= saved_position < len(
                self.verse_rows
            )
        ):
            self._select_verse_position(
                saved_position
            )

        if (
            0 <= source_index
            < self.source_combo.count()
        ):
            self.source_combo.setCurrentIndex(
                source_index
            )

        window_state = self.settings.value(
            f"{base}/window_state"
        )
        geometry = self.settings.value(
            f"{base}/geometry"
        )

        if geometry is not None:
            self.restoreGeometry(
                geometry
            )
        if window_state is not None:
            self.restoreState(
                window_state
            )

        if (
            not self.reference_history
            and self.current_reference
        ):
            self.reference_history = [
                normalize_verse_ref(
                    self.current_reference
                )
            ]
            self.reference_history_index = 0

        self._update_reference_history_controls()

    def _restore_last_project(self):
        path = str(
            self.settings.value(
                "last_project_path",
                "",
            )
            or ""
        )
        if not path:
            return

        folder = Path(path)
        if not folder.exists():
            return

        self._open_project_path(
            folder,
            quiet=True,
        )

    # ------------------------------------------------------------------
    # Backup manual de las notas del consultor
    # ------------------------------------------------------------------
    def create_manual_notes_backup(self):
        if (
            not self.notes_workspace
            or not self.consultant_name
        ):
            QMessageBox.information(
                self,
                "Backup de notas",
                "Abra primero un proyecto y configure el usuario consultor.",
            )
            return

        document = (
            self.notes_workspace.consultant_document()
        )
        if document is None:
            QMessageBox.warning(
                self,
                "Backup de notas",
                "No encontré el archivo Notes_*.xml del consultor actual.",
            )
            return

        source = Path(document.path)
        if not source.exists():
            QMessageBox.warning(
                self,
                "Backup de notas",
                "El archivo de notas del consultor ya no existe en disco.",
            )
            return

        backup_dir = (
            source.parent
            / ".consultor_backups"
            / "manual"
        )
        backup_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        stamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        destination = (
            backup_dir
            / f"{source.stem}_MANUAL_{stamp}{source.suffix}"
        )

        try:
            shutil.copy2(
                source,
                destination,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Backup de notas",
                f"No fue posible crear el backup:\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Backup de notas",
            "Backup creado correctamente.\n\n"
            f"{destination}",
        )

    # ------------------------------------------------------------------
    # Importación de notas generadas externamente / ChatGPT
    # ------------------------------------------------------------------
    def import_notes_from_file(self):
        if not self._can_import_notes():
            return

        start = self.settings.value(
            "last_import_notes_dir",
            str(self.project.folder if self.project else Path.home()),
        )

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar notas XML",
            start,
            "Archivos XML (*.xml);;Todos los archivos (*)",
        )
        if not path:
            return

        self.settings.setValue(
            "last_import_notes_dir",
            str(Path(path).parent),
        )

        try:
            preview = parse_comment_file(path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Importar notas",
                str(exc),
            )
            return

        self._run_notes_import(
            preview,
            source_label=Path(path).name,
        )

    def import_notes_from_clipboard(self):
        if not self._can_import_notes():
            return

        xml_text = QApplication.clipboard().text()
        if not xml_text.strip():
            QMessageBox.warning(
                self,
                "Importar desde portapapeles",
                "El portapapeles no contiene texto.",
            )
            return

        try:
            preview = parse_comment_xml(
                xml_text
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Importar desde portapapeles",
                "No fue posible interpretar el XML copiado.\n\n"
                f"{exc}\n\n"
                "Si viene de ChatGPT, use el botón «Copiar» del bloque "
                "de código XML o copie desde <CommentList> hasta "
                "</CommentList>.",
            )
            return

        self._run_notes_import(
            preview,
            source_label="portapapeles",
        )

    def _can_import_notes(self) -> bool:
        if not self.project:
            QMessageBox.information(
                self,
                "Importar notas",
                "Primero abra la carpeta del proyecto.",
            )
            return False

        if not self.notes_workspace:
            QMessageBox.warning(
                self,
                "Importar notas",
                "No está disponible el archivo Notes_*.xml del consultor. "
                "Revise Configuración > Usuario consultor.",
            )
            return False

        if self.notes_workspace.consultant_document() is None:
            QMessageBox.warning(
                self,
                "Importar notas",
                "No encontré el archivo de notas del consultor actual.",
            )
            return False

        return True

    def _project_reference_set(self) -> set[str]:
        refs = set()
        if not self.project:
            return refs

        for project_text in self.project.texts:
            for verse in project_text.document.verses:
                refs.add(
                    normalize_verse_ref(
                        verse.reference
                    )
                )
        return refs

    def _run_notes_import(
        self,
        preview,
        source_label: str,
    ):
        if not self.notes_workspace:
            return

        people = self.notes_workspace.all_people()
        project_refs = self._project_reference_set()

        dialog = ImportNotesDialog(
            preview=preview,
            consultant_name=self.consultant_name,
            people=people,
            project_refs=project_refs,
            parent=self,
        )

        if not dialog.exec():
            return

        destination = (
            self.notes_workspace.consultant_document()
        )
        if destination is None:
            return

        existing_threads = set(
            self.notes_workspace.thread_index.keys()
        )

        force_user = (
            self.consultant_name
            if dialog.force_user
            else None
        )

        try:
            result = import_comments(
                destination_document=destination,
                preview=preview,
                existing_thread_ids=existing_threads,
                override_target=dialog.override_target,
                force_user=force_user,
                skip_duplicates=dialog.skip_duplicates,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Importar notas",
                f"No fue posible importar las notas:\n{exc}",
            )
            return

        # Recargar todos los Notes_*.xml para que la conversación entre
        # archivos se reconstruya con los nuevos Thread.
        self.notes_workspace.reload()
        self._after_internal_file_write()

        if self.current_reference:
            self._refresh_threads_for_reference()

        target_text = (
            "se conservaron los destinatarios del XML"
            if dialog.override_target is None
            else f"se dirigieron a {dialog.override_target}"
        )

        message = (
            f"Fuente: {source_label}\n\n"
            f"Notas importadas: {result.imported}\n"
            f"Duplicados omitidos: {result.skipped_duplicates}\n"
            f"Destino: Notes_{self.consultant_name}.xml\n"
            f"Destinatario: {target_text}.\n\n"
            "Se creó una copia de seguridad antes de modificar el XML."
        )

        if result.imported_refs:
            message += (
                "\n\nPrimeras referencias: "
                + ", ".join(result.imported_refs[:5])
            )
            if len(result.imported_refs) > 5:
                message += ", …"

        QMessageBox.information(
            self,
            "Importación terminada",
            message,
        )

    # ------------------------------------------------------------------
    # Copiar rango SFM al portapapeles
    # ------------------------------------------------------------------
    def _current_chapter_verses(self):
        if not self.current_text or not self.current_chapter:
            return []

        return [
            verse
            for verse in self.current_text.document.verses
            if verse.chapter == self.current_chapter
        ]

    def copy_sfm_range_to_clipboard(self):
        verses = self._current_chapter_verses()

        if not verses:
            QMessageBox.information(
                self,
                "Copiar SFM",
                "No hay un capítulo activo para copiar.",
            )
            return

        current_position = self.current_verse_position
        if current_position < 0:
            current_position = 0

        dialog = CopySfmRangeDialog(
            verses=verses,
            current_position=current_position,
            parent=self,
        )

        if not dialog.exec():
            return

        sfm_text = build_sfm_range(
            verses,
            dialog.start_index,
            dialog.end_index,
        )

        if not sfm_text:
            QMessageBox.warning(
                self,
                "Copiar SFM",
                "No se generó contenido para el rango seleccionado.",
            )
            return

        QApplication.clipboard().setText(
            sfm_text
        )

        start_verse = verses[
            min(dialog.start_index, dialog.end_index)
        ].verse
        end_verse = verses[
            max(dialog.start_index, dialog.end_index)
        ].verse

        self.statusBar().showMessage(
            f"Copiado al portapapeles: capítulo {self.current_chapter}, "
            f"versículos {start_verse}–{end_verse} "
            "(solo marcadores \\\\s y \\\\v).",
            5000,
        )

    # ------------------------------------------------------------------
    # Detección de cambios externos en SFM / Notes XML
    # ------------------------------------------------------------------
    def _file_stamp(
        self,
        path: str | Path,
    ):
        path = Path(path)
        try:
            stat = path.stat()
        except OSError:
            return None

        return (
            stat.st_mtime_ns,
            stat.st_size,
        )

    def _project_watch_paths(self):
        if not self.project:
            return []

        paths = [
            item.path
            for item in self.project.texts
        ]
        paths.extend(
            item.path
            for item in self.project.notes_files
        )

        unique = []
        seen = set()

        for path in paths:
            resolved = str(
                Path(path).resolve()
            )
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(
                resolved
            )

        return unique

    def _configure_project_file_watcher(self):
        current = list(
            self.file_watcher.files()
        )
        if current:
            self.file_watcher.removePaths(
                current
            )

        self._watched_file_stamps = {}
        self._pending_external_changes.clear()
        self.external_change_bar.hide()

        paths = [
            path
            for path in self._project_watch_paths()
            if Path(path).exists()
        ]

        if paths:
            self.file_watcher.addPaths(
                paths
            )

        for path in paths:
            self._watched_file_stamps[
                path
            ] = self._file_stamp(
                path
            )

    def _refresh_file_watcher_stamps(self):
        if not self.project:
            return

        paths = self._project_watch_paths()
        currently_watched = set(
            self.file_watcher.files()
        )

        for path in paths:
            if (
                Path(path).exists()
                and path not in currently_watched
            ):
                self.file_watcher.addPath(
                    path
                )

            self._watched_file_stamps[
                path
            ] = self._file_stamp(
                path
            )

    def _project_file_changed(
        self,
        path: str,
    ):
        # Algunos editores reemplazan el archivo en lugar de modificarlo;
        # esperar unos milisegundos permite que termine la escritura.
        QTimer.singleShot(
            350,
            lambda p=path:
                self._process_project_file_change(
                    p
                ),
        )

    def _process_project_file_change(
        self,
        path: str,
    ):
        resolved = str(
            Path(path).resolve()
        )

        if Path(resolved).exists():
            if (
                resolved
                not in self.file_watcher.files()
            ):
                self.file_watcher.addPath(
                    resolved
                )

        new_stamp = self._file_stamp(
            resolved
        )
        old_stamp = (
            self._watched_file_stamps.get(
                resolved
            )
        )

        # Si una escritura fue realizada por Consultor App, sus operaciones
        # actualizan el stamp antes de que llegue esta señal.
        if (
            new_stamp is not None
            and new_stamp == old_stamp
        ):
            return

        self._pending_external_changes.add(
            resolved
        )

        names = sorted(
            {
                Path(item).name
                for item in self._pending_external_changes
            }
        )

        if len(names) <= 2:
            description = ", ".join(
                names
            )
        else:
            description = (
                ", ".join(names[:2])
                + f" y {len(names) - 2} archivo(s) más"
            )

        self.external_change_label.setText(
            "Cambios externos detectados: "
            f"{description}. "
            "Recargue para trabajar con la versión actual."
        )
        self.external_change_bar.show()

    def _dismiss_external_change_notice(self):
        for path in list(
            self._pending_external_changes
        ):
            self._watched_file_stamps[
                path
            ] = self._file_stamp(
                path
            )

        self._pending_external_changes.clear()
        self.external_change_bar.hide()

    def _reload_external_changes(self):
        if not self.project:
            return

        note_dirty = bool(
            self.note_editor.document().isModified()
        )
        reply_dirty = bool(
            self.reply_editor.document().isModified()
        )

        if note_dirty or reply_dirty:
            answer = QMessageBox.question(
                self,
                "Recargar cambios externos",
                "Hay texto editado que todavía no se ha guardado. "
                "Recargar descartará esos cambios locales.\n\n"
                "¿Desea continuar?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        folder = self.project.folder

        self._pending_external_changes.clear()
        self.external_change_bar.hide()

        self._save_project_session()
        self._open_project_path(
            folder,
            quiet=True,
        )

        self.statusBar().showMessage(
            "Archivos externos recargados.",
            4000,
        )

    def _after_internal_file_write(self):
        # Evita que QFileSystemWatcher presente como externo un cambio que
        # acabamos de hacer nosotros mismos.
        self._refresh_file_watcher_stamps()

    # ------------------------------------------------------------------
    # Proyecto
    # ------------------------------------------------------------------
    def open_project(self):
        start = self.settings.value(
            "last_project_dir",
            str(Path.home()),
        )
        folder = QFileDialog.getExistingDirectory(
            self,
            "Abrir carpeta de proyecto",
            start,
        )
        if not folder:
            return

        self._open_project_path(
            folder
        )

    def _open_project_path(
        self,
        folder: str | Path,
        quiet: bool = False,
    ):
        folder = Path(folder).expanduser()

        if not folder.exists():
            if not quiet:
                QMessageBox.warning(
                    self,
                    "Proyecto",
                    f"La carpeta ya no existe:\n{folder}",
                )
            return

        # Guardar el punto exacto del proyecto anterior antes de cambiar.
        self._save_project_session()

        self._restoring_project_session = True
        try:
            try:
                project = load_project(
                    folder
                )
            except Exception as exc:
                if not quiet:
                    QMessageBox.critical(
                        self,
                        "Proyecto",
                        str(exc),
                    )
                return

            self.project = project
            self.spell_manager.set_project_key(
                str(folder)
            )
            self._refresh_spellcheck_controls()

            self.reference_history = []
            self.reference_history_index = -1
            self._update_reference_history_controls()

            self.settings.setValue(
                "last_project_dir",
                str(folder),
            )
            self.settings.setValue(
                "last_project_path",
                str(folder),
            )
            self._add_recent_project(
                folder
            )

            self._ensure_consultant_identity()
            self._build_notes_workspace()
            self._populate_texts()

            self._restore_project_session(
                folder
            )

        finally:
            self._restoring_project_session = False

        self._configure_project_file_watcher()
        self._save_project_session()

        self.statusBar().showMessage(
            f"Proyecto abierto: "
            f"{len(self.project.texts)} texto(s), "
            f"{len(self.project.notes_files)} archivo(s) de notas.",
            5000,
        )

    def _populate_texts(self):
        self.text_combo.blockSignals(True)
        self.text_combo.clear()

        if self.project:
            for item in self.project.texts:
                # ProjectText.label usa \mt cuando existe.
                self.text_combo.addItem(
                    item.label,
                    item,
                )

        self.text_combo.blockSignals(False)

        if self.text_combo.count():
            self.text_combo.setCurrentIndex(0)
            self._text_changed(0)
        else:
            self.current_text = None
            self.verse_table.setRowCount(0)
            self.chapter_combo.clear()
            self.project_title.setText(
                self.project.folder.name
                if self.project
                else "Sin texto SFM"
            )

    def _text_changed(self, index):
        if index < 0:
            return

        item = self.text_combo.itemData(index)
        if item is None:
            return

        self.current_text = item

        chapters = sorted(
            {v.chapter for v in item.document.verses},
            key=lambda x: int(x) if x.isdigit() else x,
        )

        self.chapter_combo.blockSignals(True)
        self.chapter_combo.clear()
        for chapter in chapters:
            self.chapter_combo.addItem(
                f"Cap. {chapter}",
                chapter,
            )
        self.chapter_combo.blockSignals(False)

        if chapters:
            self.chapter_combo.setCurrentIndex(0)
            self._load_chapter(chapters[0])

        self._save_project_session()

    def _chapter_changed(self, index):
        if index < 0:
            return

        chapter = self.chapter_combo.itemData(index)
        if chapter is not None:
            self._load_chapter(str(chapter))

        if (
            hasattr(self, "note_tools_dock")
            and self.note_tools_dock.isVisible()
            and self.note_tools_scope_combo.currentData()
            == "chapter"
        ):
            self._clear_note_tool_results(
                self._note_tools_scope_description()
            )

        self._save_project_session()

    def _make_nonselectable(self, item: QTableWidgetItem):
        item.setFlags(
            item.flags()
            & ~Qt.ItemIsSelectable
        )

    def _consultant_note_summary(
        self,
        reference: str,
    ) -> dict:
        summary = {
            "total": 0,
            "pending": 0,
            "replied": 0,
            "resolved": 0,
        }

        if not self.notes_workspace:
            return summary

        ref = normalize_verse_ref(reference)
        if not ref:
            return summary

        threads = self.notes_workspace.threads_for_reference(
            ref,
            include_resolved=True,
        )

        for thread in threads:
            summary["total"] += 1

            if thread.resolved_for_consultant():
                summary["resolved"] += 1
            elif thread.has_reply_from_counterpart():
                summary["replied"] += 1
            else:
                summary["pending"] += 1

        return summary

    def _refresh_note_markers(self):
        if not hasattr(self, "note_reference_by_row"):
            return

        for row, reference in self.note_reference_by_row.items():
            item = self.verse_table.item(
                row,
                0,
            )
            if item is None:
                continue

            base = self.note_base_label_by_row.get(
                row,
                "",
            )
            summary = self._consultant_note_summary(
                reference
            )

            total = summary["total"]
            if total:
                marker = (
                    "🚩"
                    if total == 1
                    else f"🚩{total}"
                )

                if base:
                    item.setText(
                        f"{base}  {marker}"
                    )
                else:
                    item.setText(marker)

                item.setToolTip(
                    f"{total} nota(s) del consultor\n"
                    f"Pendientes: {summary['pending']}\n"
                    f"Con respuesta: {summary['replied']}\n"
                    f"Resueltas: {summary['resolved']}"
                )

                font = QFont(item.font())
                font.setBold(True)
                item.setFont(font)
            else:
                item.setText(base)
                item.setToolTip("")

    def _load_chapter(self, chapter):
        if not self.current_text:
            return

        self.current_chapter = str(chapter)
        document = self.current_text.document

        self.project_title.setText(
            f"{document.title} — capítulo {self.current_chapter}"
        )

        verses = [
            v
            for v in document.verses
            if v.chapter == self.current_chapter
        ]

        self.verse_table.blockSignals(True)
        self.verse_table.clearSpans()
        self.verse_table.setRowCount(0)

        self.verse_rows = []
        self.anchor_widgets_by_row = {}
        self.note_reference_by_row = {}
        self.note_base_label_by_row = {}
        self.current_anchor_widget = None

        for verse in verses:
            # \s / \s1 / \s2: visibles en negrilla, seleccionables y
            # con una columna independiente para el indicador de notas.
            for index, subtitle in enumerate(verse.subtitles):
                row = self.verse_table.rowCount()
                self.verse_table.insertRow(row)

                marker_item = QTableWidgetItem("")
                marker_item.setTextAlignment(
                    Qt.AlignCenter
                )
                self._make_nonselectable(marker_item)
                self.verse_table.setItem(
                    row,
                    0,
                    marker_item,
                )

                if index < len(verse.subtitle_anchors):
                    target = verse.subtitle_anchors[index]
                else:
                    target = None

                if target is not None:
                    self.note_reference_by_row[row] = (
                        normalize_verse_ref(
                            target.reference
                        )
                    )
                    self.note_base_label_by_row[row] = ""

                    heading_widget = AnchorTextEdit(
                        target,
                        heading=True,
                    )
                    heading_widget.activated.connect(
                        lambda widget, r=row:
                            self._anchor_widget_activated(widget, r)
                    )
                    heading_widget.note_requested.connect(
                        self.begin_new_note
                    )
                    self.verse_table.setCellWidget(
                        row,
                        1,
                        heading_widget,
                    )
                    self.anchor_widgets_by_row[row] = heading_widget
                else:
                    heading = QTableWidgetItem(subtitle)
                    font = QFont(heading.font())
                    font.setBold(True)
                    font.setPointSize(
                        max(font.pointSize(), 11)
                    )
                    heading.setFont(font)
                    self._make_nonselectable(heading)
                    self.verse_table.setItem(
                        row,
                        1,
                        heading,
                    )

            # Versículo principal.
            row = self.verse_table.rowCount()
            self.verse_table.insertRow(row)
            self.verse_rows.append(row)

            num = QTableWidgetItem(verse.verse)
            num.setData(
                Qt.UserRole,
                verse.reference,
            )
            num_font = QFont(num.font())
            num_font.setBold(True)
            num.setFont(num_font)

            self.verse_table.setItem(
                row,
                0,
                num,
            )
            self.note_reference_by_row[row] = (
                normalize_verse_ref(
                    verse.reference
                )
            )
            self.note_base_label_by_row[row] = (
                verse.verse
            )

            if verse.anchor is not None:
                verse_widget = AnchorTextEdit(
                    verse.anchor,
                    heading=False,
                )
                verse_widget.activated.connect(
                    lambda widget, r=row:
                        self._anchor_widget_activated(widget, r)
                )
                verse_widget.note_requested.connect(
                    self.begin_new_note
                )
                self.verse_table.setCellWidget(
                    row,
                    1,
                    verse_widget,
                )
                self.anchor_widgets_by_row[row] = verse_widget
            else:
                self.verse_table.setItem(
                    row,
                    1,
                    QTableWidgetItem(verse.text),
                )

            # \ft: se muestran visualmente como nota al pie. No forman parte
            # del texto principal seleccionado para la nota.
            for footnote in verse.footnotes:
                foot_row = self.verse_table.rowCount()
                self.verse_table.insertRow(foot_row)

                foot_text = (
                    footnote.text
                    or "(nota sin texto \\ft)"
                )
                foot = QTableWidgetItem(
                    f"[{footnote.number}] Nota al pie: {foot_text}"
                )
                foot_font = QFont(foot.font())
                foot_font.setItalic(True)
                if foot_font.pointSize() > 8:
                    foot_font.setPointSize(
                        foot_font.pointSize() - 1
                    )
                foot.setFont(foot_font)
                self._make_nonselectable(foot)

                self.verse_table.setItem(
                    foot_row,
                    0,
                    foot,
                )
                self.verse_table.setSpan(
                    foot_row,
                    0,
                    1,
                    2,
                )

        self.verse_table.blockSignals(False)

        self._refresh_note_markers()

        QTimer.singleShot(
            0,
            self._resize_anchor_rows,
        )
        QTimer.singleShot(
            150,
            self._resize_anchor_rows,
        )

        if self.verse_rows:
            self._select_verse_position(0)
        else:
            self.current_reference = ""
            self.current_verse_position = -1
            self._refresh_threads_for_reference()

        self._update_nav_buttons()

    def _resize_anchor_rows(self):
        if not hasattr(self, "anchor_widgets_by_row"):
            return

        for row, widget in self.anchor_widgets_by_row.items():
            width = (
                self.verse_table.columnWidth(1)
                - 8
            )

            height = widget.ideal_height(width)
            widget.setFixedHeight(height)
            self.verse_table.setRowHeight(
                row,
                height + 4,
            )

        self.verse_table.resizeRowsToContents()

    def _clear_note_anchor_highlights(self):
        for widget in getattr(
            self,
            "anchor_widgets_by_row",
            {},
        ).values():
            try:
                widget.clear_note_highlight()
            except Exception:
                pass

    def _find_anchor_widget_for_message(
        self,
        msg,
    ):
        if msg is None:
            return (
                None,
                None,
            )

        reference = normalize_verse_ref(
            msg.verse_ref
        )
        selected = (
            msg.selected_text
            or ""
        ).strip()
        raw_position = int(
            getattr(
                msg,
                "start_position",
                0,
            )
            or 0
        )

        candidates = []

        for row, widget in self.anchor_widgets_by_row.items():
            target = widget.anchor_target
            if (
                normalize_verse_ref(
                    target.reference
                )
                != reference
            ):
                continue

            score = 0

            if (
                selected
                and selected in (
                    target.visible_text
                    or ""
                )
            ):
                score += 100

            if (
                selected
                and selected in (
                    target.source_text
                    or ""
                )
            ):
                score += 60

            if (
                0
                <= raw_position
                <= len(
                    target.source_text
                    or ""
                )
            ):
                score += 20

                if selected:
                    fragment = (
                        target.source_text[
                            raw_position:
                            raw_position
                            + len(selected)
                        ]
                    )
                    if (
                        fragment.casefold()
                        == selected.casefold()
                    ):
                        score += 120

            if (
                msg.verse_text
                and target.source_text
                == msg.verse_text
            ):
                score += 150

            candidates.append(
                (
                    score,
                    row,
                    widget,
                )
            )

        if not candidates:
            return (
                None,
                None,
            )

        candidates.sort(
            key=lambda item: (
                item[0],
                -item[1],
            ),
            reverse=True,
        )

        _score, row, widget = (
            candidates[0]
        )
        return (
            row,
            widget,
        )

    def _highlight_note_anchor(
        self,
        msg,
    ):
        self._clear_note_anchor_highlights()

        row, widget = (
            self._find_anchor_widget_for_message(
                msg
            )
        )
        if widget is None:
            return

        _start, _end, match_mode = widget.highlight_note(
            msg.selected_text,
            getattr(
                msg,
                "start_position",
                0,
            ),
        )

        item = self.verse_table.item(
            row,
            0,
        )
        if item is not None:
            self.verse_table.scrollToItem(
                item,
                QAbstractItemView.PositionAtCenter,
            )

        selected = (
            msg.selected_text
            or ""
        ).strip()
        if selected:
            if match_mode == "exact":
                self.selection_status_label.setText(
                    "Anclaje de la nota resaltado: "
                    f"«{selected}»"
                )
            else:
                self.selection_status_label.setText(
                    "El texto seleccionado originalmente cambió; "
                    "se muestra la posición histórica aproximada de la nota."
                )
        else:
            self.selection_status_label.setText(
                "Anclaje puntual de la nota resaltado "
                f"en StartPosition {getattr(msg, 'start_position', 0)}."
            )

    def _anchor_widget_activated(
        self,
        widget: AnchorTextEdit,
        row: int,
    ):
        self._clear_note_anchor_highlights()
        self.current_anchor_widget = widget
        metadata = widget.selection_metadata()

        selected = metadata.get("SelectedText", "")
        position = metadata.get("StartPosition", 0)
        kind = (
            "subtítulo"
            if metadata.get("Kind") == "section"
            else "versículo"
        )

        if selected:
            preview = selected.replace("\n", " ")
            if len(preview) > 80:
                preview = preview[:77] + "…"
            self.selection_status_label.setText(
                f"Anclaje de nota: {kind} · "
                f"«{preview}» · posición SFM {position}"
            )
        else:
            self.selection_status_label.setText(
                f"Anclaje de nota: {kind} · "
                f"punto en posición SFM {position}"
            )

        self.new_note_button.setEnabled(
            bool(self.notes_workspace)
        )

        reference = normalize_verse_ref(
            metadata.get("VerseRef", "")
        )
        previous_reference = self.current_reference

        if row in self.verse_rows:
            try:
                self.current_verse_position = (
                    self.verse_rows.index(row)
                )
            except ValueError:
                pass

            self.verse_table.blockSignals(True)
            self.verse_table.selectRow(row)
            self.verse_table.blockSignals(False)

        self._update_nav_buttons()

        # Mover el cursor o ampliar una selección no debe recargar
        # BibleGateway ni reconstruir el panel de notas en cada carácter.
        if reference and reference != previous_reference:
            self.current_reference = reference
            self._refresh_threads_for_reference()

            if self.sync_checkbox.isChecked():
                parts = reference.split(".")
                if len(parts) >= 3 and parts[2] == "0":
                    nav_reference = ".".join(parts[:2])
                else:
                    nav_reference = reference

                self.reference_controller.set_reference(
                    nav_reference,
                    force=True,
                )

    def _select_verse_position(self, position):
        if not (0 <= position < len(self.verse_rows)):
            return

        self.current_verse_position = position
        row = self.verse_rows[position]

        self.verse_table.selectRow(row)
        item = self.verse_table.item(row, 0)
        if item:
            self.verse_table.scrollToItem(item)

    def _record_reference_history(
        self,
        reference: str,
    ):
        if (
            self._restoring_project_session
            or self._reference_history_navigating
        ):
            return

        reference = normalize_verse_ref(
            reference
        )
        if not reference:
            return

        if (
            0 <= self.reference_history_index
            < len(self.reference_history)
            and self.reference_history[
                self.reference_history_index
            ] == reference
        ):
            self._update_reference_history_controls()
            return

        # Como en un navegador: si se vuelve atrás y después se visita
        # un pasaje nuevo, la rama "siguiente" se reemplaza.
        if (
            self.reference_history_index
            < len(self.reference_history) - 1
        ):
            self.reference_history = (
                self.reference_history[
                    : self.reference_history_index + 1
                ]
            )

        self.reference_history.append(
            reference
        )

        # Evitar un desplegable interminable en sesiones muy largas.
        if len(self.reference_history) > 40:
            overflow = (
                len(self.reference_history) - 40
            )
            self.reference_history = (
                self.reference_history[
                    overflow:
                ]
            )

        self.reference_history_index = (
            len(self.reference_history) - 1
        )
        self._update_reference_history_controls()

    def _update_reference_history_controls(self):
        if not hasattr(
            self,
            "reference_history_combo",
        ):
            return

        count = len(
            self.reference_history
        )
        valid_index = (
            0 <= self.reference_history_index < count
        )

        self.prev_reference_button.setEnabled(
            valid_index
            and self.reference_history_index > 0
        )
        self.next_reference_button.setEnabled(
            valid_index
            and self.reference_history_index < count - 1
        )

        self.reference_history_combo.blockSignals(
            True
        )
        self.reference_history_combo.clear()

        for position, reference in enumerate(
            self.reference_history
        ):
            try:
                label = to_spanish_reference(
                    reference
                )
            except Exception:
                label = reference

            self.reference_history_combo.addItem(
                label,
                position,
            )

        if valid_index:
            self.reference_history_combo.setCurrentIndex(
                self.reference_history_index
            )

        self.reference_history_combo.blockSignals(
            False
        )
        self.reference_history_combo.setEnabled(
            bool(count)
        )

    def _navigate_reference_history_position(
        self,
        position: int,
    ):
        if not (
            0 <= position
            < len(self.reference_history)
        ):
            return

        reference = self.reference_history[
            position
        ]

        self._reference_history_navigating = True
        try:
            self.reference_history_index = (
                position
            )
            self._navigate_to_note_reference(
                reference,
                None,
            )
        finally:
            self._reference_history_navigating = False

        self._update_reference_history_controls()
        self._save_project_session()

    def move_reference_history(
        self,
        delta: int,
    ):
        target = (
            self.reference_history_index
            + int(delta)
        )
        self._navigate_reference_history_position(
            target
        )

    def _reference_history_combo_changed(
        self,
        combo_index: int,
    ):
        if (
            combo_index < 0
            or self._reference_history_navigating
        ):
            return

        position = (
            self.reference_history_combo.itemData(
                combo_index
            )
        )
        try:
            position = int(
                position
            )
        except (TypeError, ValueError):
            return

        if position == self.reference_history_index:
            return

        self._navigate_reference_history_position(
            position
        )

    def move_chapter(self, delta):
        index = self.chapter_combo.currentIndex()
        target = index + delta

        if 0 <= target < self.chapter_combo.count():
            self.chapter_combo.setCurrentIndex(target)

    def move_verse(self, delta):
        if not self.verse_rows:
            return

        target = self.current_verse_position + delta
        if 0 <= target < len(self.verse_rows):
            self._select_verse_position(target)


    def _note_reference_order_key(
        self,
        reference: str,
    ):
        ref = normalize_verse_ref(
            reference
        )
        book = (
            ref.split(".")[0]
            if ref
            else ""
        )

        book_order = {}
        if self.project:
            for index, project_text in enumerate(
                self.project.texts
            ):
                code = (
                    project_text.document.book
                    or ""
                ).upper()
                book_order.setdefault(
                    code,
                    index,
                )

        return (
            book_order.get(
                book,
                9999,
            ),
            verse_sort_key(
                ref
            ),
        )

    def _all_consultant_threads_ordered(
        self,
    ):
        if not self.notes_workspace:
            return []

        include_resolved = (
            self.show_resolved_checkbox.isChecked()
            if hasattr(
                self,
                "show_resolved_checkbox",
            )
            else False
        )

        consultant_key = (
            self.consultant_name
            or ""
        ).strip().casefold()

        result = []

        for thread_id, messages in (
            self.notes_workspace.thread_index.items()
        ):
            if not any(
                (
                    wrapped.owner
                    or ""
                ).strip().casefold()
                == consultant_key
                for wrapped in messages
            ):
                continue

            thread = self.notes_workspace.thread(
                thread_id
            )
            if thread is None:
                continue

            if (
                not include_resolved
                and thread.resolved_for_consultant()
            ):
                continue

            ref = normalize_verse_ref(
                thread.verse_ref
            )

            first_date = (
                thread.messages[0].message.date
                if thread.messages
                else ""
            )

            order_key = (
                self._note_reference_order_key(
                    ref
                )
            )
            result.append(
                (
                    order_key[0],
                    order_key[1],
                    first_date,
                    thread.thread,
                    thread,
                )
            )

        result.sort(
            key=lambda item: item[:4]
        )
        return [
            item[-1]
            for item in result
        ]

    def _review_threads(
        self,
    ):
        if not self.notes_workspace:
            return []
    
        # El modo revisión necesita conocer también los resueltos para poder
        # aplicar cualquiera de sus filtros.
        consultant_key = (
            self.consultant_name
            or ""
        ).strip().casefold()
    
        result = []
        for thread_id, messages in (
            self.notes_workspace.thread_index.items()
        ):
            if not any(
                (
                    wrapped.owner
                    or ""
                ).strip().casefold()
                == consultant_key
                for wrapped in messages
            ):
                continue
    
            thread = self.notes_workspace.thread(
                thread_id
            )
            if thread is None:
                continue
    
            mode = (
                self.review_filter_combo.currentData()
                if hasattr(
                    self,
                    "review_filter_combo",
                )
                else "pending"
            )
    
            resolved = (
                thread.resolved_for_consultant()
            )
            replied = (
                thread.has_reply_from_counterpart()
            )
    
            if (
                mode == "pending"
                and (
                    resolved
                    or replied
                )
            ):
                continue
    
            if (
                mode == "responded"
                and (
                    resolved
                    or not replied
                )
            ):
                continue
    
            if (
                mode == "resolved"
                and not resolved
            ):
                continue
    
            first_date = (
                thread.messages[0].message.date
                if thread.messages
                else ""
            )
            order_key = (
                self._note_reference_order_key(
                    thread.verse_ref
                )
            )
            result.append(
                (
                    order_key[0],
                    order_key[1],
                    first_date,
                    thread.thread,
                    thread,
                )
            )
    
        result.sort(
            key=lambda item: item[:4]
        )
        return [
            item[-1]
            for item in result
        ]
    
    def _note_navigation_threads(
        self,
    ):
        if self.review_mode:
            return self._review_threads()
        return self._all_consultant_threads_ordered()
    
    def _review_mode_toggled(
        self,
        checked: bool,
    ):
        self.review_mode = bool(
            checked
        )
    
        self.review_filter_combo.setVisible(
            self.review_mode
        )
        self.review_progress_label.setVisible(
            self.review_mode
        )
    
        if self.review_mode:
            self.review_mode_button.setText(
                "■ Revisión"
            )
            self.show_resolved_checkbox.blockSignals(
                True
            )
            self.show_resolved_checkbox.setChecked(
                self.review_filter_combo.currentData()
                in {
                    "resolved",
                    "all",
                }
            )
            self.show_resolved_checkbox.blockSignals(
                False
            )
            self._refresh_threads_for_reference()

            self.notes_dock.show()
            self.notes_dock.raise_()
    
            threads = self._review_threads()
            current_id = (
                self.current_interaction_thread.thread
                if self.current_interaction_thread
                else ""
            )
            ids = [
                thread.thread
                for thread in threads
            ]
    
            if (
                threads
                and current_id not in ids
            ):
                target = threads[0]
                self._navigate_to_note_reference(
                    target.verse_ref,
                    target.thread,
                )
        else:
            self.review_mode_button.setText(
                "▶ Revisión"
            )
    
        self._update_note_nav_buttons()
        self._update_review_progress()
    
    def _review_filter_changed(
        self,
        index: int,
    ):
        if not self.review_mode:
            return
    
        threads = self._review_threads()
        if threads:
            current_id = (
                self.current_interaction_thread.thread
                if self.current_interaction_thread
                else ""
            )
            ids = [
                thread.thread
                for thread in threads
            ]
            if current_id not in ids:
                target = threads[0]
                self._navigate_to_note_reference(
                    target.verse_ref,
                    target.thread,
                )
    
        self._update_note_nav_buttons()
        self._update_review_progress()
    
    def _update_review_progress(self):
        if not hasattr(
            self,
            "review_progress_label",
        ):
            return
    
        if not self.review_mode:
            self.review_progress_label.setText(
                ""
            )
            return
    
        threads = self._review_threads()
        total = len(threads)
    
        filter_name = (
            self.review_filter_combo.currentText()
        )

        if not total:
            self.review_progress_label.setText(
                f"{filter_name} 0/0"
            )
            return
    
        ids = [
            thread.thread
            for thread in threads
        ]
        current_id = (
            self.current_interaction_thread.thread
            if self.current_interaction_thread
            else ""
        )
    
        if current_id in ids:
            position = (
                ids.index(current_id)
                + 1
            )
        else:
            position = 0
    
        self.review_progress_label.setText(
            f"{filter_name} {position}/{total}"
        )
    
    def _next_review_target(self):
        if (
            not self.review_mode
            or not self.current_interaction_thread
        ):
            return None

        threads = self._review_threads()
        ids = [
            thread.thread
            for thread in threads
        ]
        current_id = (
            self.current_interaction_thread.thread
        )

        if current_id not in ids:
            return None

        index = ids.index(
            current_id
        )
        if index >= len(threads) - 1:
            return None

        return threads[
            index + 1
        ]

    def _advance_review_after_action(
        self,
        target=None,
    ):
        if not self.review_mode:
            return

        if target is None:
            self._update_review_progress()
            if not self._review_threads():
                self.review_progress_label.setText(
                    f"{self.review_filter_combo.currentText()} ✓"
                )
            return

        QTimer.singleShot(
            0,
            lambda t=target:
                self._navigate_to_note_reference(
                    t.verse_ref,
                    t.thread,
                ),
        )

    def _update_note_nav_buttons(self):
        if not hasattr(
            self,
            "prev_note_button",
        ):
            return

        threads = (
            self._note_navigation_threads()
        )

        if not threads:
            self.prev_note_button.setEnabled(
                False
            )
            self.next_note_button.setEnabled(
                False
            )
            self._update_review_progress()
            return

        ids = [
            thread.thread
            for thread in threads
        ]

        current_id = (
            self.current_interaction_thread.thread
            if self.current_interaction_thread
            else ""
        )

        if current_id not in ids:
            if not self.current_reference:
                self.prev_note_button.setEnabled(
                    False
                )
                self.next_note_button.setEnabled(
                    bool(ids)
                )
                self._update_review_progress()
                return

            current_key = (
                self._note_reference_order_key(
                    self.current_reference
                )
            )
            thread_keys = [
                self._note_reference_order_key(
                    thread.verse_ref
                )
                for thread in threads
            ]

            self.prev_note_button.setEnabled(
                any(
                    key < current_key
                    for key in thread_keys
                )
            )
            self.next_note_button.setEnabled(
                any(
                    key > current_key
                    for key in thread_keys
                )
            )
            self._update_review_progress()
            return

        index = ids.index(
            current_id
        )
        self.prev_note_button.setEnabled(
            index > 0
        )
        self.next_note_button.setEnabled(
            index < len(ids) - 1
        )
        self._update_review_progress()

    def move_consultant_note(
        self,
        delta: int,
    ):
        threads = (
            self._note_navigation_threads()
        )
        if not threads:
            return

        ids = [
            thread.thread
            for thread in threads
        ]

        current_id = (
            self.current_interaction_thread.thread
            if self.current_interaction_thread
            else ""
        )

        if current_id in ids:
            current_index = ids.index(
                current_id
            )
            target_index = (
                current_index + delta
            )

            if not (
                0
                <= target_index
                < len(threads)
            ):
                return

            target = threads[
                target_index
            ]
        else:
            if not self.current_reference:
                target = (
                    threads[0]
                    if delta >= 0
                    else threads[-1]
                )
            else:
                current_key = (
                    self._note_reference_order_key(
                        self.current_reference
                    )
                )
                candidates = [
                    thread
                    for thread in threads
                    if (
                        self._note_reference_order_key(
                            thread.verse_ref
                        )
                        > current_key
                        if delta >= 0
                        else self._note_reference_order_key(
                            thread.verse_ref
                        )
                        < current_key
                    )
                ]

                if not candidates:
                    return

                target = (
                    candidates[0]
                    if delta >= 0
                    else candidates[-1]
                )
        self._navigate_to_note_reference(
            target.verse_ref,
            target.thread,
        )

    def _navigate_to_note_reference(
        self,
        reference: str,
        thread_id: str | None = None,
    ):
        ref = normalize_verse_ref(
            reference
        )
        if not ref:
            return

        target_thread = (
            self.notes_workspace.thread(
                thread_id
            )
            if (
                self.notes_workspace
                and thread_id
            )
            else None
        )

        if (
            target_thread
            and target_thread.resolved_for_consultant()
            and not self.show_resolved_checkbox.isChecked()
        ):
            self.show_resolved_checkbox.setChecked(
                True
            )

        parts = ref.split(".")
        book = (
            parts[0]
            if parts
            else ""
        )
        chapter = (
            parts[1]
            if len(parts) > 1
            else ""
        )
        verse = (
            parts[2]
            if len(parts) > 2
            else ""
        )

        text_index = -1

        if (
            self.current_text is not None
            and (
                self.current_text.document.book
                or ""
            ).upper()
            == book
        ):
            text_index = (
                self.text_combo.currentIndex()
            )
        else:
            for index in range(
                self.text_combo.count()
            ):
                project_text = (
                    self.text_combo.itemData(
                        index
                    )
                )
                if (
                    project_text
                    and (
                        project_text.document.book
                        or ""
                    ).upper()
                    == book
                ):
                    text_index = index
                    break

        if text_index >= 0:
            if (
                self.text_combo.currentIndex()
                != text_index
            ):
                self.text_combo.setCurrentIndex(
                    text_index
                )

            chapter_index = (
                self.chapter_combo.findData(
                    chapter
                )
            )
            if chapter_index >= 0:
                if (
                    self.chapter_combo.currentIndex()
                    != chapter_index
                ):
                    self.chapter_combo.setCurrentIndex(
                        chapter_index
                    )

            # v.0 representa encabezados/secciones iniciales. En ese caso
            # seleccionamos v.1, porque la búsqueda de notas de v.1 ya incluye
            # la referencia v.0.
            target_ref = ref
            if verse == "0":
                target_ref = (
                    f"{book}.{chapter}.1"
                )

            for position, row in enumerate(
                self.verse_rows
            ):
                item = self.verse_table.item(
                    row,
                    0,
                )
                row_ref = (
                    item.data(Qt.UserRole)
                    if item
                    else None
                )
                if (
                    row_ref
                    and normalize_verse_ref(
                        row_ref
                    )
                    == target_ref
                ):
                    self._select_verse_position(
                        position
                    )
                    break
        else:
            self.current_reference = ref
            self._refresh_threads_for_reference()

        if thread_id:
            for index in range(
                self.thread_combo.count()
            ):
                if (
                    self.thread_combo.itemData(
                        index
                    )
                    == thread_id
                ):
                    self.thread_combo.setCurrentIndex(
                        index
                    )
                    break

        self.notes_dock.show()
        self.notes_dock.raise_()
        self._update_note_nav_buttons()

    def _update_nav_buttons(self):
        ci = (
            self.chapter_combo.currentIndex()
            if hasattr(self, "chapter_combo")
            else -1
        )
        cc = (
            self.chapter_combo.count()
            if hasattr(self, "chapter_combo")
            else 0
        )

        self.prev_chapter_button.setEnabled(ci > 0)
        self.next_chapter_button.setEnabled(
            0 <= ci < cc - 1
        )

        self.prev_verse_button.setEnabled(
            self.current_verse_position > 0
        )
        self.next_verse_button.setEnabled(
            0
            <= self.current_verse_position
            < len(self.verse_rows) - 1
        )

    def _verse_selection_changed(self):
        row = self.verse_table.currentRow()

        if row not in self.verse_rows:
            return

        item = self.verse_table.item(row, 0)
        if not item:
            return

        reference = item.data(Qt.UserRole)
        if not reference:
            return

        widget = self.anchor_widgets_by_row.get(
            row
        )
        if widget is not None:
            self.current_anchor_widget = widget
            metadata = widget.selection_metadata()
            self.selection_status_label.setText(
                "Anclaje de nota: versículo · "
                f"punto en posición SFM "
                f"{metadata.get('StartPosition', 0)}"
            )
            self.new_note_button.setEnabled(
                bool(self.notes_workspace)
            )

        try:
            self.current_verse_position = (
                self.verse_rows.index(row)
            )
        except ValueError:
            self.current_verse_position = -1

        self.current_reference = normalize_verse_ref(
            reference
        )
        self._update_nav_buttons()

        if self.sync_checkbox.isChecked():
            self.reference_controller.set_reference(
                self.current_reference,
                force=True,
            )
        else:
            self._set_reference_edit(
                to_spanish_reference(
                    self.current_reference
                )
            )

        self._refresh_threads_for_reference()
        self._save_project_session()

    # ------------------------------------------------------------------
    # Identidad y repositorio de notas
    # ------------------------------------------------------------------
    def _ensure_consultant_identity(self):
        if not self.project or not self.project.notes_files:
            return

        owners = []
        seen = set()
        for info in self.project.notes_files:
            key = info.owner.casefold()
            if key not in seen:
                owners.append(info.owner)
                seen.add(key)

        valid = any(
            _same_name(owner, self.consultant_name)
            for owner in owners
        )

        if not valid:
            current = 0
            value, ok = QInputDialog.getItem(
                self,
                "Usuario consultor",
                "¿Cuál de estos archivos Notes_ corresponde a tus notas?",
                owners,
                current,
                False,
            )
            if ok and value.strip():
                self.consultant_name = value.strip()
                self.settings.setValue(
                    "consultant_name",
                    self.consultant_name,
                )

    def choose_consultant(self):
        owners = []
        if self.project:
            seen = set()
            for info in self.project.notes_files:
                key = info.owner.casefold()
                if key not in seen:
                    owners.append(info.owner)
                    seen.add(key)

        if owners:
            current_index = 0
            for i, owner in enumerate(owners):
                if _same_name(
                    owner,
                    self.consultant_name,
                ):
                    current_index = i
                    break

            value, ok = QInputDialog.getItem(
                self,
                "Usuario consultor",
                "¿Cuál archivo Notes_ corresponde a tus notas?",
                owners,
                current_index,
                False,
            )
        else:
            value, ok = QInputDialog.getText(
                self,
                "Usuario consultor",
                "Nombre del usuario consultor:",
                text=self.consultant_name,
            )

        if ok and value.strip():
            self.consultant_name = value.strip()
            self.settings.setValue(
                "consultant_name",
                self.consultant_name,
            )

            if self.project:
                self._build_notes_workspace()
                self._refresh_threads_for_reference()

    def _build_notes_workspace(self):
        self.notes_workspace = None
        self.consultant_label.setText(
            f"Consultor: {self.consultant_name or '—'}"
        )

        if (
            not self.project
            or not self.project.notes_files
            or not self.consultant_name
        ):
            self._set_notes_disabled(
                "No hay archivos de notas disponibles."
            )
            return

        try:
            workspace = NotesWorkspace(
                self.project.notes_files,
                self.consultant_name,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Notas XML",
                f"No fue posible cargar los archivos de notas:\n{exc}",
            )
            self._set_notes_disabled()
            return

        if workspace.consultant_document() is None:
            QMessageBox.warning(
                self,
                "Usuario consultor",
                "No encontré un Notes_*.xml cuyo User corresponda "
                f"a '{self.consultant_name}'.",
            )
            self._set_notes_disabled()
            return

        self.notes_workspace = workspace
        self._refresh_threads_for_reference()

    def _reference_candidates_for_notes(self):
        if not self.current_reference:
            return []

        ref = normalize_verse_ref(
            self.current_reference
        )
        parts = ref.split(".")

        if len(parts) < 3:
            return [ref]

        # Si estamos exactamente en v.0 (encabezado/sección inicial), buscar
        # solo las notas de v.0.
        if parts[2] == "0":
            return [ref]

        refs = [ref]

        # Las notas de encabezado inicial de capítulo se asocian con v.0.
        # También las mostramos al estar en v.1.
        if parts[2] == "1":
            refs.append(
                f"{parts[0]}.{parts[1]}.0"
            )

        return refs

    def _refresh_threads_for_reference(self):
        self._record_reference_history(
            self.current_reference
        )
        self._sync_resource_reference(
            self.current_reference
        )
        self.cancel_reply(silent=True)
        self.cancel_new_note(silent=True)
        self._refresh_note_markers()

        self.thread_combo.blockSignals(True)
        self.thread_combo.clear()

        if (
            not self.notes_workspace
            or not self.current_reference
        ):
            self.thread_combo.blockSignals(False)
            self._set_notes_disabled()
            self._update_note_nav_buttons()
            return

        include_resolved = (
            self.show_resolved_checkbox.isChecked()
        )

        threads: list[InteractionThread] = []
        seen = set()

        for ref in self._reference_candidates_for_notes():
            for thread in self.notes_workspace.threads_for_reference(
                ref,
                include_resolved=include_resolved,
            ):
                if thread.thread not in seen:
                    threads.append(thread)
                    seen.add(thread.thread)

        for position, thread in enumerate(
            threads,
            start=1,
        ):
            original = (
                thread.original_consultant_message()
            )
            preview = ""
            if original:
                preview = (
                    original.message.selected_text
                    or original.message.contents.replace(
                        "\n",
                        " ",
                    )
                ).strip()

            if len(preview) > 58:
                preview = preview[:55] + "…"

            counterpart = thread.counterpart()
            if thread.resolved_for_consultant():
                status = "✓ resuelta"
            elif thread.has_reply_from_counterpart():
                status = "● respondió"
            else:
                status = "○ pendiente"

            label = (
                f"{position}. → {counterpart} · {status}"
            )
            if preview:
                label += f" — {preview}"

            self.thread_combo.addItem(
                label,
                thread.thread,
            )

        self.thread_combo.blockSignals(False)

        if self.thread_combo.count():
            self.thread_combo.setCurrentIndex(0)
            self._thread_changed(0)
        else:
            self._set_notes_disabled(
                "No hay notas del consultor para este versículo."
            )

        self._update_note_nav_buttons()

    def _thread_changed(self, index):
        if (
            index < 0
            or not self.notes_workspace
        ):
            self._set_notes_disabled()
            return

        thread_id = self.thread_combo.itemData(index)
        if not thread_id:
            return

        thread = self.notes_workspace.thread(
            thread_id
        )
        if not thread:
            return

        self.current_interaction_thread = thread

        counterpart = thread.counterpart()
        replied = thread.has_reply_from_counterpart()

        self.interaction_label.setText(
            f"Interacción: {self.consultant_name} ↔ {counterpart}"
        )

        if thread.resolved_for_consultant():
            self.thread_status_label.setText(
                "✓ Hilo resuelto"
            )
        elif replied:
            self.thread_status_label.setText(
                "● Hay respuesta"
            )
        else:
            self.thread_status_label.setText(
                "○ Esperando respuesta"
            )

        self._populate_conversation(thread)
        self._update_note_nav_buttons()
        self._update_review_progress()


    def _populate_conversation(
        self,
        thread: InteractionThread,
    ):
        """
        Izquierda: solo intervenciones propias del consultor.
        Derecha: solo respuestas de otros usuarios.
        """
        self.message_tree.blockSignals(True)
        self.message_tree.clear()

        self.my_message_combo.blockSignals(True)
        self.my_message_combo.clear()

        own_messages = [
            wrapped
            for wrapped in thread.visible_messages
            if _same_name(
                wrapped.owner,
                self.consultant_name,
            )
        ]

        for index, wrapped in enumerate(
            own_messages
        ):
            msg = wrapped.message
            label = (
                "Nota original"
                if index == 0
                else f"Seguimiento propio {index}"
            )

            if msg.date:
                label += (
                    " · "
                    + msg.date[:16].replace(
                        "T",
                        " ",
                    )
                )

            self.my_message_combo.addItem(
                label,
                wrapped,
            )

        self.my_message_combo.setVisible(
            len(own_messages) > 1
        )
        self.my_message_combo.blockSignals(
            False
        )

        if own_messages:
            self.my_message_combo.setCurrentIndex(
                0
            )
            self._show_consultant_message(
                own_messages[0]
            )
        else:
            self._set_message_editor_empty(
                "Este hilo no contiene una intervención propia activa."
            )

        external_messages = [
            wrapped
            for wrapped in thread.visible_messages
            if not _same_name(
                wrapped.owner,
                self.consultant_name,
            )
        ]

        if external_messages:
            for wrapped in external_messages:
                msg = wrapped.message

                content = (
                    msg.contents.strip()
                    or msg.selected_text.strip()
                    or "(sin contenido)"
                )

                date = (
                    msg.date[:16].replace(
                        "T",
                        " ",
                    )
                    if msg.date
                    else ""
                )

                item = QTreeWidgetItem(
                    [
                        wrapped.owner,
                        content,
                        date,
                    ]
                )
                item.setData(
                    0,
                    Qt.UserRole,
                    wrapped,
                )

                font = QFont(
                    item.font(0)
                )
                font.setItalic(True)
                item.setFont(
                    0,
                    font,
                )

                self.message_tree.addTopLevelItem(
                    item
                )
        else:
            empty = QTreeWidgetItem(
                [
                    "",
                    "Sin respuesta del interlocutor.",
                    "",
                ]
            )
            empty.setFlags(
                empty.flags()
                & ~Qt.ItemIsSelectable
            )
            self.message_tree.addTopLevelItem(
                empty
            )

        self.message_tree.blockSignals(False)


    def _my_message_changed(
        self,
        index: int,
    ):
        if index < 0:
            return

        wrapped = self.my_message_combo.itemData(
            index
        )
        if wrapped:
            self._show_consultant_message(
                wrapped
            )


    def _show_consultant_message(
        self,
        wrapped: InteractionMessage,
    ):
        self.current_interaction_message = (
            wrapped
        )
        self.reply_mode = False

        msg = wrapped.message

        self.note_editor.setPlainText(
            msg.contents
        )
        self._update_note_verse_comparison(
            msg
        )
        self._highlight_note_anchor(
            msg
        )

        target = (
            msg.reply_to_user
            or msg.assigned_user
            or "—"
        )

        self.note_metadata.setText(
            f"Dirigida a: {target}   ·   "
            f"Fecha: {msg.date or '—'}   ·   "
            f"Thread: {msg.thread}"
        )

        editable = (
            _same_name(
                wrapped.owner,
                self.consultant_name,
            )
            and not wrapped.deleted
        )

        self.note_editor.setReadOnly(
            not editable
        )
        self.note_marker_combo.setEnabled(
            editable
        )
        self.save_note_button.setEnabled(
            editable
        )

        can_resolve = bool(
            self.current_interaction_thread
            and not self.current_interaction_thread.resolved_for_consultant()
        )
        self.resolve_button.setEnabled(
            can_resolve
        )
        self.delete_note_button.setEnabled(
            editable
        )
        self.new_note_button.setEnabled(
            bool(
                self.notes_workspace
                and self.current_anchor_widget
            )
        )
        self.reply_button.setEnabled(
            can_resolve
        )

        if wrapped.deleted:
            self.editability_label.setText(
                "Nota resuelta · solo lectura"
            )
        elif editable:
            self.editability_label.setText(
                "Mi nota · editable"
            )
        else:
            self.editability_label.setText(
                "Solo lectura"
            )

        self.new_note_button.show()
        self.save_note_button.show()
        self.resolve_button.show()
        self.delete_note_button.show()

        self.save_new_note_button.hide()
        self.cancel_new_note_button.hide()

        self.recipient_label.hide()
        self.recipient_combo.hide()


    def _response_item_changed(
        self,
        current,
        previous,
    ):
        if current is None:
            return

        wrapped = current.data(
            0,
            Qt.UserRole,
        )
        if not wrapped:
            return

        msg = wrapped.message
        target = (
            msg.reply_to_user
            or msg.assigned_user
            or self.consultant_name
        )

        self.interaction_label.setText(
            f"{wrapped.owner} → {target}"
        )


    def _message_item_changed(
        self,
        current,
        previous,
    ):
        # Alias de compatibilidad; las respuestas ya no reemplazan
        # el editor principal del consultor.
        self._response_item_changed(
            current,
            previous,
        )

    def _insert_note_marker_from_combo(
        self,
        index: int,
    ):
        data = self.note_marker_combo.itemData(
            index
        )

        # Volver inmediatamente al elemento neutro para poder insertar el
        # mismo marcador varias veces.
        self.note_marker_combo.blockSignals(
            True
        )
        self.note_marker_combo.setCurrentIndex(
            0
        )
        self.note_marker_combo.blockSignals(
            False
        )

        if not data:
            return

        if self.note_editor.isReadOnly():
            self.statusBar().showMessage(
                "La intervención seleccionada es de solo lectura.",
                3000,
            )
            return

        if data == "__template__":
            snippet = (
                "COM: \n\n"
                "PT: \n\n"
                "SUG:\n"
                "A) \n\n"
                "CONT: \n\n"
                "IndS: %"
            )
        elif data == "SUG:":
            snippet = (
                "SUG:\n"
                "A) "
            )
        elif data == "IndS: %":
            snippet = "IndS: %"
        else:
            snippet = f"{data} "

        cursor = self.note_editor.textCursor()
        current_text = self.note_editor.toPlainText()

        prefix = ""
        if current_text and cursor.position() > 0:
            before = current_text[
                max(0, cursor.position() - 2):
                cursor.position()
            ]
            if not before.endswith("\n\n"):
                prefix = (
                    "\n"
                    if before.endswith("\n")
                    else "\n\n"
                )

        cursor.insertText(
            prefix + snippet
        )
        self.note_editor.setTextCursor(
            cursor
        )
        self.note_editor.setFocus()

    def _current_sfm_source_for_message(
        self,
        msg,
    ) -> str:
        if not self.project or msg is None:
            return ""

        reference = normalize_verse_ref(
            msg.verse_ref
        )
        selected = (
            msg.selected_text or ""
        ).strip()

        # Priorizar el SFM que está abierto en pantalla. Esto es importante
        # si el proyecto contiene traducción y retrotraducción con las mismas
        # referencias.
        project_texts = []
        if self.current_text is not None:
            project_texts.append(
                self.current_text
            )
        project_texts.extend(
            item
            for item in self.project.texts
            if item is not self.current_text
        )

        # Primero buscar un \s asociado a la referencia y, si hay
        # SelectedText, preferir el bloque que realmente contiene esa
        # selección.
        for project_text in project_texts:
            for verse in project_text.document.verses:
                for anchor in verse.subtitle_anchors:
                    if (
                        normalize_verse_ref(
                            anchor.reference
                        )
                        != reference
                    ):
                        continue

                    if (
                        not selected
                        or selected in anchor.source_text
                    ):
                        return (
                            anchor.source_text
                            or anchor.visible_text
                        )

        # Luego buscar el bloque del versículo normal.
        for project_text in project_texts:
            for verse in project_text.document.verses:
                if (
                    normalize_verse_ref(
                        verse.reference
                    )
                    == reference
                ):
                    return (
                        verse.source_text
                        or verse.text
                    )

        return ""


    def _normalize_verse_for_change(
        self,
        value: str,
    ) -> str:
        text = value or ""

        # Quitar notas al pie y marcadores USFM para calcular cambio del contenido
        # lingüístico, no del formato.
        text = re.sub(
            r"\\f(?:\s+.*?)?\\f\*",
            " ",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(
            r"\\[A-Za-z0-9]+\*?",
            " ",
            text,
        )
        text = re.sub(
            r"^\s*\d+(?:-\d+)?[a-z]?\s+",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip().casefold()

        return text


    def _verse_change_percentage(
        self,
        old_verse: str,
        current_verse: str,
    ):
        old_norm = self._normalize_verse_for_change(
            old_verse
        )
        current_norm = self._normalize_verse_for_change(
            current_verse
        )

        if not old_norm or not current_norm:
            return None

        similarity = difflib.SequenceMatcher(
            None,
            old_norm,
            current_norm,
        ).ratio()

        return round(
            (1.0 - similarity) * 100.0,
            1,
        )


    def _set_change_badge(
        self,
        percentage,
    ):
        if percentage is None:
            self.verse_change_label.setText(
                "Cambio textual: —"
            )
            self.verse_change_label.setStyleSheet(
                "font-weight: 700; padding: 3px 8px; "
                "border-radius: 8px; background: #e6e6e6;"
            )
            return

        self.verse_change_label.setText(
            f"Cambio textual: {percentage:.1f} %"
        )

        if percentage <= 10:
            background = "#dff2e2"
            border = "#a8cfaf"
        elif percentage <= 30:
            background = "#fff0c9"
            border = "#e3c574"
        else:
            background = "#f8dddd"
            border = "#dfa2a2"

        self.verse_change_label.setStyleSheet(
            "font-weight: 700; padding: 3px 8px; "
            f"border-radius: 8px; background: {background}; "
            f"border: 1px solid {border};"
        )
        self.verse_change_label.setToolTip(
            "Porcentaje aproximado de cambio textual entre el <Verse> "
            "guardado en la nota y el SFM actual. "
            "Se calcula sobre el texto normalizado, sin marcadores USFM."
        )


    def _update_note_verse_comparison(
        self,
        msg,
    ):
        if msg is None:
            self.note_verse_ref_label.setText(
                "VerseRef: —"
            )
            self.note_old_verse.setText(
                "<b>ANTES ·</b> —"
            )
            self.note_current_verse.setText(
                "<b>ACTUAL ·</b> —"
            )
            self._set_change_badge(
                None
            )
            return

        reference = (
            msg.verse_ref or "—"
        )
        self.note_verse_ref_label.setText(
            f"VerseRef: {reference}"
        )

        old_verse = (
            msg.verse_text or ""
        )
        current_verse = (
            self._current_sfm_source_for_message(
                msg
            )
        )

        old_display = (
            old_verse.strip()
            or "No hay <Verse> histórico guardado."
        )
        current_display = (
            current_verse.strip()
            or "No se encontró esta referencia en los SFM actuales del proyecto."
        )

        if old_verse and current_verse:
            old_diff, current_diff = diff_html(
                old_display,
                current_display,
            )
            self.note_old_verse.setText(
                "<b>ANTES ·</b> "
                + old_diff
            )
            self.note_current_verse.setText(
                "<b>ACTUAL ·</b> "
                + current_diff
            )
        else:
            # Los textos auxiliares no contienen contenido aportado por el
            # usuario; se pueden mostrar sin resaltado diferencial.
            self.note_old_verse.setText(
                "<b>ANTES ·</b> "
                + html.escape(old_display)
            )
            self.note_current_verse.setText(
                "<b>ACTUAL ·</b> "
                + html.escape(current_display)
            )

        percentage = self._verse_change_percentage(
            old_verse,
            current_verse,
        )
        self._set_change_badge(
            percentage
        )

    def _set_message_editor_empty(self, text):
        self._clear_note_anchor_highlights()
        self.current_interaction_message = None
        self.my_message_combo.clear()
        self.my_message_combo.hide()
        self.note_metadata.setText(text)
        self.note_editor.clear()
        self.note_editor.setReadOnly(True)
        self.note_marker_combo.setEnabled(False)
        self._update_note_verse_comparison(
            None
        )
        self.new_note_button.setEnabled(
            bool(
                self.notes_workspace
                and self.current_anchor_widget
            )
        )
        self.save_note_button.setEnabled(False)
        self.reply_button.setEnabled(False)
        self.resolve_button.setEnabled(False)
        self.delete_note_button.setEnabled(False)
        self.reply_mode = False
        self.reply_editor.clear()
        self.reply_editor.hide()
        self.reply_recipient_label.hide()
        self.reply_recipient_combo.hide()
        self.save_reply_button.hide()
        self.cancel_reply_button.hide()
        self.editability_label.setText("")

    def _set_notes_disabled(
        self,
        message="Sin nota seleccionada",
    ):
        self._clear_note_anchor_highlights()
        self.current_interaction_thread = None
        self.current_interaction_message = None
        self.message_tree.clear()
        self.my_message_combo.clear()
        self.my_message_combo.hide()

        self.interaction_label.setText(
            "Interacción: —"
        )
        self.thread_status_label.setText("")
        self.note_metadata.setText(message)

        self.note_editor.clear()
        self.note_editor.setReadOnly(True)
        self.note_marker_combo.setEnabled(False)
        self._update_note_verse_comparison(
            None
        )

        self.new_note_button.setEnabled(
            bool(
                self.notes_workspace
                and self.current_anchor_widget
            )
        )
        self.save_note_button.setEnabled(False)
        self.reply_button.setEnabled(False)
        self.resolve_button.setEnabled(False)
        self.delete_note_button.setEnabled(False)

        self.save_new_note_button.hide()
        self.cancel_new_note_button.hide()
        self.save_reply_button.hide()
        self.cancel_reply_button.hide()
        self.reply_editor.hide()
        self.reply_recipient_label.hide()
        self.reply_recipient_combo.hide()
        self.recipient_label.hide()
        self.recipient_combo.hide()

        self.editability_label.setText("")

    # ------------------------------------------------------------------
    # Editar MIS intervenciones / responder sin modificar las ajenas
    # ------------------------------------------------------------------
    def _recipient_people(self):
        people = []
        if self.notes_workspace:
            people = [
                person
                for person in self.notes_workspace.all_people()
                if not _same_name(
                    person,
                    self.consultant_name,
                )
            ]

        if "Team" not in people:
            people.insert(0, "Team")
        return people

    def begin_new_note_from_current_anchor(self):
        widget = self.current_anchor_widget

        if widget is None and self.verse_rows:
            row = self.verse_rows[
                max(0, self.current_verse_position)
            ]
            widget = self.anchor_widgets_by_row.get(
                row
            )

        if widget is None:
            QMessageBox.information(
                self,
                "Nueva nota",
                "Primero haga clic en el texto del versículo o subtítulo. "
                "Puede seleccionar una palabra/frase o simplemente colocar "
                "el cursor en el punto donde quiere anclar la nota.",
            )
            return

        self.begin_new_note(widget)

    def begin_new_note(self, widget=None):
        if not self.notes_workspace:
            QMessageBox.warning(
                self,
                "Nueva nota",
                "No está disponible el archivo Notes_*.xml del consultor.",
            )
            return

        if widget is None:
            widget = self.current_anchor_widget

        if widget is None:
            self.begin_new_note_from_current_anchor()
            return

        self.cancel_reply(silent=True)

        self.current_anchor_widget = widget
        anchor = widget.selection_metadata()

        self.new_note_mode = True
        self.new_note_anchor = anchor

        self.recipient_combo.clear()
        self.recipient_combo.addItems(
            self._recipient_people()
        )
        self.recipient_combo.setCurrentText(
            "Team"
        )

        selected = (
            anchor.get("SelectedText", "")
            or ""
        )
        start_position = anchor.get(
            "StartPosition",
            0,
        )
        verse_ref = normalize_verse_ref(
            anchor.get("VerseRef", "")
        )
        kind = (
            "subtítulo \\s"
            if anchor.get("Kind") == "section"
            else "texto del versículo"
        )

        if selected:
            anchor_description = (
                f"Selección: «{selected}»"
            )
        else:
            anchor_description = (
                "Anclaje en un punto, sin texto seleccionado"
            )

        self.interaction_label.setText(
            "Nueva nota"
        )
        self.thread_status_label.setText("")
        self.note_metadata.setText(
            f"{kind}   |   VerseRef: {verse_ref}   |   "
            f"StartPosition: {start_position}   |   "
            f"{anchor_description}"
        )

        self.note_verse_ref_label.setText(
            f"VerseRef: {verse_ref}"
        )
        self.note_old_verse.setText(
            "<b>ANTES ·</b> Nueva nota: todavía no existe un "
            "&lt;Verse&gt; histórico guardado."
        )
        self.note_current_verse.setText(
            "<b>ACTUAL ·</b> "
            + html.escape(
                anchor.get("Verse", "") or ""
            )
        )
        self._set_change_badge(
            None
        )

        self.note_editor.clear()
        self.note_editor.setReadOnly(False)
        self.note_marker_combo.setEnabled(True)
        self.note_editor.setPlaceholderText(
            "Escriba el contenido de la nueva nota.\n\n"
            "Ejemplo:\n"
            "COM: ...\n\n"
            "PT: ...\n\n"
            "SUG:\n"
            "A) ...\n"
            "B) ...\n\n"
            "CONT: ..."
        )

        self.recipient_label.setText(
            "Dirigir a:"
        )
        self.recipient_label.show()
        self.recipient_combo.show()

        self.new_note_button.hide()
        self.save_note_button.hide()
        self.reply_button.hide()
        self.resolve_button.hide()
        self.delete_note_button.hide()

        self.reply_button.setEnabled(False)
        self.save_reply_button.hide()
        self.cancel_reply_button.hide()
        self.reply_editor.hide()
        self.reply_recipient_label.hide()
        self.reply_recipient_combo.hide()

        self.save_new_note_button.show()
        self.cancel_new_note_button.show()

        self.editability_label.setText(
            "● Nueva nota anclada al SFM"
        )
        self.note_editor.setFocus()

    def save_new_note(self):
        if (
            not self.new_note_mode
            or not self.new_note_anchor
            or not self.notes_workspace
        ):
            return

        text_value = self.note_editor.toPlainText().strip()
        if not text_value:
            QMessageBox.warning(
                self,
                "Nueva nota",
                "Escriba el contenido de la nota.",
            )
            return

        target = (
            self.recipient_combo.currentText().strip()
            or "Team"
        )

        anchor = dict(
            self.new_note_anchor
        )

        try:
            thread_id = (
                self.notes_workspace.create_consultant_note(
                    anchor=anchor,
                    text=text_value,
                    target=target,
                )
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Nueva nota",
                str(exc),
            )
            return

        self._after_internal_file_write()
        self.cancel_new_note(silent=True)

        self.current_reference = normalize_verse_ref(
            anchor.get("VerseRef", "")
        )
        self._refresh_threads_for_reference()

        for index in range(
            self.thread_combo.count()
        ):
            if (
                self.thread_combo.itemData(index)
                == thread_id
            ):
                self.thread_combo.setCurrentIndex(
                    index
                )
                break

        self.statusBar().showMessage(
            "Nueva nota creada en "
            f"Notes_{self.consultant_name}.xml. "
            "Se creó una copia de seguridad.",
            5000,
        )

    def cancel_new_note(self, silent=False):
        if not self.new_note_mode:
            return

        self.new_note_mode = False
        self.new_note_anchor = None

        self.recipient_label.hide()
        self.recipient_combo.hide()
        self.save_new_note_button.hide()
        self.cancel_new_note_button.hide()

        self.new_note_button.show()
        self.save_note_button.show()
        self.resolve_button.show()
        self.delete_note_button.show()

        if (
            self.current_interaction_thread
            and self.current_interaction_message
        ):
            self._show_consultant_message(
                self.current_interaction_message
            )
        elif not silent:
            self._set_notes_disabled(
                "No hay una nota seleccionada."
            )

    def save_my_message(self):
        if (
            not self.notes_workspace
            or not self.current_interaction_message
        ):
            return

        wrapped = self.current_interaction_message

        if not _same_name(
            wrapped.owner,
            self.consultant_name,
        ):
            QMessageBox.warning(
                self,
                "Notas",
                "Las respuestas de otros usuarios son de solo lectura.",
            )
            return

        try:
            self.notes_workspace.update_consultant_message(
                wrapped,
                self.note_editor.toPlainText(),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Guardar cambios",
                str(exc),
            )
            return

        self._after_internal_file_write()
        self._refresh_threads_for_reference()
        self.statusBar().showMessage(
            "Intervención guardada. Se creó copia de seguridad.",
            4000,
        )

    def resolve_current_thread(self):
        """
        Resolver no borra el historial. Añade en el Notes_*.xml del consultor
        un nuevo Comment del mismo Thread con Status=deleted.
        """
        if (
            not self.notes_workspace
            or not self.current_interaction_thread
        ):
            return

        thread = self.current_interaction_thread
        review_next_target = (
            self._next_review_target()
        )

        if thread.resolved_for_consultant():
            QMessageBox.information(
                self,
                "Resolver nota",
                "Esta nota ya está resuelta.",
            )
            return

        counterpart = thread.counterpart()

        answer = QMessageBox.question(
            self,
            "Resolver nota",
            "¿Resolver esta nota?\n\n"
            "Se conservará toda la conversación y se añadirá "
            "un marcador de cierre <Status>deleted</Status> "
            f"en Notes_{self.consultant_name}.xml.\n\n"
            f"Interacción: {self.consultant_name} ↔ {counterpart}",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.notes_workspace.resolve_thread(
                thread
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Resolver nota",
                str(exc),
            )
            return

        self._after_internal_file_write()
        self._refresh_threads_for_reference()
        self.statusBar().showMessage(
            "Nota resuelta. El historial se conservó y se creó una copia de seguridad.",
            5000,
        )
        self._advance_review_after_action(
            review_next_target
        )

    def delete_current_message(self):
        """
        Borrado físico de una intervención propia.

        No se usa Status=deleted para esta acción; ese marcador se reserva
        para Resolver. El nodo Comment seleccionado se elimina del XML propio.
        """
        if (
            not self.notes_workspace
            or not self.current_interaction_thread
            or not self.current_interaction_message
        ):
            return

        wrapped = self.current_interaction_message
        thread = self.current_interaction_thread

        if not _same_name(
            wrapped.owner,
            self.consultant_name,
        ):
            QMessageBox.warning(
                self,
                "Borrar nota",
                "Solo puede borrar intervenciones que estén en su propio archivo de notas.",
            )
            return

        if wrapped.deleted:
            QMessageBox.warning(
                self,
                "Borrar nota",
                "El marcador de resolución no se borra desde esta opción.",
            )
            return

        is_original = self.notes_workspace.is_original_consultant_message(
            thread,
            wrapped,
        )
        has_external = self.notes_workspace.has_external_replies(
            thread
        )

        if is_original and has_external:
            message = (
                "Esta es la nota inicial del hilo y ya tiene respuestas "
                "de otro usuario.\n\n"
                "Si la borra, esas respuestas pueden quedar sin su nota "
                "principal. Para cerrar normalmente esta conversación se "
                "recomienda usar «Resolver nota».\n\n"
                "¿Aun así desea borrar físicamente su nota inicial?"
            )
        else:
            message = (
                "¿Borrar físicamente la intervención seleccionada?\n\n"
                "Esta acción la eliminará de su Notes_*.xml. "
                "Se creará una copia de seguridad antes de guardar."
            )

        answer = QMessageBox.question(
            self,
            "Borrar nota",
            message,
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.notes_workspace.delete_consultant_message(
                wrapped
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Borrar nota",
                str(exc),
            )
            return

        self._after_internal_file_write()
        self._refresh_threads_for_reference()
        self.statusBar().showMessage(
            "Intervención borrada. Se creó una copia de seguridad.",
            5000,
        )


    def begin_reply(self):
        thread = self.current_interaction_thread
        if (
            not thread
            or not self.notes_workspace
        ):
            return

        self.cancel_new_note(silent=True)
        self.reply_mode = True

        counterpart = thread.counterpart()
        people = self._recipient_people()

        self.reply_recipient_combo.clear()
        self.reply_recipient_combo.addItems(
            people
        )

        idx = self.reply_recipient_combo.findText(
            counterpart,
            Qt.MatchFixedString,
        )
        if idx >= 0:
            self.reply_recipient_combo.setCurrentIndex(
                idx
            )
        else:
            self.reply_recipient_combo.setEditText(
                counterpart
            )

        self.reply_editor.clear()
        self.reply_editor.show()
        self.reply_recipient_label.show()
        self.reply_recipient_combo.show()
        self.save_reply_button.show()
        self.cancel_reply_button.show()
        self.reply_button.hide()

        self.reply_editor.setFocus()


    def cancel_reply(self, silent=False):
        if not self.reply_mode:
            return

        self.reply_mode = False

        self.reply_editor.clear()
        self.reply_editor.hide()
        self.reply_recipient_label.hide()
        self.reply_recipient_combo.hide()
        self.save_reply_button.hide()
        self.cancel_reply_button.hide()
        self.reply_button.show()

        if (
            self.current_interaction_thread
            and not self.current_interaction_thread.resolved_for_consultant()
        ):
            self.reply_button.setEnabled(True)
        else:
            self.reply_button.setEnabled(False)


    def save_reply(self):
        if (
            not self.notes_workspace
            or not self.current_interaction_thread
        ):
            return

        text_value = self.reply_editor.toPlainText().strip()
        if not text_value:
            QMessageBox.warning(
                self,
                "Respuesta",
                "Escriba el contenido de la respuesta.",
            )
            return

        target = (
            self.reply_recipient_combo.currentText().strip()
            or self.current_interaction_thread.counterpart()
            or "Team"
        )

        thread_id = (
            self.current_interaction_thread.thread
        )
        review_next_target = (
            self._next_review_target()
        )

        try:
            self.notes_workspace.append_consultant_reply(
                self.current_interaction_thread,
                text_value,
                target,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Guardar respuesta",
                str(exc),
            )
            return

        self.reply_mode = False
        self._after_internal_file_write()
        self._refresh_threads_for_reference()

        for i in range(
            self.thread_combo.count()
        ):
            if (
                self.thread_combo.itemData(i)
                == thread_id
            ):
                self.thread_combo.setCurrentIndex(
                    i
                )
                break

        self.statusBar().showMessage(
            f"Respuesta guardada en Notes_{self.consultant_name}.xml.",
            5000,
        )
        self._advance_review_after_action(
            review_next_target
        )

    # ------------------------------------------------------------------
    # Consulta bíblica
    # ------------------------------------------------------------------
    def _set_reference_edit(self, text):
        self.reference_edit.lineEdit().setText(text)

    def search_reference(self):
        try:
            reference = parse_reference(
                self.reference_edit.currentText()
            )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Cita bíblica",
                str(exc),
            )
            return

        self.reference_controller.set_reference(
            reference,
            force=True,
        )

    def _reference_changed(self, reference):
        self._set_reference_edit(
            to_spanish_reference(reference)
        )
        self._load_browser(reference)
        self._sync_resource_reference(
            reference
        )

    def _source_changed(self, _index):
        reference = (
            self.reference_controller.reference
        )
        if reference:
            self._load_browser(reference)

    def _load_browser(self, reference):
        url = build_url(
            self.source_combo.currentIndex(),
            reference,
        )
        self.browser.setUrl(QUrl(url))

    def _apply_clean_view(self):
        script = cleanup_javascript(
            self.browser.url().host()
        )
        if script:
            self.browser.page().runJavaScript(
                script
            )

    def _browser_load_finished(self, ok):
        if not ok:
            return

        # Algunas partes de BibleGateway se insertan después de loadFinished.
        # Reaplicamos el modo limpio y el desplazamiento al pasaje unas veces.
        self._apply_clean_view()
        QTimer.singleShot(
            450,
            self._apply_clean_view,
        )
        QTimer.singleShot(
            1200,
            self._apply_clean_view,
        )

    def browser_back(self):
        self.browser.back()

    def browser_forward(self):
        self.browser.forward()

    def browser_reload(self):
        self.browser.reload()

    def open_external(self):
        url = self.browser.url().toString()
        if url:
            webbrowser.open(url)

    # ------------------------------------------------------------------
    # Distribución
    # ------------------------------------------------------------------
    def _restore_layout(self):
        geometry = self.settings.value(
            "v21/geometry"
        )
        state = self.settings.value(
            "v21/state"
        )

        if geometry is not None:
            self.restoreGeometry(geometry)

        if state is not None:
            self.restoreState(state)
        else:
            self.reset_layout()

    def reset_layout(self):
        self.addDockWidget(
            Qt.RightDockWidgetArea,
            self.bible_dock,
        )
        self.addDockWidget(
            Qt.BottomDockWidgetArea,
            self.notes_dock,
        )
        self.addDockWidget(
            Qt.RightDockWidgetArea,
            self.chatgpt_dock,
        )
        self.addDockWidget(
            Qt.RightDockWidgetArea,
            self.note_tools_dock,
        )
        self.addDockWidget(
            Qt.RightDockWidgetArea,
            self.resources_dock,
        )

        self.bible_dock.show()
        self.notes_dock.show()
        self.chatgpt_dock.hide()
        self.note_tools_dock.hide()
        self.resources_dock.hide()

        self.resizeDocks(
            [self.bible_dock],
            [470],
            Qt.Horizontal,
        )
        self.resizeDocks(
            [self.notes_dock],
            [430],
            Qt.Vertical,
        )

    def closeEvent(self, event):
        self._save_project_session()
        self._save_resource_windows()

        self._closing_app = True
        for window in list(
            self.resource_windows
        ):
            try:
                window.close()
            except RuntimeError:
                pass

        self.settings.setValue(
            "v21/geometry",
            self.saveGeometry(),
        )
        self.settings.setValue(
            "v21/state",
            self.saveState(),
        )
        super().closeEvent(event)
