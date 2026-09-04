from __future__ import annotations

from pathlib import Path
import html
import os
import urllib.request

from PySide6.QtCore import (
    Qt,
    Signal,
    QSettings,
    QStandardPaths,
    QThread,
)
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .context_resources import (
    fetch_context_chapter,
    provider_by_key,
    providers_for_group,
    split_reference,
)

from .native_resources import (
    ALL_DATASETS,
    DATASET_FILES,
    DATASET_URLS,
    EXTRA_DATASETS,
    NT_DATASETS,
    NativeResourceStore,
    describe_morphology,
    first_reference,
    normalize_strongs,
)


class NativeInstallWorker(QThread):
    progress = Signal(str, int, int)
    installed = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        data_dir: str | Path,
        db_path: str | Path,
        datasets,
        parent=None,
    ):
        super().__init__(parent)
        self.data_dir = Path(
            data_dir
        )
        self.db_path = Path(
            db_path
        )
        self.datasets = tuple(
            datasets
        )

    def _download(
        self,
        key: str,
        index: int,
        total: int,
    ) -> Path:
        self.data_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        target = (
            self.data_dir
            / DATASET_FILES[key]
        )
        part = target.with_suffix(
            target.suffix
            + ".part"
        )

        request = urllib.request.Request(
            DATASET_URLS[key],
            headers={
                "User-Agent": (
                    "Consultor-App/18 "
                    "(Bible translation consultation tool)"
                )
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=90,
        ) as response:
            expected = int(
                response.headers.get(
                    "Content-Length",
                    "0",
                )
                or 0
            )
            downloaded = 0

            with part.open(
                "wb"
            ) as output:
                while True:
                    chunk = response.read(
                        1024 * 256
                    )
                    if not chunk:
                        break

                    output.write(
                        chunk
                    )
                    downloaded += len(
                        chunk
                    )

                    if expected > 0:
                        file_percent = int(
                            downloaded
                            * 100
                            / expected
                        )
                    else:
                        file_percent = -1

                    label = (
                        f"Descargando {DATASET_FILES[key]} "
                        f"({index}/{total})"
                    )
                    self.progress.emit(
                        label,
                        file_percent,
                        100,
                    )

        part.replace(
            target
        )
        return target

    def run(self):
        try:
            total = len(
                self.datasets
            )
            paths = {}

            for index, key in enumerate(
                self.datasets,
                start=1,
            ):
                self.progress.emit(
                    f"Preparando {DATASET_FILES[key]} "
                    f"({index}/{total})",
                    0,
                    0,
                )
                paths[key] = self._download(
                    key,
                    index,
                    total,
                )

            store = NativeResourceStore(
                self.db_path
            )

            imported = {}

            for index, key in enumerate(
                self.datasets,
                start=1,
            ):
                self.progress.emit(
                    f"Indexando {DATASET_FILES[key]} "
                    f"({index}/{total})",
                    0,
                    0,
                )

                path = paths[key]

                if key in {
                    "sblgnt",
                    "oshb",
                }:
                    count = (
                        store.import_translation_json(
                            path
                        )
                    )

                elif key in {
                    "tokens_greek",
                    "tokens_hebrew",
                }:
                    count = (
                        store.import_tokens_json(
                            path
                        )
                    )

                elif key in {
                    "lexicon_greek",
                    "lexicon_hebrew",
                }:
                    count = (
                        store.import_lexicon_json(
                            path
                        )
                    )

                elif key == "crossrefs":
                    count = (
                        store.import_crossrefs(
                            path
                        )
                    )

                elif key == "topics":
                    count = (
                        store.import_topics_json(
                            path
                        )
                    )

                elif key == "places":
                    count = (
                        store.import_places_jsonl(
                            path
                        )
                    )

                else:
                    count = 0

                imported[key] = count

            if set(
                NT_DATASETS
            ).issubset(
                set(self.datasets)
            ):
                store.set_meta(
                    "nt_installed",
                    "1",
                )

            if set(
                EXTRA_DATASETS
            ).issubset(
                set(self.datasets)
            ):
                store.set_meta(
                    "extras_installed",
                    "1",
                )

            if set(
                ALL_DATASETS
            ).issubset(
                set(self.datasets)
            ):
                store.set_meta(
                    "full_installed",
                    "1",
                )

            self.installed.emit(
                imported
            )

        except Exception as exc:
            self.failed.emit(
                str(exc)
            )


class ContextFetchWorker(QThread):
    loaded = Signal(dict)
    failed = Signal(str, str)

    def __init__(
        self,
        provider_key: str,
        reference: str,
        parent=None,
    ):
        super().__init__(parent)
        self.provider_key = str(
            provider_key
        )
        self.reference = str(
            reference
        )

    def run(self):
        try:
            payload = fetch_context_chapter(
                self.provider_key,
                self.reference,
            )
            self.loaded.emit(
                payload
            )
        except Exception as exc:
            self.failed.emit(
                self.provider_key,
                str(exc),
            )



class ResourcePanelWidget(QWidget):
    new_window_requested = Signal()
    toggle_floating_requested = Signal()
    move_screen_requested = Signal()
    local_folder_requested = Signal()
    use_chatgpt_requested = Signal(str)
    source_changed = Signal(str)
    follow_changed = Signal(bool)
    navigate_reference_requested = Signal(str)

    TAB_KEYS = (
        "notes",
        "commentary",
        "source",
        "lexicon",
        "crossrefs",
        "topics",
        "places",
        "private_notes",
        "info",
    )

    def __init__(
        self,
        settings: QSettings,
        settings_prefix: str,
        parent=None,
        allow_dock_actions: bool = True,
    ):
        super().__init__(parent)
        self.settings = settings
        self.settings_prefix = (
            settings_prefix
        )
        self.allow_dock_actions = bool(
            allow_dock_actions
        )

        base = Path(
            QStandardPaths.writableLocation(
                QStandardPaths.AppDataLocation
            )
        )
        self.native_dir = (
            base
            / "resources"
            / "native"
        )
        self.raw_dir = (
            self.native_dir
            / "raw"
        )
        self.db_path = (
            self.native_dir
            / "native_resources.sqlite3"
        )

        self.store = (
            NativeResourceStore(
                self.db_path
            )
        )
        self.current_reference = ""
        self.fixed_reference = ""
        self.current_word = None
        self.install_worker = None
        self.context_workers = {}
        self._building_ui = True

        self._build_ui()
        self._building_ui = False
        self._restore_settings()
        self._refresh_install_status()

    # --------------------------------------------------------------
    # UI
    # --------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            5, 5, 5, 5
        )
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(4)

        self.follow_checkbox = QCheckBox(
            "🔗 Seguir"
        )
        self.follow_checkbox.setChecked(
            True
        )
        self.follow_checkbox.setToolTip(
            "Sincronizar recursos con el VerseRef activo."
        )
        self.follow_checkbox.toggled.connect(
            self._follow_toggled
        )

        self.reference_label = QLabel(
            "—"
        )
        self.reference_label.setStyleSheet(
            "font-weight: 700; "
            "font-size: 13px;"
        )

        self.install_nt_button = QPushButton(
            "Instalar NT"
        )
        self.install_nt_button.setToolTip(
            "Descargar e indexar texto griego, "
            "morfología, léxico y referencias cruzadas."
        )
        self.install_nt_button.clicked.connect(
            self.install_nt
        )

        self.install_all_button = QPushButton(
            "Instalar todo"
        )
        self.install_all_button.setToolTip(
            "Añadir también texto hebreo, morfología, "
            "léxico del AT, temas y lugares bíblicos."
        )
        self.install_all_button.clicked.connect(
            self.install_all
        )

        self.install_extras_button = QPushButton(
            "Instalar extras"
        )
        self.install_extras_button.setToolTip(
            "Instalar Temas bíblicos de Nave y "
            "Lugares bíblicos de OpenBible.info."
        )
        self.install_extras_button.clicked.connect(
            self.install_extras
        )

        self.more_button = QToolButton()
        self.more_button.setText(
            "⋮"
        )
        self.more_button.clicked.connect(
            self._show_menu
        )

        for button in (
            self.install_nt_button,
            self.install_all_button,
            self.install_extras_button,
        ):
            button.setFixedHeight(
                30
            )

        self.more_button.setFixedSize(
            30,
            30,
        )

        top.addWidget(
            self.follow_checkbox
        )
        top.addWidget(
            self.reference_label,
            1,
        )
        top.addWidget(
            self.install_nt_button
        )
        top.addWidget(
            self.install_all_button
        )
        top.addWidget(
            self.install_extras_button
        )
        top.addWidget(
            self.more_button
        )

        self.status_label = QLabel(
            ""
        )
        self.status_label.setWordWrap(
            True
        )
        self.status_label.setStyleSheet(
            "font-size: 11px; "
            "color: palette(mid);"
        )

        self.progress = QProgressBar()
        self.progress.hide()
        self.progress.setMinimumHeight(
            18
        )

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(
            self._tab_changed
        )

        self._build_notes_tab()
        self._build_commentary_tab()
        self._build_source_tab()
        self._build_lexicon_tab()
        self._build_crossrefs_tab()
        self._build_topics_tab()
        self._build_places_tab()
        self._build_private_notes_tab()
        self._build_info_tab()

        layout.addLayout(
            top
        )
        layout.addWidget(
            self.status_label
        )
        layout.addWidget(
            self.progress
        )
        layout.addWidget(
            self.tabs,
            1,
        )

    def _build_context_tab(
        self,
        *,
        group: str,
        title: str,
    ):
        panel = QWidget()
        layout = QVBoxLayout(
            panel
        )
        layout.setContentsMargins(
            5, 5, 5, 5
        )
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(4)

        provider_combo = QComboBox()
        provider_combo.setMinimumWidth(
            245
        )

        for provider in providers_for_group(
            group
        ):
            provider_combo.addItem(
                provider.label,
                provider.key,
            )

        refresh_button = QPushButton(
            "Actualizar"
        )
        refresh_button.setFixedHeight(
            30
        )

        chatgpt_button = QPushButton(
            "Usar con ChatGPT"
        )
        chatgpt_button.setFixedHeight(
            30
        )

        top.addWidget(
            provider_combo,
            1,
        )
        top.addWidget(
            refresh_button
        )
        top.addWidget(
            chatgpt_button
        )

        info_label = QLabel(
            ""
        )
        info_label.setWordWrap(
            True
        )
        info_label.setStyleSheet(
            "font-size: 10px; color: palette(mid);"
        )

        view = QTextBrowser()
        view.setOpenExternalLinks(
            True
        )

        layout.addLayout(
            top
        )
        layout.addWidget(
            info_label
        )
        layout.addWidget(
            view,
            1,
        )

        self.tabs.addTab(
            panel,
            title,
        )

        provider_combo.currentIndexChanged.connect(
            lambda _index, g=group:
                self._context_provider_changed(
                    g
                )
        )
        refresh_button.clicked.connect(
            lambda _checked=False, g=group:
                self._ensure_context_loaded(
                    g,
                    force=True,
                )
        )
        chatgpt_button.clicked.connect(
            lambda _checked=False, g=group:
                self._context_to_chatgpt(
                    g
                )
        )

        return {
            "panel": panel,
            "combo": provider_combo,
            "view": view,
            "info": info_label,
            "refresh": refresh_button,
            "chatgpt": chatgpt_button,
        }

    def _build_notes_tab(self):
        self.notes_context_ui = (
            self._build_context_tab(
                group="notes",
                title="Notas",
            )
        )

    def _build_commentary_tab(self):
        self.commentary_context_ui = (
            self._build_context_tab(
                group="commentary",
                title="Comentarios",
            )
        )

    def _build_source_tab(self):
        panel = QWidget()
        layout = QVBoxLayout(
            panel
        )
        layout.setContentsMargins(
            5, 5, 5, 5
        )
        layout.setSpacing(4)

        self.original_text = QTextBrowser()
        self.original_text.setMinimumHeight(
            95
        )
        self.original_text.setMaximumHeight(
            165
        )

        self.words_tree = QTreeWidget()
        self.words_tree.setHeaderLabels(
            [
                "#",
                "Palabra",
                "Lema",
                "Glosa EN",
                "Morfología",
                "Strong",
            ]
        )
        self.words_tree.setRootIsDecorated(
            False
        )
        self.words_tree.setAlternatingRowColors(
            True
        )
        self.words_tree.setWordWrap(
            True
        )
        self.words_tree.itemClicked.connect(
            self._word_clicked
        )
        self.words_tree.itemDoubleClicked.connect(
            self._word_double_clicked
        )

        header = self.words_tree.header()
        header.setStretchLastSection(
            False
        )
        header.resizeSection(
            0,
            38,
        )
        header.resizeSection(
            1,
            105,
        )
        header.resizeSection(
            2,
            105,
        )
        header.resizeSection(
            3,
            130,
        )
        header.resizeSection(
            4,
            230,
        )
        header.resizeSection(
            5,
            70,
        )

        help_label = QLabel(
            "Doble clic en una palabra para abrir su entrada léxica."
        )
        help_label.setStyleSheet(
            "font-size: 10px; color: palette(mid);"
        )

        layout.addWidget(
            self.original_text
        )
        layout.addWidget(
            self.words_tree,
            1,
        )
        layout.addWidget(
            help_label
        )

        self.tabs.addTab(
            panel,
            "Texto fuente",
        )

    def _build_lexicon_tab(self):
        panel = QWidget()
        layout = QVBoxLayout(
            panel
        )
        layout.setContentsMargins(
            5, 5, 5, 5
        )
        layout.setSpacing(4)

        self.lexicon_title = QLabel(
            "Seleccione una palabra del texto fuente."
        )
        self.lexicon_title.setStyleSheet(
            "font-size: 15px; "
            "font-weight: 700;"
        )
        self.lexicon_title.setWordWrap(
            True
        )

        self.lexicon_body = QTextBrowser()

        self.lexicon_chatgpt = QPushButton(
            "Usar con ChatGPT"
        )
        self.lexicon_chatgpt.setFixedHeight(
            30
        )
        self.lexicon_chatgpt.clicked.connect(
            self._lexicon_to_chatgpt
        )

        layout.addWidget(
            self.lexicon_title
        )
        layout.addWidget(
            self.lexicon_body,
            1,
        )
        layout.addWidget(
            self.lexicon_chatgpt
        )

        self.tabs.addTab(
            panel,
            "Léxico",
        )

    def _build_crossrefs_tab(self):
        panel = QWidget()
        layout = QVBoxLayout(
            panel
        )
        layout.setContentsMargins(
            5, 5, 5, 5
        )
        layout.setSpacing(4)

        self.crossrefs_tree = QTreeWidget()
        self.crossrefs_tree.setHeaderLabels(
            [
                "Referencia",
                "Peso",
            ]
        )
        self.crossrefs_tree.setRootIsDecorated(
            False
        )
        self.crossrefs_tree.setAlternatingRowColors(
            True
        )
        self.crossrefs_tree.itemDoubleClicked.connect(
            self._crossref_activated
        )
        self.crossrefs_tree.header().setStretchLastSection(
            False
        )
        self.crossrefs_tree.header().resizeSection(
            0,
            180,
        )
        self.crossrefs_tree.header().resizeSection(
            1,
            70,
        )

        button_row = QHBoxLayout()

        self.crossref_go_button = QPushButton(
            "Ir a referencia"
        )
        self.crossref_go_button.setFixedHeight(
            30
        )
        self.crossref_go_button.clicked.connect(
            self._go_selected_crossref
        )

        self.crossref_chatgpt = QPushButton(
            "Usar lista con ChatGPT"
        )
        self.crossref_chatgpt.setFixedHeight(
            30
        )
        self.crossref_chatgpt.clicked.connect(
            self._crossrefs_to_chatgpt
        )

        button_row.addWidget(
            self.crossref_go_button
        )
        button_row.addWidget(
            self.crossref_chatgpt
        )
        button_row.addStretch()

        info = QLabel(
            "El peso corresponde a los votos/relevancia del conjunto "
            "de referencias cruzadas de OpenBible.info."
        )
        info.setWordWrap(
            True
        )
        info.setStyleSheet(
            "font-size: 10px; color: palette(mid);"
        )

        layout.addWidget(
            self.crossrefs_tree,
            1,
        )
        layout.addLayout(
            button_row
        )
        layout.addWidget(
            info
        )

        self.tabs.addTab(
            panel,
            "Referencias",
        )

    def _build_topics_tab(self):
        panel = QWidget()
        layout = QVBoxLayout(
            panel
        )
        layout.setContentsMargins(
            5, 5, 5, 5
        )
        layout.setSpacing(4)

        splitter = QSplitter(
            Qt.Horizontal
        )

        self.topics_tree = QTreeWidget()
        self.topics_tree.setHeaderLabels(
            [
                "Tema",
                "Sección",
            ]
        )
        self.topics_tree.setRootIsDecorated(
            False
        )
        self.topics_tree.setAlternatingRowColors(
            True
        )
        self.topics_tree.itemClicked.connect(
            self._topic_clicked
        )

        self.topic_verses_tree = QTreeWidget()
        self.topic_verses_tree.setHeaderLabels(
            [
                "Referencias del tema",
            ]
        )
        self.topic_verses_tree.setRootIsDecorated(
            False
        )
        self.topic_verses_tree.setAlternatingRowColors(
            True
        )
        self.topic_verses_tree.itemDoubleClicked.connect(
            self._topic_reference_activated
        )

        splitter.addWidget(
            self.topics_tree
        )
        splitter.addWidget(
            self.topic_verses_tree
        )
        splitter.setSizes(
            [
                300,
                230,
            ]
        )

        self.topic_detail_label = QLabel(
            "Temas de Nave asociados con el versículo actual."
        )
        self.topic_detail_label.setWordWrap(
            True
        )
        self.topic_detail_label.setStyleSheet(
            "font-size: 10px; color: palette(mid);"
        )

        self.topic_go_button = QPushButton(
            "Ir a referencia"
        )
        self.topic_go_button.setFixedHeight(
            30
        )
        self.topic_go_button.clicked.connect(
            self._go_selected_topic_reference
        )

        row = QHBoxLayout()
        row.addWidget(
            self.topic_go_button
        )
        row.addStretch()

        layout.addWidget(
            splitter,
            1,
        )
        layout.addLayout(
            row
        )
        layout.addWidget(
            self.topic_detail_label
        )

        self.tabs.addTab(
            panel,
            "Temas",
        )

    def _build_places_tab(self):
        panel = QWidget()
        layout = QVBoxLayout(
            panel
        )
        layout.setContentsMargins(
            5, 5, 5, 5
        )
        layout.setSpacing(4)

        self.places_tree = QTreeWidget()
        self.places_tree.setHeaderLabels(
            [
                "Lugar",
                "Tipo",
                "Estado",
                "Conf.",
            ]
        )
        self.places_tree.setRootIsDecorated(
            False
        )
        self.places_tree.setAlternatingRowColors(
            True
        )
        self.places_tree.itemClicked.connect(
            self._place_clicked
        )

        self.place_detail = QTextBrowser()
        self.place_detail.setMaximumHeight(
            210
        )

        self.place_verses_tree = QTreeWidget()
        self.place_verses_tree.setHeaderLabels(
            [
                "Otras referencias",
            ]
        )
        self.place_verses_tree.setRootIsDecorated(
            False
        )
        self.place_verses_tree.setAlternatingRowColors(
            True
        )
        self.place_verses_tree.itemDoubleClicked.connect(
            self._place_reference_activated
        )

        splitter = QSplitter(
            Qt.Vertical
        )
        splitter.addWidget(
            self.places_tree
        )

        lower = QWidget()
        lower_layout = QVBoxLayout(
            lower
        )
        lower_layout.setContentsMargins(
            0, 0, 0, 0
        )
        lower_layout.addWidget(
            self.place_detail
        )
        lower_layout.addWidget(
            self.place_verses_tree
        )
        splitter.addWidget(
            lower
        )
        splitter.setSizes(
            [
                260,
                300,
            ]
        )

        note = QLabel(
            "Identified = una ubicación principal; disputed = varias "
            "ubicaciones posibles; unknown = ubicación no identificada. "
            "La confianza se conserva como puntuación del conjunto fuente."
        )
        note.setWordWrap(
            True
        )
        note.setStyleSheet(
            "font-size: 10px; color: palette(mid);"
        )

        layout.addWidget(
            splitter,
            1,
        )
        layout.addWidget(
            note
        )

        self.tabs.addTab(
            panel,
            "Lugares",
        )

    def _build_private_notes_tab(self):
        panel = QWidget()
        layout = QVBoxLayout(
            panel
        )
        layout.setContentsMargins(
            5, 5, 5, 5
        )
        layout.setSpacing(4)

        top = QHBoxLayout()

        self.private_import_button = QPushButton(
            "Importar JSON privado…"
        )
        self.private_import_button.setFixedHeight(
            30
        )
        self.private_import_button.clicked.connect(
            self.import_private_notes
        )

        self.private_chatgpt_button = QPushButton(
            "Usar con ChatGPT"
        )
        self.private_chatgpt_button.setFixedHeight(
            30
        )
        self.private_chatgpt_button.clicked.connect(
            self._private_notes_to_chatgpt
        )

        top.addWidget(
            self.private_import_button
        )
        top.addWidget(
            self.private_chatgpt_button
        )
        top.addStretch()

        self.private_notes_view = QTextBrowser()

        note = QLabel(
            "Esta pestaña no distribuye notas comerciales. "
            "Solo muestra archivos que usted importe localmente "
            "y tenga derecho a utilizar."
        )
        note.setWordWrap(
            True
        )
        note.setStyleSheet(
            "font-size: 10px; color: palette(mid);"
        )

        layout.addLayout(
            top
        )
        layout.addWidget(
            self.private_notes_view,
            1,
        )
        layout.addWidget(
            note
        )

        self.tabs.addTab(
            panel,
            "Notas privadas",
        )

    def _build_info_tab(self):
        panel = QWidget()
        layout = QVBoxLayout(
            panel
        )
        layout.setContentsMargins(
            5, 5, 5, 5
        )

        self.info_view = QTextBrowser()
        layout.addWidget(
            self.info_view
        )

        self.tabs.addTab(
            panel,
            "Información",
        )

    # --------------------------------------------------------------
    # Settings / public API kept compatible with resource windows
    # --------------------------------------------------------------
    def _settings_key(
        self,
        name: str,
    ) -> str:
        return (
            f"{self.settings_prefix}/{name}"
        )

    def _restore_settings(self):
        follow = self.settings.value(
            self._settings_key(
                "follow"
            ),
            True,
            type=bool,
        )
        self.follow_checkbox.setChecked(
            follow
        )

        self.fixed_reference = str(
            self.settings.value(
                self._settings_key(
                    "fixed_reference"
                ),
                "",
            )
            or ""
        )

        notes_provider = str(
            self.settings.value(
                self._settings_key(
                    "notes_provider"
                ),
                "darby-translation-notes",
            )
            or "darby-translation-notes"
        )
        notes_index = (
            self.notes_context_ui[
                "combo"
            ].findData(
                notes_provider
            )
        )
        if notes_index >= 0:
            self.notes_context_ui[
                "combo"
            ].setCurrentIndex(
                notes_index
            )

        commentary_provider = str(
            self.settings.value(
                self._settings_key(
                    "commentary_provider"
                ),
                "adam-clarke",
            )
            or "adam-clarke"
        )
        commentary_index = (
            self.commentary_context_ui[
                "combo"
            ].findData(
                commentary_provider
            )
        )
        if commentary_index >= 0:
            self.commentary_context_ui[
                "combo"
            ].setCurrentIndex(
                commentary_index
            )

        tab = str(
            self.settings.value(
                self._settings_key(
                    "tab"
                ),
                "notes",
            )
            or "notes"
        )
        self.set_source(
            tab
        )

    def _save_settings(self):
        self.settings.setValue(
            self._settings_key(
                "follow"
            ),
            self.follow_checkbox.isChecked(),
        )
        self.settings.setValue(
            self._settings_key(
                "fixed_reference"
            ),
            self.fixed_reference,
        )
        self.settings.setValue(
            self._settings_key(
                "tab"
            ),
            self.source_key(),
        )
        if hasattr(
            self,
            "notes_context_ui",
        ):
            self.settings.setValue(
                self._settings_key(
                    "notes_provider"
                ),
                self._context_provider_key(
                    "notes"
                ),
            )

        if hasattr(
            self,
            "commentary_context_ui",
        ):
            self.settings.setValue(
                self._settings_key(
                    "commentary_provider"
                ),
                self._context_provider_key(
                    "commentary"
                ),
            )

    def source_key(self) -> str:
        index = self.tabs.currentIndex()
        if (
            0
            <= index
            < len(self.TAB_KEYS)
        ):
            return self.TAB_KEYS[
                index
            ]
        return "source"

    def set_source(
        self,
        key: str,
    ):
        try:
            index = self.TAB_KEYS.index(
                key
            )
        except ValueError:
            index = 0

        self.tabs.setCurrentIndex(
            index
        )

    def effective_reference(self) -> str:
        if self.follow_checkbox.isChecked():
            return self.current_reference
        return (
            self.fixed_reference
            or self.current_reference
        )

    def set_reference(
        self,
        reference: str,
    ):
        reference = (
            first_reference(
                reference
            )
            or reference
        )
        self.current_reference = (
            reference
            or ""
        )

        if self.follow_checkbox.isChecked():
            self.reference_label.setText(
                self.current_reference
                or "—"
            )
            self.refresh()
        elif not self.fixed_reference:
            self.fixed_reference = (
                self.current_reference
            )
            self.reference_label.setText(
                self.fixed_reference
                or "—"
            )

    def _follow_toggled(
        self,
        checked: bool,
    ):
        if checked:
            self.reference_label.setText(
                self.current_reference
                or "—"
            )
        else:
            self.fixed_reference = (
                self.current_reference
            )
            self.reference_label.setText(
                (
                    self.fixed_reference
                    or "—"
                )
                + "  🔒"
            )

        self._save_settings()
        self.follow_changed.emit(
            checked
        )
        self.refresh()

    def _tab_changed(
        self,
        _index: int,
    ):
        if getattr(
            self,
            "_building_ui",
            False,
        ):
            return

        self._save_settings()
        self.source_changed.emit(
            self.source_key()
        )

        key = self.source_key()
        if key == "notes":
            self._ensure_context_loaded(
                "notes"
            )
        elif key == "commentary":
            self._ensure_context_loaded(
                "commentary"
            )

    # --------------------------------------------------------------
    # Notas y comentarios abiertos
    # --------------------------------------------------------------
    def _context_ui(
        self,
        group: str,
    ):
        if group == "notes":
            return self.notes_context_ui
        return self.commentary_context_ui

    def _context_provider_key(
        self,
        group: str,
    ) -> str:
        ui = self._context_ui(
            group
        )
        return str(
            ui["combo"].currentData()
            or ""
        )

    def _context_provider_changed(
        self,
        group: str,
    ):
        self._save_settings()
        self._render_context_group(
            group
        )

        if self.source_key() == (
            "notes"
            if group == "notes"
            else "commentary"
        ):
            self._ensure_context_loaded(
                group
            )

    def _context_reference_parts(self):
        reference = first_reference(
            self.effective_reference()
        )
        if not reference:
            return (
                "",
                0,
                0,
            )

        try:
            return split_reference(
                reference
            )
        except ValueError:
            return (
                "",
                0,
                0,
            )

    def _render_context_group(
        self,
        group: str,
    ):
        ui = self._context_ui(
            group
        )
        provider_key = (
            self._context_provider_key(
                group
            )
        )

        if not provider_key:
            ui["view"].clear()
            return

        provider = provider_by_key(
            provider_key
        )

        reference = first_reference(
            self.effective_reference()
        )

        ui["info"].setText(
            f"{provider.description} · "
            f"Licencia: {provider.license_name}."
        )

        if not reference:
            ui["view"].setHtml(
                "<p>Seleccione un versículo.</p>"
            )
            return

        book, chapter, _verse = (
            self._context_reference_parts()
        )
        if not book:
            ui["view"].setHtml(
                "<p>No se pudo interpretar la referencia actual.</p>"
            )
            return

        cached = (
            self.store.context_chapter_cached(
                provider_key,
                book,
                chapter,
            )
        )

        if not cached:
            ui["view"].setHtml(
                "<h3>"
                + html.escape(
                    provider.label
                )
                + "</h3>"
                "<p><b>"
                + html.escape(
                    reference
                )
                + "</b></p>"
                "<p>Este capítulo todavía no está en la caché local. "
                "Al abrir esta pestaña Consultor App lo consulta en la "
                "fuente abierta y guarda una copia local para futuras "
                "consultas.</p>"
            )
            return

        rows = (
            self.store.context_notes_for(
                provider_key,
                reference,
            )
        )
        meta = (
            self.store.context_chapter_meta(
                provider_key,
                book,
                chapter,
            )
        )

        parts = [
            "<h3>"
            + html.escape(
                provider.label
            )
            + "</h3>",
            "<p><b>"
            + html.escape(
                reference
            )
            + "</b></p>",
        ]

        if rows:
            for row in rows:
                heading = str(
                    row["heading"]
                    or ""
                ).strip()
                body = str(
                    row["text"]
                    or ""
                ).strip()

                parts.append(
                    "<div style='margin:0 0 14px 0;'>"
                )

                if heading:
                    parts.append(
                        "<b>"
                        + html.escape(
                            heading
                        )
                        + "</b>"
                    )

                parts.append(
                    "<p style='line-height:1.45;'>"
                    + html.escape(
                        body
                    ).replace(
                        "\n",
                        "<br>"
                    )
                    + "</p></div>"
                )
        else:
            parts.append(
                "<p><i>Esta fuente no contiene una nota específica "
                "para este versículo.</i></p>"
            )

        source_url = ""
        license_url = (
            provider.license_url
        )

        if meta is not None:
            source_url = str(
                meta["source_url"]
                or ""
            )
            license_url = str(
                meta["license_url"]
                or license_url
            )

        parts.append(
            "<hr><p style='font-size:10px;'>"
            "<b>Fuente:</b> "
            + html.escape(
                provider.attribution
            )
        )

        if license_url:
            parts.append(
                " · <a href='"
                + html.escape(
                    license_url,
                    quote=True,
                )
                + "'>"
                + html.escape(
                    provider.license_name
                )
                + "</a>"
            )

        if source_url:
            parts.append(
                " · <a href='"
                + html.escape(
                    source_url,
                    quote=True,
                )
                + "'>Fuente consultada</a>"
            )

        parts.append(
            "</p>"
        )

        ui["view"].setHtml(
            "".join(
                parts
            )
        )

    def _ensure_context_loaded(
        self,
        group: str,
        *,
        force: bool = False,
    ):
        reference = first_reference(
            self.effective_reference()
        )
        if not reference:
            return

        provider_key = (
            self._context_provider_key(
                group
            )
        )
        if not provider_key:
            return

        book, chapter, _verse = (
            self._context_reference_parts()
        )
        if not book:
            return

        if (
            not force
            and self.store.context_chapter_cached(
                provider_key,
                book,
                chapter,
            )
        ):
            self._render_context_group(
                group
            )
            return

        worker_key = (
            f"{provider_key}:"
            f"{book}:"
            f"{chapter}"
        )

        existing = self.context_workers.get(
            worker_key
        )
        if (
            existing is not None
            and existing.isRunning()
        ):
            return

        ui = self._context_ui(
            group
        )
        ui["refresh"].setEnabled(
            False
        )
        ui["info"].setText(
            "Consultando la fuente abierta…"
        )

        worker = ContextFetchWorker(
            provider_key,
            reference,
            self,
        )

        self.context_workers[
            worker_key
        ] = worker

        worker.loaded.connect(
            lambda payload, key=worker_key:
                self._context_fetch_finished(
                    payload,
                    key,
                )
        )
        worker.failed.connect(
            lambda provider, message, key=worker_key:
                self._context_fetch_failed(
                    provider,
                    message,
                    key,
                )
        )
        worker.start()

    def _context_fetch_finished(
        self,
        payload: dict,
        worker_key: str,
    ):
        provider_key = str(
            payload.get(
                "provider"
            )
            or ""
        )
        provider = provider_by_key(
            provider_key
        )

        self.store.replace_context_chapter(
            provider_key,
            str(
                payload.get(
                    "book"
                )
                or ""
            ),
            int(
                payload.get(
                    "chapter"
                )
                or 0
            ),
            list(
                payload.get(
                    "notes"
                )
                or []
            ),
            provider_name=str(
                payload.get(
                    "provider_name"
                )
                or provider.label
            ),
            source_url=str(
                payload.get(
                    "source_url"
                )
                or ""
            ),
            license_name=str(
                payload.get(
                    "license_name"
                )
                or provider.license_name
            ),
            license_url=str(
                payload.get(
                    "license_url"
                )
                or provider.license_url
            ),
            fetched_at=str(
                payload.get(
                    "fetched_at"
                )
                or ""
            ),
        )

        self.context_workers.pop(
            worker_key,
            None,
        )

        group = provider.group
        ui = self._context_ui(
            group
        )
        ui["refresh"].setEnabled(
            True
        )

        self._render_context_group(
            group
        )

        # Si una referencia no tiene nota, el capítulo sigue marcado como
        # consultado para no repetir solicitudes innecesariamente.
        count = len(
            payload.get(
                "notes"
            )
            or []
        )

        self.status_label.setText(
            f"{provider.label}: capítulo guardado "
            f"en caché ({count} entrada(s))."
        )

    def _context_fetch_failed(
        self,
        provider_key: str,
        message: str,
        worker_key: str,
    ):
        self.context_workers.pop(
            worker_key,
            None,
        )

        provider = provider_by_key(
            provider_key
        )
        ui = self._context_ui(
            provider.group
        )
        ui["refresh"].setEnabled(
            True
        )
        ui["info"].setText(
            f"No fue posible consultar {provider.label}."
        )
        ui["view"].setHtml(
            "<h3>"
            + html.escape(
                provider.label
            )
            + "</h3>"
            "<p>No se pudo obtener el capítulo desde la fuente abierta.</p>"
            "<p><small>"
            + html.escape(
                message
            )
            + "</small></p>"
            "<p>Los recursos nativos ya instalados siguen funcionando; "
            "puede volver a intentarlo con «Actualizar».</p>"
        )

    def _context_to_chatgpt(
        self,
        group: str,
    ):
        ui = self._context_ui(
            group
        )
        body = (
            ui["view"].toPlainText()
            or ""
        ).strip()

        if not body:
            return

        provider_key = (
            self._context_provider_key(
                group
            )
        )
        provider = provider_by_key(
            provider_key
        )

        payload = (
            (
                "NOTA DE CONTEXTO BÍBLICO"
                if group == "notes"
                else "COMENTARIO BÍBLICO"
            )
            + "\n"
            + f"Fuente: {provider.label}\n"
            + f"Licencia: {provider.license_name}\n"
            + f"Referencia: {self.effective_reference()}\n\n"
            + body
        )

        self.use_chatgpt_requested.emit(
            payload
        )

        # --------------------------------------------------------------
    # Install
    # --------------------------------------------------------------
    def install_nt(self):
        self._start_install(
            NT_DATASETS
        )

    def install_all(self):
        self._start_install(
            ALL_DATASETS
        )

    def install_extras(self):
        self._start_install(
            EXTRA_DATASETS
        )

    def _start_install(
        self,
        datasets,
    ):
        if (
            self.install_worker
            and self.install_worker.isRunning()
        ):
            return

        answer = QMessageBox.question(
            self,
            "Instalar recursos bíblicos abiertos",
            "Consultor App descargará datos estructurados abiertos "
            "desde repositorios públicos y los indexará localmente.\n\n"
            "NT: texto griego, morfología, léxico y referencias cruzadas.\n"
            "Extras: Temas bíblicos de Nave y Lugares de OpenBible.info.\n"
            "Todo: instala NT + hebreo/AT + extras.\n\n"
            "La instalación requiere Internet una sola vez. "
            "Después los recursos funcionan sin conexión.\n\n"
            "¿Continuar?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.install_nt_button.setEnabled(
            False
        )
        self.install_all_button.setEnabled(
            False
        )
        self.install_extras_button.setEnabled(
            False
        )
        self.progress.show()

        self.install_worker = NativeInstallWorker(
            self.raw_dir,
            self.db_path,
            datasets,
            self,
        )
        self.install_worker.progress.connect(
            self._install_progress
        )
        self.install_worker.installed.connect(
            self._install_finished
        )
        self.install_worker.failed.connect(
            self._install_failed
        )
        self.install_worker.start()

    def _install_progress(
        self,
        label: str,
        value: int,
        maximum: int,
    ):
        self.status_label.setText(
            label
        )

        if maximum <= 0:
            self.progress.setRange(
                0,
                0,
            )
        else:
            self.progress.setRange(
                0,
                maximum,
            )
            self.progress.setValue(
                max(
                    0,
                    value,
                )
            )

    def _install_finished(
        self,
        imported: dict,
    ):
        self.install_nt_button.setEnabled(
            True
        )
        self.install_all_button.setEnabled(
            True
        )
        self.install_extras_button.setEnabled(
            True
        )
        self.progress.hide()

        total = sum(
            int(value)
            for value in imported.values()
        )

        self.status_label.setText(
            f"Recursos instalados e indexados: "
            f"{total:,} registros procesados."
        )

        self._refresh_install_status()
        self.refresh()

    def _install_failed(
        self,
        message: str,
    ):
        self.install_nt_button.setEnabled(
            True
        )
        self.install_all_button.setEnabled(
            True
        )
        self.install_extras_button.setEnabled(
            True
        )
        self.progress.hide()

        QMessageBox.warning(
            self,
            "No fue posible instalar los recursos",
            "La descarga o indexación no terminó.\n\n"
            f"{message}\n\n"
            "Los recursos ya instalados no se eliminan. "
            "Puede volver a intentarlo.",
        )

        self._refresh_install_status()

    def _refresh_install_status(self):
        counts = self.store.counts()

        nt_installed = (
            self.store.get_meta(
                "nt_installed"
            )
            == "1"
        )
        full_installed = (
            self.store.get_meta(
                "full_installed"
            )
            == "1"
        )
        extras_installed = (
            self.store.get_meta(
                "extras_installed"
            )
            == "1"
        )

        self.install_nt_button.setVisible(
            not nt_installed
        )
        self.install_extras_button.setVisible(
            not extras_installed
        )
        self.install_all_button.setText(
            (
                "Actualizar todo"
                if full_installed
                else "Instalar todo"
            )
        )

        if self.store.has_native_data():
            self.status_label.setText(
                "Recursos nativos: "
                f"{counts['verses']:,} versos · "
                f"{counts['tokens']:,} palabras etiquetadas · "
                f"{counts['lexicon']:,} entradas léxicas · "
                f"{counts['crossrefs']:,} referencias · "
                f"{counts['topics']:,} temas · "
                f"{counts['places']:,} lugares · "
                f"{counts['context_notes']:,} notas/comentarios en caché."
            )
        else:
            self.status_label.setText(
                "Recursos nativos todavía no instalados. "
                "Puede comenzar con «Instalar NT»."
            )

        self._render_info()

    # --------------------------------------------------------------
    # Display
    # --------------------------------------------------------------
    def refresh(self):
        reference = (
            self.effective_reference()
        )
        self.reference_label.setText(
            (
                reference
                or "—"
            )
            + (
                ""
                if self.follow_checkbox.isChecked()
                else "  🔒"
            )
        )

        self._render_context_group(
            "notes"
        )
        self._render_context_group(
            "commentary"
        )

        self._render_source(
            reference
        )
        self._render_crossrefs(
            reference
        )
        self._render_topics(
            reference
        )
        self._render_places(
            reference
        )
        self._render_private_notes(
            reference
        )
        self._render_info()

        if self.source_key() == "notes":
            self._ensure_context_loaded(
                "notes"
            )
        elif self.source_key() == "commentary":
            self._ensure_context_loaded(
                "commentary"
            )

    def _render_source(
        self,
        reference: str,
    ):
        self.words_tree.clear()
        self.current_word = None

        if not reference:
            self.original_text.setHtml(
                "<p>Seleccione un versículo.</p>"
            )
            return

        row = self.store.verse_text(
            reference
        )
        words = self.store.words_for_verse(
            reference
        )

        if row:
            direction = row["direction"]
            text = html.escape(
                row["text"]
            )
            if direction == "rtl":
                rendered = (
                    "<div dir='rtl' "
                    "style='font-size:23px; "
                    "line-height:1.8; "
                    "text-align:right;'>"
                    f"{text}</div>"
                )
            else:
                rendered = (
                    "<div style='font-size:21px; "
                    "line-height:1.7;'>"
                    f"{text}</div>"
                )

            self.original_text.setHtml(
                rendered
            )
        else:
            self.original_text.setHtml(
                "<p><b>No hay texto fuente instalado "
                f"para {html.escape(reference)}.</b></p>"
                "<p>Si es AT, instale «Todo»; "
                "si es NT, instale los recursos NT.</p>"
            )

        for word in words:
            morphology = (
                describe_morphology(
                    word.morph_code
                )
            )
            item = QTreeWidgetItem(
                [
                    str(word.position),
                    word.surface_form,
                    word.lemma,
                    word.gloss,
                    morphology,
                    word.strongs_id,
                ]
            )
            item.setData(
                0,
                Qt.UserRole,
                word,
            )
            item.setToolTip(
                4,
                word.morph_code,
            )
            self.words_tree.addTopLevelItem(
                item
            )

        if words:
            self.words_tree.setCurrentItem(
                self.words_tree.topLevelItem(
                    0
                )
            )
            self._show_word(
                words[0]
            )
        else:
            self.lexicon_title.setText(
                "Sin análisis morfológico para esta referencia."
            )
            self.lexicon_body.clear()

    def _word_clicked(
        self,
        item,
        _column,
    ):
        word = item.data(
            0,
            Qt.UserRole,
        )
        if word is not None:
            self._show_word(
                word
            )

    def _word_double_clicked(
        self,
        item,
        _column,
    ):
        word = item.data(
            0,
            Qt.UserRole,
        )
        if word is None:
            return

        self._show_word(
            word
        )
        self.tabs.setCurrentIndex(
            1
        )

    def _show_word(
        self,
        word,
    ):
        self.current_word = word

        title_parts = [
            word.surface_form,
        ]
        if word.lemma:
            title_parts.append(
                word.lemma
            )
        if word.strongs_id:
            title_parts.append(
                word.strongs_id
            )

        self.lexicon_title.setText(
            " · ".join(
                part
                for part in title_parts
                if part
            )
        )

        morphology = (
            describe_morphology(
                word.morph_code
            )
        )

        parts = []

        if word.transliteration:
            parts.append(
                "<p><b>Transliteración:</b> "
                + html.escape(
                    word.transliteration
                )
                + "</p>"
            )

        if word.gloss:
            parts.append(
                "<p><b>Glosa (inglés):</b> "
                + html.escape(
                    word.gloss
                )
                + "</p>"
            )

        if morphology:
            parts.append(
                "<p><b>Morfología:</b> "
                + html.escape(
                    morphology
                )
                + "</p>"
            )

        if word.definition:
            parts.append(
                "<hr><p><b>Definición léxica "
                "(fuente en inglés):</b></p>"
                "<p>"
                + html.escape(
                    word.definition
                ).replace(
                    "\n",
                    "<br>"
                )
                + "</p>"
            )

        if not parts:
            parts.append(
                "<p>No hay una entrada léxica "
                "disponible para esta palabra.</p>"
            )

        self.lexicon_body.setHtml(
            "".join(parts)
        )

    def _render_crossrefs(
        self,
        reference: str,
    ):
        self.crossrefs_tree.clear()

        if not reference:
            return

        rows = self.store.crossrefs_for(
            reference,
            limit=100,
        )

        for row in rows:
            item = QTreeWidgetItem(
                [
                    row["to_ref"],
                    str(
                        row["votes"]
                    ),
                ]
            )
            item.setData(
                0,
                Qt.UserRole,
                row["to_ref"],
            )
            self.crossrefs_tree.addTopLevelItem(
                item
            )

    def _crossref_activated(
        self,
        item,
        _column,
    ):
        reference = item.data(
            0,
            Qt.UserRole,
        )
        if reference:
            self.navigate_reference_requested.emit(
                self._first_target_reference(
                    reference
                )
            )

    def _first_target_reference(
        self,
        reference: str,
    ) -> str:
        reference = (
            reference
            or ""
        )
        if " – " in reference:
            reference = reference.split(
                " – ",
                1,
            )[0]
        return first_reference(
            reference
        )

    def _go_selected_crossref(self):
        item = (
            self.crossrefs_tree.currentItem()
        )
        if item is not None:
            self._crossref_activated(
                item,
                0,
            )

    def _render_topics(
        self,
        reference: str,
    ):
        self.topics_tree.clear()
        self.topic_verses_tree.clear()
        self.topic_detail_label.setText(
            "Temas de Nave asociados con el versículo actual."
        )

        if not reference:
            return

        rows = self.store.topics_for(
            reference
        )

        for row in rows:
            item = QTreeWidgetItem(
                [
                    row["name"],
                    row["section"],
                ]
            )
            item.setData(
                0,
                Qt.UserRole,
                row["topic_id"],
            )
            item.setData(
                1,
                Qt.UserRole,
                row["see_also"],
            )
            self.topics_tree.addTopLevelItem(
                item
            )

        if rows:
            first = self.topics_tree.topLevelItem(
                0
            )
            self.topics_tree.setCurrentItem(
                first
            )
            self._topic_clicked(
                first,
                0,
            )

    def _topic_clicked(
        self,
        item,
        _column,
    ):
        topic_id = item.data(
            0,
            Qt.UserRole,
        )
        if not topic_id:
            return

        self.topic_verses_tree.clear()
        rows = self.store.topic_verses(
            str(topic_id),
            limit=300,
        )

        for row in rows:
            reference = row["reference"]
            child = QTreeWidgetItem(
                [
                    reference,
                ]
            )
            child.setData(
                0,
                Qt.UserRole,
                reference,
            )
            self.topic_verses_tree.addTopLevelItem(
                child
            )

        see_also = str(
            item.data(
                1,
                Qt.UserRole,
            )
            or ""
        )
        if see_also:
            self.topic_detail_label.setText(
                f"{len(rows)} referencia(s). "
                f"Véase también: {see_also}"
            )
        else:
            self.topic_detail_label.setText(
                f"{len(rows)} referencia(s) en este tema."
            )

    def _topic_reference_activated(
        self,
        item,
        _column,
    ):
        reference = item.data(
            0,
            Qt.UserRole,
        )
        if reference:
            self.navigate_reference_requested.emit(
                first_reference(
                    str(reference)
                )
            )

    def _go_selected_topic_reference(self):
        item = self.topic_verses_tree.currentItem()
        if item is not None:
            self._topic_reference_activated(
                item,
                0,
            )

    def _render_places(
        self,
        reference: str,
    ):
        self.places_tree.clear()
        self.place_verses_tree.clear()
        self.place_detail.clear()

        if not reference:
            return

        rows = self.store.places_for(
            reference
        )

        labels = {
            "identified": "Identificado",
            "disputed": "Discutido",
            "unknown": "Desconocido",
        }

        for row in rows:
            item = QTreeWidgetItem(
                [
                    row["name"],
                    row["place_type"],
                    labels.get(
                        row["status"],
                        row["status"],
                    ),
                    str(
                        row["confidence"]
                    ),
                ]
            )
            item.setData(
                0,
                Qt.UserRole,
                row["place_id"],
            )
            item.setData(
                1,
                Qt.UserRole,
                dict(row),
            )
            self.places_tree.addTopLevelItem(
                item
            )

        if rows:
            first = self.places_tree.topLevelItem(
                0
            )
            self.places_tree.setCurrentItem(
                first
            )
            self._place_clicked(
                first,
                0,
            )
        else:
            self.place_detail.setHtml(
                "<p>No hay lugares indexados "
                "para esta referencia.</p>"
            )

    def _place_clicked(
        self,
        item,
        _column,
    ):
        place_id = item.data(
            0,
            Qt.UserRole,
        )
        row = item.data(
            1,
            Qt.UserRole,
        )
        if not (
            place_id
            and isinstance(row, dict)
        ):
            return

        longitude = row.get(
            "longitude"
        )
        latitude = row.get(
            "latitude"
        )

        coordinates = "—"
        if (
            longitude is not None
            and latitude is not None
        ):
            coordinates = (
                f"{float(latitude):.5f}, "
                f"{float(longitude):.5f}"
            )

        description = html.escape(
            str(
                row.get("description")
                or ""
            )
        )

        self.place_detail.setHtml(
            "<h3>"
            + html.escape(
                str(
                    row.get("name")
                    or ""
                )
            )
            + "</h3>"
            "<p><b>Tipo:</b> "
            + html.escape(
                str(
                    row.get("place_type")
                    or "—"
                )
            )
            + "<br><b>Estado:</b> "
            + html.escape(
                str(
                    row.get("status")
                    or "—"
                )
            )
            + "<br><b>Confianza:</b> "
            + html.escape(
                str(
                    row.get("confidence")
                    or 0
                )
            )
            + "<br><b>Coordenadas:</b> "
            + html.escape(
                coordinates
            )
            + "</p>"
            + (
                "<p>"
                + description
                + "</p>"
                if description
                else ""
            )
        )

        self.place_verses_tree.clear()
        for verse_row in self.store.place_verses(
            str(place_id),
            limit=300,
        ):
            reference = verse_row[
                "reference"
            ]
            child = QTreeWidgetItem(
                [
                    reference,
                ]
            )
            child.setData(
                0,
                Qt.UserRole,
                reference,
            )
            self.place_verses_tree.addTopLevelItem(
                child
            )

    def _place_reference_activated(
        self,
        item,
        _column,
    ):
        reference = item.data(
            0,
            Qt.UserRole,
        )
        if reference:
            self.navigate_reference_requested.emit(
                first_reference(
                    str(reference)
                )
            )

    def _render_private_notes(
        self,
        reference: str,
    ):
        rows = self.store.private_notes_for(
            reference
        )

        if not rows:
            self.private_notes_view.setHtml(
                "<p>No hay notas privadas importadas "
                "para esta referencia.</p>"
            )
            return

        parts = []
        for row in rows:
            note_type = (
                row["note_type"]
                or "nota"
            )
            marker = (
                row["marker"]
                or ""
            )
            parts.append(
                "<div style='margin-bottom:12px;'>"
                "<b>"
                + html.escape(
                    note_type
                )
                + (
                    " · "
                    + html.escape(
                        marker
                    )
                    if marker
                    else ""
                )
                + "</b>"
                "<p>"
                + html.escape(
                    row["text"]
                ).replace(
                    "\n",
                    "<br>"
                )
                + "</p></div>"
            )

        self.private_notes_view.setHtml(
            "".join(
                parts
            )
        )

    def import_private_notes(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar notas privadas",
            str(Path.home()),
            "JSON (*.json);;Todos los archivos (*)",
        )
        if not path:
            return

        try:
            count = (
                self.store.import_private_notes_json(
                    path
                )
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Notas privadas",
                f"No se pudo importar el archivo.\n\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Notas privadas",
            f"Se importaron {count} nota(s).\n\n"
            "El archivo original permanece local y no "
            "se incorpora al paquete de Consultor App.",
        )
        self.refresh()

    def _render_info(self):
        counts = self.store.counts()

        self.info_view.setHtml(
            """
            <h3>Recursos bíblicos nativos</h3>

            <p>Estos recursos se descargan una vez, se indexan en SQLite y
            después funcionan sin navegador web.</p>

            <h4>Texto fuente, morfología y léxico</h4>
            <p>Datos derivados de STEPBible-Data, creados por STEPBible.org
            con base en trabajo de Tyndale House Cambridge. Los conjuntos
            utilizados están publicados bajo CC BY 4.0. El NT usa selección
            de palabras SBLGNT y el AT deriva de OpenScriptures/WLC a través
            de los datos de STEPBible.</p>

            <h4>Referencias cruzadas</h4>
            <p>Datos de OpenBible.info, publicados bajo licencia CC BY.</p>

            <h4>Temas bíblicos</h4>
            <p>Nave's Topical Bible (1897, dominio público), mediante una
            compilación estructurada CC BY 4.0. Permite ver qué temas están
            asociados con el versículo y navegar por las referencias de cada
            tema.</p>

            <h4>Lugares bíblicos</h4>
            <p>OpenBible.info Bible Geocoding Data, CC BY 4.0. Consultor App
            conserva nombre, tipo, estado de identificación, coordenadas cuando
            existen y una puntuación de confianza sin convertirla
            artificialmente en porcentaje.</p>

            <h4>Notas abiertas</h4>
            <p><b>Darby Translation Notes</b>: notas históricas de traducción
            en dominio público. Se consultan por capítulo y se almacenan en
            caché local. <b>Tyndale Open Study Notes</b>: notas modernas de
            estudio y contexto bajo CC BY-SA 4.0. Consultor App las identifica
            como notas de estudio, no como notas de traducción.</p>

            <h4>Comentarios abiertos</h4>
            <p>Adam Clarke, Jamieson-Fausset-Brown, John Calvin, John Gill,
            Keil &amp; Delitzsch y Matthew Henry se consultan mediante la
            Free Use Bible API de HelloAO. Las fichas de la API identifican
            estos textos como dominio público. Consultor App guarda únicamente
            capítulos ya consultados para poder reutilizarlos sin volver a
            descargarlos.</p>

            <h4>Idioma</h4>
            <p>Consultor App presenta la morfología con etiquetas básicas en
            español. Las glosas y definiciones léxicas de los conjuntos
            instalados actualmente proceden de fuentes en inglés y se
            identifican explícitamente como tales.</p>

            <h4>Notas privadas</h4>
            <p>Consultor App no incluye notas comerciales. La pestaña
            «Notas privadas» permite cargar localmente un JSON que el usuario
            tenga derecho a utilizar.</p>

            <hr>
            <p><b>Instalado actualmente</b><br>
            Versos fuente: {verses:,}<br>
            Palabras etiquetadas: {tokens:,}<br>
            Entradas léxicas: {lexicon:,}<br>
            Referencias cruzadas: {crossrefs:,}<br>
            Temas: {topics:,}<br>
            Enlaces tema-versículo: {topic_verses:,}<br>
            Lugares: {places:,}<br>
            Enlaces lugar-versículo: {place_verses:,}<br>
            Capítulos de notas/comentarios en caché: {context_chapters:,}<br>
            Entradas de notas/comentarios en caché: {context_notes:,}<br>
            Notas privadas: {private_notes:,}</p>
            """.format(
                **counts
            )
        )

    # --------------------------------------------------------------
    # ChatGPT
    # --------------------------------------------------------------
    def _lexicon_to_chatgpt(self):
        if self.current_word is None:
            return

        word = self.current_word
        body = (
            "ANÁLISIS DEL TEXTO FUENTE\n"
            f"Referencia: {self.effective_reference()}\n"
            f"Palabra: {word.surface_form}\n"
            f"Lema: {word.lemma}\n"
            f"Strong: {word.strongs_id}\n"
            f"Transliteración: {word.transliteration}\n"
            f"Glosa EN: {word.gloss}\n"
            f"Morfología: {describe_morphology(word.morph_code)}\n"
            f"Código morfológico: {word.morph_code}\n\n"
            f"Definición EN:\n{word.definition}"
        )
        self.use_chatgpt_requested.emit(
            body
        )

    def _crossrefs_to_chatgpt(self):
        lines = []
        for index in range(
            self.crossrefs_tree.topLevelItemCount()
        ):
            item = (
                self.crossrefs_tree.topLevelItem(
                    index
                )
            )
            lines.append(
                f"- {item.text(0)} "
                f"(peso {item.text(1)})"
            )

        body = (
            "REFERENCIAS CRUZADAS\n"
            f"Referencia base: {self.effective_reference()}\n\n"
            + "\n".join(
                lines[:50]
            )
        )
        self.use_chatgpt_requested.emit(
            body
        )

    def _private_notes_to_chatgpt(self):
        text = (
            self.private_notes_view.toPlainText()
            or ""
        ).strip()
        if not text:
            return

        self.use_chatgpt_requested.emit(
            "NOTAS PRIVADAS\n"
            f"Referencia: {self.effective_reference()}\n\n"
            + text
        )

    # --------------------------------------------------------------
    # Menu / compatibility
    # --------------------------------------------------------------
    def _show_menu(self):
        menu = self.more_button.menu()
        if menu is None:
            from PySide6.QtWidgets import QMenu
            menu = QMenu(self)

        menu.clear()

        if self.allow_dock_actions:
            floating = QAction(
                "Acoplar / hacer flotante",
                menu,
            )
            floating.triggered.connect(
                self.toggle_floating_requested.emit
            )
            menu.addAction(
                floating
            )

        screen = QAction(
            "Mover a otra pantalla",
            menu,
        )
        screen.triggered.connect(
            self.move_screen_requested.emit
        )
        menu.addAction(
            screen
        )

        extra = QAction(
            "Nueva ventana de recurso",
            menu,
        )
        extra.triggered.connect(
            self.new_window_requested.emit
        )
        menu.addAction(
            extra
        )

        menu.addSeparator()

        install_nt = QAction(
            "Instalar / actualizar recursos NT",
            menu,
        )
        install_nt.triggered.connect(
            self.install_nt
        )
        menu.addAction(
            install_nt
        )

        install_all = QAction(
            "Instalar / actualizar todos los recursos",
            menu,
        )
        install_all.triggered.connect(
            self.install_all
        )
        menu.addAction(
            install_all
        )

        install_extras = QAction(
            "Instalar / actualizar Temas y Lugares",
            menu,
        )
        install_extras.triggered.connect(
            self.install_extras
        )
        menu.addAction(
            install_extras
        )

        private_notes = QAction(
            "Importar notas privadas JSON…",
            menu,
        )
        private_notes.triggered.connect(
            self.import_private_notes
        )
        menu.addAction(
            private_notes
        )

        menu.exec(
            self.more_button.mapToGlobal(
                self.more_button.rect().bottomLeft()
            )
        )

    def choose_local_folder(
        self,
        parent=None,
    ):
        # Compatibilidad con v17: ahora el recurso local relevante son notas
        # privadas estructuradas, no una carpeta web.
        self.import_private_notes()
        return True


class ResourceFloatingWindow(QWidget):
    closed = Signal(object)

    def __init__(
        self,
        settings: QSettings,
        settings_prefix: str,
        parent=None,
    ):
        super().__init__(
            parent,
            Qt.Window,
        )
        self.setWindowTitle(
            "Consultor App · Recursos nativos"
        )
        self.resize(
            760,
            760,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            0, 0, 0, 0
        )

        self.panel = ResourcePanelWidget(
            settings,
            settings_prefix,
            self,
            allow_dock_actions=False,
        )
        layout.addWidget(
            self.panel
        )

    def closeEvent(
        self,
        event,
    ):
        self.closed.emit(
            self
        )
        super().closeEvent(
            event
        )
