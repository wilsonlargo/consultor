from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path
import hashlib
import importlib
import glob
import subprocess
import sys

from PySide6.QtCore import (
    QObject,
    Qt,
    QSettings,
    QStandardPaths,
    QThread,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QPlainTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .spellcheck_core import (
    WordListBackend,
    iter_spell_tokens,
    load_plain_wordlist,
)


LANGUAGES = (
    ("es", "Español"),
    ("en", "English"),
    ("fr", "Français"),
    ("pt", "Português"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("eu", "Euskara"),
    ("nl", "Nederlands"),
    ("ru", "Русский"),
    ("ar", "العربية"),
    ("lv", "Latviešu"),
    ("fa", "فارسی"),
    ("custom", "Diccionario personalizado"),
)

LANGUAGE_LABELS = dict(
    LANGUAGES
)

SYSTEM_DICTIONARY_PATTERNS = {
    "es": ("es_ES.dic", "es_*.dic"),
    "en": ("en_US.dic", "en_*.dic"),
    "fr": ("fr_FR.dic", "fr_*.dic"),
    "pt": ("pt_PT.dic", "pt_BR.dic", "pt_*.dic"),
    "de": ("de_DE.dic", "de_*.dic"),
    "it": ("it_IT.dic", "it_*.dic"),
    "eu": ("eu_ES.dic", "eu_*.dic"),
    "nl": ("nl_NL.dic", "nl_*.dic"),
    "ru": ("ru_RU.dic", "ru_*.dic"),
    "ar": ("ar.dic", "ar_*.dic"),
}

SYSTEM_DICTIONARY_DIRS = (
    "/usr/share/hunspell",
    "/usr/share/myspell",
    "/usr/share/myspell/dicts",
    "/usr/local/share/hunspell",
)


def _find_system_dictionary(
    language: str,
) -> Path | None:
    patterns = SYSTEM_DICTIONARY_PATTERNS.get(
        language,
        (),
    )

    for directory in SYSTEM_DICTIONARY_DIRS:
        for pattern in patterns:
            matches = sorted(
                glob.glob(
                    str(
                        Path(directory)
                        / pattern
                    )
                )
            )
            if matches:
                return Path(
                    matches[0]
                )

    return None


def _load_pyspellchecker(
    language: str,
):
    try:
        from spellchecker import SpellChecker
    except Exception:
        return None

    try:
        checker = SpellChecker(
            language=language,
            distance=2,
        )
    except Exception:
        return None

    return checker


class SpellDependencyInstaller(QThread):
    finished_install = Signal(bool, str)

    def run(self):
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "pyspellchecker>=0.8.2",
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )

            if process.returncode != 0:
                message = (
                    process.stderr.strip()
                    or process.stdout.strip()
                    or "pip terminó con error."
                )
                self.finished_install.emit(
                    False,
                    message[-3000:],
                )
                return

            importlib.invalidate_caches()

            self.finished_install.emit(
                True,
                (
                    process.stdout.strip()
                    or "pyspellchecker instalado."
                )[-3000:],
            )

        except Exception as exc:
            self.finished_install.emit(
                False,
                str(exc),
            )



class SpellCheckerManager(QObject):
    changed = Signal()
    status_changed = Signal(str)

    def __init__(
        self,
        settings: QSettings,
        parent=None,
    ):
        super().__init__(
            parent
        )
        self.settings = settings
        self.project_key = ""
        self.session_ignored = set()

        self.enabled = self.settings.value(
            "spellcheck/enabled",
            True,
            type=bool,
        )

        self.language = str(
            self.settings.value(
                "spellcheck/default_language",
                "es",
            )
            or "es"
        )

        self.custom_backend = None
        self.custom_dictionary_name = ""
        self.system_backend = None
        self.system_dictionary_name = ""
        self._checker = None

        self._load_backend()

    # ----------------------------------------------------------
    # Settings
    # ----------------------------------------------------------
    def _project_hash(
        self,
    ) -> str:
        if not self.project_key:
            return "global"

        return hashlib.sha1(
            self.project_key.encode(
                "utf-8"
            )
        ).hexdigest()[:16]

    def _project_setting(
        self,
        name: str,
    ) -> str:
        return (
            "spellcheck/projects/"
            f"{self._project_hash()}/"
            f"{name}"
        )

    def set_project_key(
        self,
        project_key: str,
    ):
        self.project_key = str(
            project_key
            or ""
        )
        self.session_ignored.clear()

        project_language = str(
            self.settings.value(
                self._project_setting(
                    "language"
                ),
                "",
            )
            or ""
        )

        if project_language:
            self.language = (
                project_language
            )

        self._load_backend()
        self.changed.emit()

    def set_enabled(
        self,
        enabled: bool,
    ):
        self.enabled = bool(
            enabled
        )
        self.settings.setValue(
            "spellcheck/enabled",
            self.enabled,
        )
        self.changed.emit()

    def set_language(
        self,
        language: str,
    ):
        language = str(
            language
            or ""
        ).strip()

        if language not in LANGUAGE_LABELS:
            return

        self.language = language

        self.settings.setValue(
            "spellcheck/default_language",
            language,
        )

        if self.project_key:
            self.settings.setValue(
                self._project_setting(
                    "language"
                ),
                language,
            )

        self.custom_backend = None
        self.custom_dictionary_name = ""
        self._load_backend()
        self.changed.emit()

    def personal_words(
        self,
    ) -> set[str]:
        raw = self.settings.value(
            "spellcheck/personal_words",
            [],
        )

        if isinstance(
            raw,
            str,
        ):
            raw = (
                [raw]
                if raw
                else []
            )

        return {
            str(word).strip().casefold()
            for word in (
                raw
                if isinstance(
                    raw,
                    (list, tuple),
                )
                else []
            )
            if str(word).strip()
        }

    def project_words(
        self,
    ) -> set[str]:
        raw = self.settings.value(
            self._project_setting(
                "words"
            ),
            [],
        )

        if isinstance(
            raw,
            str,
        ):
            raw = (
                [raw]
                if raw
                else []
            )

        return {
            str(word).strip().casefold()
            for word in (
                raw
                if isinstance(
                    raw,
                    (list, tuple),
                )
                else []
            )
            if str(word).strip()
        }

    def add_personal_word(
        self,
        word: str,
    ):
        word = str(
            word
        ).strip().casefold()

        if not word:
            return

        words = self.personal_words()
        words.add(
            word
        )

        self.settings.setValue(
            "spellcheck/personal_words",
            sorted(
                words
            ),
        )

        self._clear_caches()
        self.changed.emit()

    def add_project_word(
        self,
        word: str,
    ):
        word = str(
            word
        ).strip().casefold()

        if not word:
            return

        words = self.project_words()
        words.add(
            word
        )

        self.settings.setValue(
            self._project_setting(
                "words"
            ),
            sorted(
                words
            ),
        )

        self._clear_caches()
        self.changed.emit()

    def ignore_for_session(
        self,
        word: str,
    ):
        word = str(
            word
        ).strip().casefold()

        if word:
            self.session_ignored.add(
                word
            )
            self._clear_caches()
            self.changed.emit()

    def clear_session_ignored(
        self,
    ):
        self.session_ignored.clear()
        self._clear_caches()
        self.changed.emit()

    # ----------------------------------------------------------
    # Backends
    # ----------------------------------------------------------
    def _load_backend(self):
        self._checker = None
        self.custom_backend = None
        self.custom_dictionary_name = ""
        self.system_backend = None
        self.system_dictionary_name = ""

        if self.language == "custom":
            custom_path = str(
                self.settings.value(
                    self._project_setting(
                        "custom_dictionary_path"
                    ),
                    "",
                )
                or ""
            )
            if (
                custom_path
                and Path(custom_path).exists()
            ):
                try:
                    words = load_plain_wordlist(
                        custom_path
                    )
                except Exception:
                    words = set()

                if words:
                    self.custom_backend = WordListBackend(
                        words
                    )
                    self.custom_dictionary_name = (
                        Path(custom_path).stem
                    )
        else:
            self._checker = (
                _load_pyspellchecker(
                    self.language
                )
            )

            if self._checker is None:
                system_path = _find_system_dictionary(
                    self.language
                )
                if system_path is not None:
                    try:
                        words = load_plain_wordlist(
                            system_path
                        )
                    except Exception:
                        words = set()

                    if words:
                        self.system_backend = WordListBackend(
                            words
                        )
                        self.system_dictionary_name = (
                            system_path.name
                        )

        self._clear_caches()
        self.status_changed.emit(
            self.status_text()
        )

    def _clear_caches(self):
        try:
            self._lookup_cached.cache_clear()
            self._suggest_cached.cache_clear()
        except Exception:
            pass

    def backend_ready(self) -> bool:
        return bool(
            self._checker is not None
            or self.custom_backend is not None
            or self.system_backend is not None
        )

    def reload_backend(self):
        self._load_backend()
        self.changed.emit()

    def status_text(self) -> str:
        label = LANGUAGE_LABELS.get(
            self.language,
            self.language,
        )

        if self.custom_backend:
            return (
                f"Ortografía: "
                f"{self.custom_dictionary_name} ✓"
            )

        if self.language == "custom":
            return (
                "Ortografía: diccionario personalizado no configurado."
            )

        if self._checker is not None:
            return (
                f"Ortografía: {label} ✓"
            )

        if self.system_backend is not None:
            return (
                f"Ortografía: {label} ✓ "
                f"(diccionario del sistema: {self.system_dictionary_name})"
            )

        return (
            f"Ortografía {label}: SIN DICCIONARIO. "
            "Instale el diccionario integrado desde ⚙."
        )

    def language_options(self):
        return list(
            LANGUAGES
        )

    @lru_cache(
        maxsize=8192
    )
    def _lookup_cached(
        self,
        key: str,
    ) -> bool:
        if not key:
            return True

        if key in self.session_ignored:
            return True

        if key in self.personal_words():
            return True

        if key in self.project_words():
            return True

        if (
            self.custom_backend
            and self.custom_backend.lookup(
                key
            )
        ):
            return True

        if (
            self.system_backend
            and self.system_backend.lookup(
                key
            )
        ):
            return True

        if self._checker is None:
            # Sin un diccionario base no marcamos todo como error.
            return True

        try:
            return (
                key
                in self._checker
            )
        except Exception:
            return True

    def check(
        self,
        word: str,
    ) -> bool:
        if not self.enabled:
            return True

        key = str(
            word
        ).strip().casefold()

        return self._lookup_cached(
            key
        )

    @lru_cache(
        maxsize=2048
    )
    def _suggest_cached(
        self,
        key: str,
    ) -> tuple[str, ...]:
        suggestions = []

        if self.custom_backend:
            suggestions.extend(
                self.custom_backend.suggest(
                    key,
                    limit=6,
                )
            )

        if self.system_backend:
            suggestions.extend(
                self.system_backend.suggest(
                    key,
                    limit=6,
                )
            )

        if self._checker is not None:
            try:
                candidates = (
                    self._checker.candidates(
                        key
                    )
                    or set()
                )

                # pyspellchecker no garantiza el orden de candidates.
                # correction() sí prioriza su mejor candidato.
                best = self._checker.correction(
                    key
                )

                if (
                    best
                    and best != key
                ):
                    suggestions.append(
                        best
                    )

                suggestions.extend(
                    sorted(
                        str(value)
                        for value in candidates
                        if str(value) != key
                    )
                )
            except Exception:
                pass

        result = []
        seen = set()

        for candidate in suggestions:
            candidate = str(
                candidate
            ).strip()

            if (
                not candidate
                or candidate.casefold()
                in seen
            ):
                continue

            seen.add(
                candidate.casefold()
            )
            result.append(
                candidate
            )

            if len(result) >= 6:
                break

        return tuple(
            result
        )

    def suggestions(
        self,
        word: str,
    ) -> list[str]:
        source = str(
            word
        ).strip()

        if not source:
            return []

        result = list(
            self._suggest_cached(
                source.casefold()
            )
        )

        if source[:1].isupper():
            result = [
                (
                    item[:1].upper()
                    + item[1:]
                )
                if item
                else item
                for item in result
            ]

        return result

    # ----------------------------------------------------------
    # Additional dictionaries / word lists
    # ----------------------------------------------------------
    def import_wordlist(
        self,
        path: str | Path,
    ) -> int:
        path = Path(path)

        words = load_plain_wordlist(
            path
        )

        if not words:
            return 0

        # Importar como vocabulario del proyecto es la opción más segura:
        # no sustituye el idioma principal; lo complementa.
        project_words = self.project_words()
        project_words.update(
            words
        )

        self.settings.setValue(
            self._project_setting(
                "words"
            ),
            sorted(
                project_words
            ),
        )

        self._clear_caches()
        self.changed.emit()
        return len(
            words
        )

    def use_custom_dictionary(
        self,
        path: str | Path,
    ) -> int:
        path = Path(path)
        words = load_plain_wordlist(
            path
        )

        if not words:
            return 0

        self.language = "custom"
        self.custom_backend = WordListBackend(
            words
        )
        self.custom_dictionary_name = (
            path.stem
        )
        self._checker = None

        self.settings.setValue(
            self._project_setting(
                "custom_dictionary_path"
            ),
            str(path),
        )
        self.settings.setValue(
            self._project_setting(
                "language"
            ),
            "custom",
        )

        self._clear_caches()
        self.status_changed.emit(
            self.status_text()
        )
        self.changed.emit()
        return len(
            words
        )

    # ----------------------------------------------------------
    # Analysis
    # ----------------------------------------------------------
    def misspellings(
        self,
        text: str,
    ) -> list[dict]:
        if not self.enabled:
            return []

        counter = Counter()

        for token in iter_spell_tokens(
            text
        ):
            if not self.check(
                token.word
            ):
                counter[
                    token.word
                ] += 1

        result = []
        for word, count in counter.items():
            suggestions = (
                self.suggestions(
                    word
                )
            )
            result.append(
                {
                    "word": word,
                    "count": count,
                    "suggestions": suggestions,
                }
            )

        result.sort(
            key=lambda item:
                item["word"].casefold()
        )
        return result


class SpellHighlighter(QSyntaxHighlighter):
    def __init__(
        self,
        document,
        manager: SpellCheckerManager,
    ):
        super().__init__(
            document
        )
        self.manager = manager

        self.error_format = (
            QTextCharFormat()
        )
        self.error_format.setUnderlineStyle(
            QTextCharFormat.SpellCheckUnderline
        )
        self.error_format.setUnderlineColor(
            QColor(
                "#d32f2f"
            )
        )

        self.manager.changed.connect(
            self.rehighlight
        )

    def highlightBlock(
        self,
        text: str,
    ):
        if not self.manager.enabled:
            return

        for token in iter_spell_tokens(
            text
        ):
            if self.manager.check(
                token.word
            ):
                continue

            self.setFormat(
                token.start,
                token.end - token.start,
                self.error_format,
            )


class SpellCheckPlainTextEdit(
    QPlainTextEdit
):
    def __init__(
        self,
        manager: SpellCheckerManager,
        parent=None,
    ):
        super().__init__(
            parent
        )
        self.spell_manager = manager
        self.spell_highlighter = (
            SpellHighlighter(
                self.document(),
                manager,
            )
        )

    def _word_cursor_at(
        self,
        position,
    ):
        cursor = self.cursorForPosition(
            position
        )
        cursor.select(
            QTextCursor.WordUnderCursor
        )
        return cursor

    def contextMenuEvent(
        self,
        event,
    ):
        cursor = self._word_cursor_at(
            event.pos()
        )
        word = (
            cursor.selectedText()
            or ""
        ).strip()

        full_text = self.toPlainText()
        selection_start = (
            cursor.selectionStart()
        )
        spell_token = next(
            (
                token
                for token in iter_spell_tokens(
                    full_text
                )
                if (
                    token.start
                    <= selection_start
                    < token.end
                )
            ),
            None,
        )

        menu = self.createStandardContextMenu()

        if (
            word
            and spell_token is not None
            and self.spell_manager.enabled
            and not self.spell_manager.check(
                word
            )
        ):
            suggestions = (
                self.spell_manager.suggestions(
                    word
                )
            )

            if suggestions:
                menu.insertSeparator(
                    menu.actions()[0]
                    if menu.actions()
                    else None
                )

                first_action = (
                    menu.actions()[0]
                    if menu.actions()
                    else None
                )

                for suggestion in reversed(
                    suggestions
                ):
                    action = QAction(
                        suggestion,
                        menu,
                    )
                    action.setData(
                        suggestion
                    )
                    action.triggered.connect(
                        lambda _checked=False,
                        value=suggestion,
                        c=QTextCursor(cursor):
                            self._replace_cursor_word(
                                c,
                                value,
                            )
                    )

                    if first_action:
                        menu.insertAction(
                            first_action,
                            action,
                        )
                    else:
                        menu.addAction(
                            action
                        )

                if menu.actions():
                    menu.insertSeparator(
                        menu.actions()[
                            min(
                                len(suggestions),
                                len(menu.actions()) - 1,
                            )
                        ]
                    )

            add_personal = QAction(
                f"Agregar «{word}» al diccionario personal",
                menu,
            )
            add_personal.triggered.connect(
                lambda:
                    self.spell_manager.add_personal_word(
                        word
                    )
            )
            menu.addAction(
                add_personal
            )

            add_project = QAction(
                f"Agregar «{word}» al diccionario del proyecto",
                menu,
            )
            add_project.triggered.connect(
                lambda:
                    self.spell_manager.add_project_word(
                        word
                    )
            )
            menu.addAction(
                add_project
            )

            ignore = QAction(
                "Ignorar durante esta sesión",
                menu,
            )
            ignore.triggered.connect(
                lambda:
                    self.spell_manager.ignore_for_session(
                        word
                    )
            )
            menu.addAction(
                ignore
            )

        menu.exec(
            event.globalPos()
        )

    def _replace_cursor_word(
        self,
        cursor: QTextCursor,
        replacement: str,
    ):
        cursor.insertText(
            replacement
        )
        self.setTextCursor(
            cursor
        )
        self.setFocus()


class SpellReviewDialog(QDialog):
    def __init__(
        self,
        manager: SpellCheckerManager,
        text: str,
        parent=None,
    ):
        super().__init__(
            parent
        )
        self.setWindowTitle(
            "Revisión ortográfica"
        )
        self.resize(
            620,
            420,
        )

        layout = QVBoxLayout(
            self
        )

        findings = (
            manager.misspellings(
                text
            )
        )

        label = QLabel(
            (
                f"Posibles errores: "
                f"{sum(item['count'] for item in findings)} "
                f"({len(findings)} palabra(s) distinta(s))."
                if findings
                else "No se encontraron posibles errores."
            )
        )
        label.setWordWrap(
            True
        )

        tree = QTreeWidget()
        tree.setHeaderLabels(
            [
                "Palabra",
                "Veces",
                "Sugerencias",
            ]
        )
        tree.setRootIsDecorated(
            False
        )
        tree.setAlternatingRowColors(
            True
        )

        for item in findings:
            tree.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        item["word"],
                        str(
                            item["count"]
                        ),
                        ", ".join(
                            item["suggestions"]
                        ),
                    ]
                )
            )

        buttons = QDialogButtonBox(
            QDialogButtonBox.Close
        )
        buttons.rejected.connect(
            self.reject
        )
        buttons.clicked.connect(
            self.accept
        )

        layout.addWidget(
            label
        )
        layout.addWidget(
            tree,
            1,
        )
        layout.addWidget(
            buttons
        )
