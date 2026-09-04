from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import csv
import json
import re
import sqlite3
from typing import Iterable


DATASET_URLS = {
    "sblgnt": (
        "https://raw.githubusercontent.com/kbennett2000/concord/"
        "main/data/translations/SBLGNT.json"
    ),
    "oshb": (
        "https://raw.githubusercontent.com/kbennett2000/concord/"
        "main/data/translations/OSHB.json"
    ),
    "lexicon_greek": (
        "https://raw.githubusercontent.com/kbennett2000/concord/"
        "main/data/strongs/lexicon.json"
    ),
    "lexicon_hebrew": (
        "https://raw.githubusercontent.com/kbennett2000/concord/"
        "main/data/strongs/lexicon-hebrew.json"
    ),
    "tokens_greek": (
        "https://raw.githubusercontent.com/kbennett2000/concord/"
        "main/data/strongs/tokens-sblgnt.json"
    ),
    "tokens_hebrew": (
        "https://raw.githubusercontent.com/kbennett2000/concord/"
        "main/data/strongs/tokens-oshb.json"
    ),
    "crossrefs": (
        "https://raw.githubusercontent.com/kbennett2000/concord/"
        "main/data/cross-references/cross_references.txt"
    ),
    "topics": (
        "https://raw.githubusercontent.com/kbennett2000/concord/"
        "main/data/topics/naves.json"
    ),
    "places": (
        "https://raw.githubusercontent.com/kbennett2000/concord/"
        "main/data/geography/ancient.jsonl"
    ),
}

DATASET_FILES = {
    "sblgnt": "SBLGNT.json",
    "oshb": "OSHB.json",
    "lexicon_greek": "lexicon.json",
    "lexicon_hebrew": "lexicon-hebrew.json",
    "tokens_greek": "tokens-sblgnt.json",
    "tokens_hebrew": "tokens-oshb.json",
    "crossrefs": "cross_references.txt",
    "topics": "naves.json",
    "places": "ancient.jsonl",
}

NT_DATASETS = (
    "sblgnt",
    "lexicon_greek",
    "tokens_greek",
    "crossrefs",
)

OT_DATASETS = (
    "oshb",
    "lexicon_hebrew",
    "tokens_hebrew",
)

EXTRA_DATASETS = (
    "topics",
    "places",
)

ALL_DATASETS = (
    NT_DATASETS
    + OT_DATASETS
    + EXTRA_DATASETS
)


BOOK_ALIASES = {
    "GEN": "GEN", "GENESIS": "GEN",
    "EXO": "EXO", "EXOD": "EXO", "EXODUS": "EXO",
    "LEV": "LEV", "LEVITICUS": "LEV",
    "NUM": "NUM", "NUMBERS": "NUM",
    "DEU": "DEU", "DEUT": "DEU", "DEUTERONOMY": "DEU",
    "JOS": "JOS", "JOSH": "JOS", "JOSHUA": "JOS",
    "JDG": "JDG", "JUDG": "JDG", "JUDGES": "JDG",
    "RUT": "RUT", "RUTH": "RUT",
    "1SA": "1SA", "1SAM": "1SA", "1SAMUEL": "1SA",
    "2SA": "2SA", "2SAM": "2SA", "2SAMUEL": "2SA",
    "1KI": "1KI", "1KGS": "1KI", "1KINGS": "1KI",
    "2KI": "2KI", "2KGS": "2KI", "2KINGS": "2KI",
    "1CH": "1CH", "1CHR": "1CH", "1CHRONICLES": "1CH",
    "2CH": "2CH", "2CHR": "2CH", "2CHRONICLES": "2CH",
    "EZR": "EZR", "EZRA": "EZR",
    "NEH": "NEH", "NEHEMIAH": "NEH",
    "EST": "EST", "ESTH": "EST", "ESTHER": "EST",
    "JOB": "JOB",
    "PSA": "PSA", "PS": "PSA", "PSALM": "PSA", "PSALMS": "PSA",
    "PRO": "PRO", "PROV": "PRO", "PROVERBS": "PRO",
    "ECC": "ECC", "ECCL": "ECC", "ECCLESIASTES": "ECC",
    "SNG": "SNG", "SONG": "SNG", "SONGOFSONGS": "SNG",
    "ISA": "ISA", "ISAIAH": "ISA",
    "JER": "JER", "JEREMIAH": "JER",
    "LAM": "LAM", "LAMENTATIONS": "LAM",
    "EZK": "EZK", "EZEK": "EZK", "EZEKIEL": "EZK",
    "DAN": "DAN", "DANIEL": "DAN",
    "HOS": "HOS", "HOSEA": "HOS",
    "JOL": "JOL", "JOEL": "JOL",
    "AMO": "AMO", "AMOS": "AMO",
    "OBA": "OBA", "OBAD": "OBA", "OBADIAH": "OBA",
    "JON": "JON", "JONAH": "JON",
    "MIC": "MIC", "MICAH": "MIC",
    "NAM": "NAM", "NAH": "NAM", "NAHUM": "NAM",
    "HAB": "HAB", "HABAKKUK": "HAB",
    "ZEP": "ZEP", "ZEPH": "ZEP", "ZEPHANIAH": "ZEP",
    "HAG": "HAG", "HAGGAI": "HAG",
    "ZEC": "ZEC", "ZECH": "ZEC", "ZECHARIAH": "ZEC",
    "MAL": "MAL", "MALACHI": "MAL",
    "MAT": "MAT", "MATT": "MAT", "MATTHEW": "MAT",
    "MRK": "MRK", "MARK": "MRK",
    "LUK": "LUK", "LUKE": "LUK",
    "JHN": "JHN", "JOHN": "JHN",
    "ACT": "ACT", "ACTS": "ACT",
    "ROM": "ROM", "ROMANS": "ROM",
    "1CO": "1CO", "1COR": "1CO", "1CORINTHIANS": "1CO",
    "2CO": "2CO", "2COR": "2CO", "2CORINTHIANS": "2CO",
    "GAL": "GAL", "GALATIANS": "GAL",
    "EPH": "EPH", "EPHESIANS": "EPH",
    "PHP": "PHP", "PHIL": "PHP", "PHILIPPIANS": "PHP",
    "COL": "COL", "COLOSSIANS": "COL",
    "1TH": "1TH", "1THESS": "1TH", "1THESSALONIANS": "1TH",
    "2TH": "2TH", "2THESS": "2TH", "2THESSALONIANS": "2TH",
    "1TI": "1TI", "1TIM": "1TI", "1TIMOTHY": "1TI",
    "2TI": "2TI", "2TIM": "2TI", "2TIMOTHY": "2TI",
    "TIT": "TIT", "TITUS": "TIT",
    "PHM": "PHM", "PHLM": "PHM", "PHILEMON": "PHM",
    "HEB": "HEB", "HEBREWS": "HEB",
    "JAS": "JAS", "JAMES": "JAS",
    "1PE": "1PE", "1PET": "1PE", "1PETER": "1PE",
    "2PE": "2PE", "2PET": "2PE", "2PETER": "2PE",
    "1JN": "1JN", "1JOHN": "1JN",
    "2JN": "2JN", "2JOHN": "2JN",
    "3JN": "3JN", "3JOHN": "3JN",
    "JUD": "JUD", "JUDE": "JUD",
    "REV": "REV", "REVELATION": "REV",
}


def normalize_external_reference(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""

    # Keep only the first reference when a source expresses a range as
    # Book.Ch.Verse-Book.Ch.Verse; the end is retained separately by callers.
    value = value.replace("–", "-").replace("—", "-")
    value = re.sub(r"\s+", "", value)

    match = re.match(
        r"^([1-3]?[A-Za-z]+)[.\s:]?(\d+)[.:](\d+[A-Za-z]?)(?:-(\d+[A-Za-z]?))?$",
        value,
    )
    if not match:
        # OpenBible commonly uses Gen.1.1 / John.3.16.
        match = re.match(
            r"^([1-3]?[A-Za-z]+)\.(\d+)\.(\d+[A-Za-z]?)(?:-(\d+[A-Za-z]?))?$",
            value,
        )

    if not match:
        return value.upper()

    raw_book = re.sub(
        r"[^A-Za-z0-9]",
        "",
        match.group(1),
    ).upper()
    book = BOOK_ALIASES.get(
        raw_book,
        raw_book,
    )
    chapter = match.group(2)
    verse = match.group(3)
    end = match.group(4)

    ref = f"{book}.{chapter}.{verse}"
    if end:
        ref += f"-{end}"
    return ref


def first_reference(reference: str) -> str:
    ref = normalize_external_reference(reference)
    if "-" not in ref:
        return ref
    return ref.split("-", 1)[0]


@dataclass
class WordRecord:
    reference: str
    position: int
    surface_form: str
    strongs_id: str
    morph_code: str
    lemma: str = ""
    transliteration: str = ""
    gloss: str = ""
    definition: str = ""


class NativeResourceStore:
    SCHEMA_VERSION = 3

    def __init__(
        self,
        db_path: str | Path,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._create_schema()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(
            self.db_path
        )
        conn.row_factory = (
            sqlite3.Row
        )
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _create_schema(self):
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS verses (
                    reference TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    language TEXT NOT NULL,
                    direction TEXT NOT NULL DEFAULT 'ltr',
                    source TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS lexicon (
                    strongs_id TEXT PRIMARY KEY,
                    language TEXT NOT NULL DEFAULT '',
                    lemma TEXT NOT NULL DEFAULT '',
                    transliteration TEXT NOT NULL DEFAULT '',
                    gloss TEXT NOT NULL DEFAULT '',
                    definition TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS tokens (
                    reference TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    surface_form TEXT NOT NULL DEFAULT '',
                    strongs_id TEXT NOT NULL DEFAULT '',
                    morph_code TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (reference, position)
                );

                CREATE INDEX IF NOT EXISTS idx_tokens_ref
                    ON tokens(reference);
                CREATE INDEX IF NOT EXISTS idx_tokens_strongs
                    ON tokens(strongs_id);

                CREATE TABLE IF NOT EXISTS crossrefs (
                    from_ref TEXT NOT NULL,
                    to_ref TEXT NOT NULL,
                    votes INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (from_ref, to_ref)
                );

                CREATE INDEX IF NOT EXISTS idx_crossrefs_from
                    ON crossrefs(from_ref, votes DESC);

                CREATE TABLE IF NOT EXISTS topics (
                    topic_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    section TEXT NOT NULL DEFAULT '',
                    see_also TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS topic_verses (
                    topic_id TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    PRIMARY KEY (topic_id, reference)
                );

                CREATE INDEX IF NOT EXISTS idx_topic_verses_ref
                    ON topic_verses(reference);

                CREATE TABLE IF NOT EXISTS places (
                    place_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    place_type TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    longitude REAL,
                    latitude REAL,
                    confidence INTEGER NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS place_verses (
                    place_id TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    PRIMARY KEY (place_id, reference)
                );

                CREATE INDEX IF NOT EXISTS idx_place_verses_ref
                    ON place_verses(reference);

                CREATE TABLE IF NOT EXISTS context_chapters (
                    provider TEXT NOT NULL,
                    book TEXT NOT NULL,
                    chapter INTEGER NOT NULL,
                    provider_name TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    license_name TEXT NOT NULL DEFAULT '',
                    license_url TEXT NOT NULL DEFAULT '',
                    fetched_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (provider, book, chapter)
                );

                CREATE TABLE IF NOT EXISTS context_notes (
                    provider TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    note_order INTEGER NOT NULL DEFAULT 0,
                    heading TEXT NOT NULL DEFAULT '',
                    text TEXT NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '',
                    license_name TEXT NOT NULL DEFAULT '',
                    license_url TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (
                        provider,
                        reference,
                        note_order
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_context_notes_ref
                    ON context_notes(provider, reference);

                CREATE TABLE IF NOT EXISTS private_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reference TEXT NOT NULL,
                    note_type TEXT NOT NULL DEFAULT '',
                    marker TEXT NOT NULL DEFAULT '',
                    text TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_private_notes_ref
                    ON private_notes(reference);
                """
            )
            conn.execute(
                """
                INSERT INTO meta(key, value)
                VALUES('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(self.SCHEMA_VERSION),),
            )

    def set_meta(
        self,
        key: str,
        value: str,
    ):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO meta(key, value)
                VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, str(value)),
            )

    def get_meta(
        self,
        key: str,
        default: str = "",
    ) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key=?",
                (key,),
            ).fetchone()
        return (
            str(row["value"])
            if row
            else default
        )

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            result = {}
            for table in (
                "verses",
                "lexicon",
                "tokens",
                "crossrefs",
                "topics",
                "topic_verses",
                "places",
                "place_verses",
                "context_chapters",
                "context_notes",
                "private_notes",
            ):
                result[table] = int(
                    conn.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                )
        return result

    def has_native_data(self) -> bool:
        counts = self.counts()
        return bool(
            counts["tokens"]
            or counts["verses"]
            or counts["crossrefs"]
            or counts["topic_verses"]
            or counts["place_verses"]
        )

    def clear_open_data(self):
        with self.connect() as conn:
            conn.executescript(
                """
                DELETE FROM verses;
                DELETE FROM lexicon;
                DELETE FROM tokens;
                DELETE FROM crossrefs;
                DELETE FROM topic_verses;
                DELETE FROM topics;
                DELETE FROM place_verses;
                DELETE FROM places;
                """
            )

    # --------------------------------------------------------------
    # Importers
    # --------------------------------------------------------------
    def import_translation_json(
        self,
        path: str | Path,
    ) -> int:
        path = Path(path)
        data = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

        language = str(
            data.get("language")
            or ""
        )
        source = str(
            data.get("copyright")
            or data.get("source")
            or ""
        )
        direction = (
            "rtl"
            if language in {
                "hbo",
                "he",
                "heb",
            }
            else "ltr"
        )

        rows = []

        for book in data.get(
            "books",
            [],
        ):
            book_code = str(
                book.get("abbreviation")
                or book.get("code")
                or book.get("id")
                or ""
            ).upper()
            book_code = BOOK_ALIASES.get(
                book_code,
                book_code,
            )
            if not book_code:
                continue

            for chapter in book.get(
                "chapters",
                [],
            ):
                chapter_number = int(
                    chapter.get("number")
                    or 0
                )
                if chapter_number <= 0:
                    continue

                for verse in chapter.get(
                    "verses",
                    [],
                ):
                    verse_number = verse.get(
                        "number"
                    )
                    if verse_number in (
                        None,
                        "",
                    ):
                        continue
                    text = str(
                        verse.get("text")
                        or ""
                    )
                    reference = (
                        f"{book_code}."
                        f"{chapter_number}."
                        f"{verse_number}"
                    )
                    rows.append(
                        (
                            reference,
                            text,
                            language,
                            direction,
                            source,
                        )
                    )

        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO verses(
                    reference, text, language, direction, source
                )
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(reference) DO UPDATE SET
                    text=excluded.text,
                    language=excluded.language,
                    direction=excluded.direction,
                    source=excluded.source
                """,
                rows,
            )

        return len(rows)

    def import_tokens_json(
        self,
        path: str | Path,
    ) -> int:
        path = Path(path)
        data = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )
        items = data.get(
            "tokens",
            [],
        )

        rows = []
        for item in items:
            book = str(
                item.get("book")
                or ""
            ).upper()
            book = BOOK_ALIASES.get(
                book,
                book,
            )
            chapter = item.get(
                "chapter"
            )
            verse = item.get(
                "verse"
            )
            position = item.get(
                "position"
            )
            if (
                not book
                or chapter is None
                or verse is None
                or position is None
            ):
                continue

            reference = (
                f"{book}.{chapter}.{verse}"
            )
            rows.append(
                (
                    reference,
                    int(position),
                    str(
                        item.get(
                            "surface_form"
                        )
                        or ""
                    ),
                    normalize_strongs(
                        str(
                            item.get(
                                "strongs_id"
                            )
                            or ""
                        )
                    ),
                    str(
                        item.get(
                            "morph_code"
                        )
                        or ""
                    ),
                )
            )

        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO tokens(
                    reference, position, surface_form,
                    strongs_id, morph_code
                )
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(reference, position) DO UPDATE SET
                    surface_form=excluded.surface_form,
                    strongs_id=excluded.strongs_id,
                    morph_code=excluded.morph_code
                """,
                rows,
            )

        return len(rows)

    def import_lexicon_json(
        self,
        path: str | Path,
    ) -> int:
        path = Path(path)
        data = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )
        items = data.get(
            "entries",
            [],
        )

        rows = []
        for item in items:
            strongs_id = normalize_strongs(
                str(
                    item.get(
                        "strongs_id"
                    )
                    or item.get(
                        "strongs"
                    )
                    or ""
                )
            )
            if not strongs_id:
                continue

            rows.append(
                (
                    strongs_id,
                    str(
                        item.get(
                            "language"
                        )
                        or ""
                    ),
                    str(
                        item.get(
                            "lemma"
                        )
                        or ""
                    ),
                    str(
                        item.get(
                            "transliteration"
                        )
                        or ""
                    ),
                    str(
                        item.get(
                            "gloss"
                        )
                        or ""
                    ),
                    str(
                        item.get(
                            "definition"
                        )
                        or ""
                    ),
                )
            )

        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO lexicon(
                    strongs_id, language, lemma,
                    transliteration, gloss, definition
                )
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(strongs_id) DO UPDATE SET
                    language=excluded.language,
                    lemma=excluded.lemma,
                    transliteration=excluded.transliteration,
                    gloss=excluded.gloss,
                    definition=excluded.definition
                """,
                rows,
            )

        return len(rows)

    def import_crossrefs(
        self,
        path: str | Path,
    ) -> int:
        path = Path(path)
        rows = []

        with path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
            newline="",
        ) as handle:
            for raw in handle:
                line = raw.strip()
                if (
                    not line
                    or line.startswith("#")
                ):
                    continue

                parts = line.split("\t")
                if len(parts) < 2:
                    continue

                from_raw = parts[0].strip()
                to_raw = parts[1].strip()

                # Skip header.
                if (
                    from_raw.casefold()
                    in {
                        "from verse",
                        "from",
                    }
                ):
                    continue

                votes = 0
                if len(parts) > 2:
                    try:
                        votes = int(
                            float(
                                parts[2]
                            )
                        )
                    except ValueError:
                        votes = 0

                from_ref = (
                    normalize_crossref_source(
                        from_raw
                    )
                )
                to_ref = (
                    normalize_crossref_target(
                        to_raw
                    )
                )

                if (
                    not from_ref
                    or not to_ref
                ):
                    continue

                rows.append(
                    (
                        from_ref,
                        to_ref,
                        votes,
                    )
                )

        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO crossrefs(
                    from_ref, to_ref, votes
                )
                VALUES(?, ?, ?)
                ON CONFLICT(from_ref, to_ref) DO UPDATE SET
                    votes=excluded.votes
                """,
                rows,
            )

        return len(rows)

    def import_topics_json(
        self,
        path: str | Path,
    ) -> int:
        path = Path(path)
        data = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

        if isinstance(data, dict):
            items = (
                data.get("topics")
                or data.get("items")
                or []
            )
            if not items:
                items = []
                for key, value in data.items():
                    if isinstance(value, dict):
                        item = dict(value)
                        item.setdefault("id", key)
                        items.append(item)
        elif isinstance(data, list):
            items = data
        else:
            items = []

        topic_rows = []
        verse_rows = []

        for index, item in enumerate(
            items,
            start=1,
        ):
            if not isinstance(item, dict):
                continue

            topic_id = str(
                item.get("id")
                or item.get("topic_id")
                or item.get("slug")
                or index
            )
            name = str(
                item.get("name")
                or item.get("topic")
                or item.get("title")
                or ""
            ).strip()
            if not name:
                continue

            section = str(
                item.get("section")
                or item.get("category")
                or ""
            ).strip()

            see_also_value = (
                item.get("see_also")
                or item.get("see")
                or ""
            )
            if isinstance(see_also_value, list):
                see_also = ", ".join(
                    str(value)
                    for value in see_also_value
                )
            elif isinstance(see_also_value, dict):
                see_also = str(
                    see_also_value.get("name")
                    or see_also_value.get("id")
                    or ""
                )
            else:
                see_also = str(
                    see_also_value
                    or ""
                )

            topic_rows.append(
                (
                    topic_id,
                    name,
                    section,
                    see_also,
                )
            )

            verses = (
                item.get("verses")
                or item.get("references")
                or item.get("refs")
                or []
            )
            if isinstance(verses, str):
                verses = [
                    value.strip()
                    for value in re.split(
                        r"[,;]",
                        verses,
                    )
                    if value.strip()
                ]

            for value in verses:
                if isinstance(value, dict):
                    book = str(
                        value.get("book")
                        or ""
                    ).upper()
                    chapter = value.get(
                        "chapter"
                    )
                    verse = value.get(
                        "verse"
                    )

                    if (
                        book
                        and chapter is not None
                        and verse is not None
                    ):
                        raw_reference = (
                            f"{book}.{chapter}.{verse}"
                        )
                    else:
                        raw_reference = str(
                            value.get("reference")
                            or value.get("ref")
                            or value.get("osis")
                            or ""
                        )
                else:
                    raw_reference = str(
                        value
                    )

                reference = normalize_external_reference(
                    raw_reference
                )
                if not reference:
                    continue

                # Nave may include ranges; associate the topic at least with
                # the canonical start so it appears on the verse in question.
                verse_rows.append(
                    (
                        topic_id,
                        first_reference(
                            reference
                        ),
                    )
                )

        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO topics(
                    topic_id, name, section, see_also
                )
                VALUES(?, ?, ?, ?)
                ON CONFLICT(topic_id) DO UPDATE SET
                    name=excluded.name,
                    section=excluded.section,
                    see_also=excluded.see_also
                """,
                topic_rows,
            )
            conn.executemany(
                """
                INSERT OR IGNORE INTO topic_verses(
                    topic_id, reference
                )
                VALUES(?, ?)
                """,
                verse_rows,
            )

        return len(verse_rows)

    def import_places_jsonl(
        self,
        path: str | Path,
    ) -> int:
        path = Path(path)

        place_rows = []
        verse_rows = []

        tag_re = re.compile(
            r"<[^>]+>"
        )

        with path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ) as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue

                try:
                    item = json.loads(
                        line
                    )
                except json.JSONDecodeError:
                    continue

                if not isinstance(item, dict):
                    continue

                place_id = str(
                    item.get("id")
                    or ""
                )
                name = str(
                    item.get("friendly_id")
                    or item.get("name")
                    or ""
                ).strip()

                if not (
                    place_id
                    and name
                ):
                    continue

                candidates = []

                for identification in (
                    item.get("identifications")
                    or []
                ):
                    if not isinstance(
                        identification,
                        dict,
                    ):
                        continue

                    score_info = (
                        identification.get("score")
                        or {}
                    )
                    if isinstance(
                        score_info,
                        dict,
                    ):
                        identification_score = int(
                            score_info.get("time_total")
                            or score_info.get("vote_total")
                            or 0
                        )
                    else:
                        identification_score = 0

                    for resolution in (
                        identification.get("resolutions")
                        or []
                    ):
                        if not isinstance(
                            resolution,
                            dict,
                        ):
                            continue

                        lonlat = str(
                            resolution.get("lonlat")
                            or ""
                        )
                        longitude = None
                        latitude = None

                        if "," in lonlat:
                            try:
                                longitude, latitude = [
                                    float(value.strip())
                                    for value in lonlat.split(
                                        ",",
                                        1,
                                    )
                                ]
                            except ValueError:
                                longitude = None
                                latitude = None

                        resolution_score = int(
                            resolution.get("best_time_score")
                            or resolution.get("best_path_score")
                            or identification_score
                            or 0
                        )

                        if (
                            identification_score
                            and resolution_score
                        ):
                            confidence = int(
                                identification_score
                                * resolution_score
                                / 1000
                            )
                        else:
                            confidence = max(
                                identification_score,
                                resolution_score,
                            )

                        description = tag_re.sub(
                            "",
                            str(
                                resolution.get("description")
                                or ""
                            ),
                        ).strip()

                        candidates.append(
                            {
                                "longitude": longitude,
                                "latitude": latitude,
                                "confidence": confidence,
                                "type": str(
                                    resolution.get("type")
                                    or resolution.get("class")
                                    or ""
                                ),
                                "description": description,
                            }
                        )

                with_coordinates = [
                    candidate
                    for candidate in candidates
                    if (
                        candidate["longitude"] is not None
                        and candidate["latitude"] is not None
                    )
                ]

                if with_coordinates:
                    with_coordinates.sort(
                        key=lambda value:
                            value["confidence"],
                        reverse=True,
                    )
                    best = with_coordinates[0]

                    unique_coordinates = {
                        (
                            round(
                                candidate["longitude"],
                                5,
                            ),
                            round(
                                candidate["latitude"],
                                5,
                            ),
                        )
                        for candidate in with_coordinates
                    }

                    status = (
                        "identified"
                        if len(unique_coordinates) == 1
                        else "disputed"
                    )
                else:
                    best = (
                        candidates[0]
                        if candidates
                        else {
                            "longitude": None,
                            "latitude": None,
                            "confidence": 0,
                            "type": "",
                            "description": "",
                        }
                    )
                    status = "unknown"

                place_rows.append(
                    (
                        place_id,
                        name,
                        best["type"],
                        status,
                        best["longitude"],
                        best["latitude"],
                        int(
                            best["confidence"]
                            or 0
                        ),
                        best["description"],
                    )
                )

                for verse in (
                    item.get("verses")
                    or []
                ):
                    if isinstance(
                        verse,
                        dict,
                    ):
                        raw_reference = str(
                            verse.get("osis")
                            or verse.get("usx")
                            or verse.get("readable")
                            or ""
                        )
                    else:
                        raw_reference = str(
                            verse
                        )

                    reference = normalize_external_reference(
                        raw_reference
                    )
                    if reference:
                        verse_rows.append(
                            (
                                place_id,
                                first_reference(
                                    reference
                                ),
                            )
                        )

        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO places(
                    place_id, name, place_type, status,
                    longitude, latitude, confidence, description
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(place_id) DO UPDATE SET
                    name=excluded.name,
                    place_type=excluded.place_type,
                    status=excluded.status,
                    longitude=excluded.longitude,
                    latitude=excluded.latitude,
                    confidence=excluded.confidence,
                    description=excluded.description
                """,
                place_rows,
            )
            conn.executemany(
                """
                INSERT OR IGNORE INTO place_verses(
                    place_id, reference
                )
                VALUES(?, ?)
                """,
                verse_rows,
            )

        return len(verse_rows)

    def import_private_notes_json(
        self,
        path: str | Path,
    ) -> int:
        path = Path(path)
        data = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

        items = data.get(
            "notes",
            data
            if isinstance(
                data,
                list,
            )
            else [],
        )

        rows = []

        for item in items:
            if not isinstance(
                item,
                dict,
            ):
                continue

            if item.get(
                "reference"
            ):
                reference = (
                    normalize_external_reference(
                        str(
                            item.get(
                                "reference"
                            )
                        )
                    )
                )
            else:
                book = str(
                    item.get("book")
                    or ""
                ).upper()
                book = BOOK_ALIASES.get(
                    book,
                    book,
                )
                chapter = item.get(
                    "chapter"
                )
                verse = item.get(
                    "verse"
                )
                if (
                    not book
                    or chapter is None
                    or verse is None
                ):
                    continue
                reference = (
                    f"{book}.{chapter}.{verse}"
                )

            body = str(
                item.get("text")
                or item.get("content")
                or item.get("note")
                or ""
            ).strip()
            if not body:
                continue

            rows.append(
                (
                    reference,
                    str(
                        item.get(
                            "type"
                        )
                        or item.get(
                            "note_type"
                        )
                        or ""
                    ),
                    str(
                        item.get(
                            "marker"
                        )
                        or ""
                    ),
                    body,
                    str(path),
                )
            )

        with self.connect() as conn:
            conn.execute(
                "DELETE FROM private_notes WHERE source=?",
                (str(path),),
            )
            conn.executemany(
                """
                INSERT INTO private_notes(
                    reference, note_type, marker, text, source
                )
                VALUES(?, ?, ?, ?, ?)
                """,
                rows,
            )

        return len(rows)

    # --------------------------------------------------------------
    # Queries
    # --------------------------------------------------------------
    def verse_text(
        self,
        reference: str,
    ):
        ref = first_reference(
            reference
        )
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT *
                FROM verses
                WHERE reference=?
                """,
                (ref,),
            ).fetchone()

    def words_for_verse(
        self,
        reference: str,
    ) -> list[WordRecord]:
        ref = first_reference(
            reference
        )

        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.reference,
                    t.position,
                    t.surface_form,
                    t.strongs_id,
                    t.morph_code,
                    COALESCE(l.lemma, '') AS lemma,
                    COALESCE(l.transliteration, '') AS transliteration,
                    COALESCE(l.gloss, '') AS gloss,
                    COALESCE(l.definition, '') AS definition
                FROM tokens t
                LEFT JOIN lexicon l
                    ON l.strongs_id=t.strongs_id
                WHERE t.reference=?
                ORDER BY t.position
                """,
                (ref,),
            ).fetchall()

        return [
            WordRecord(
                reference=row["reference"],
                position=int(row["position"]),
                surface_form=row["surface_form"],
                strongs_id=row["strongs_id"],
                morph_code=row["morph_code"],
                lemma=row["lemma"],
                transliteration=row["transliteration"],
                gloss=row["gloss"],
                definition=row["definition"],
            )
            for row in rows
        ]

    def lexicon_entry(
        self,
        strongs_id: str,
    ):
        strongs_id = normalize_strongs(
            strongs_id
        )
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT *
                FROM lexicon
                WHERE strongs_id=?
                """,
                (strongs_id,),
            ).fetchone()

    def crossrefs_for(
        self,
        reference: str,
        limit: int = 80,
    ):
        ref = first_reference(
            reference
        )
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT to_ref, votes
                FROM crossrefs
                WHERE from_ref=?
                ORDER BY votes DESC, to_ref
                LIMIT ?
                """,
                (
                    ref,
                    int(limit),
                ),
            ).fetchall()

    def topics_for(
        self,
        reference: str,
    ):
        ref = first_reference(
            reference
        )
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT
                    t.topic_id,
                    t.name,
                    t.section,
                    t.see_also
                FROM topic_verses tv
                JOIN topics t
                    ON t.topic_id=tv.topic_id
                WHERE tv.reference=?
                ORDER BY t.name
                """,
                (ref,),
            ).fetchall()

    def topic_verses(
        self,
        topic_id: str,
        limit: int = 300,
    ):
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT reference
                FROM topic_verses
                WHERE topic_id=?
                ORDER BY reference
                LIMIT ?
                """,
                (
                    str(topic_id),
                    int(limit),
                ),
            ).fetchall()

    def places_for(
        self,
        reference: str,
    ):
        ref = first_reference(
            reference
        )
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT
                    p.place_id,
                    p.name,
                    p.place_type,
                    p.status,
                    p.longitude,
                    p.latitude,
                    p.confidence,
                    p.description
                FROM place_verses pv
                JOIN places p
                    ON p.place_id=pv.place_id
                WHERE pv.reference=?
                ORDER BY
                    CASE p.status
                        WHEN 'identified' THEN 0
                        WHEN 'disputed' THEN 1
                        ELSE 2
                    END,
                    p.confidence DESC,
                    p.name
                """,
                (ref,),
            ).fetchall()

    def place_verses(
        self,
        place_id: str,
        limit: int = 300,
    ):
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT reference
                FROM place_verses
                WHERE place_id=?
                ORDER BY reference
                LIMIT ?
                """,
                (
                    str(place_id),
                    int(limit),
                ),
            ).fetchall()

    def replace_context_chapter(
        self,
        provider: str,
        book: str,
        chapter: int,
        notes: list[dict],
        *,
        provider_name: str = "",
        source_url: str = "",
        license_name: str = "",
        license_url: str = "",
        fetched_at: str = "",
    ) -> int:
        provider = str(provider or "").strip()
        book = str(book or "").strip().upper()
        chapter = int(chapter)

        rows = []
        order_by_ref: dict[str, int] = {}

        for note in notes:
            reference = first_reference(
                str(
                    note.get("reference")
                    or ""
                )
            )
            body = str(
                note.get("text")
                or ""
            ).strip()
            if not (
                reference
                and body
            ):
                continue

            note_order = order_by_ref.get(
                reference,
                0,
            )
            order_by_ref[
                reference
            ] = note_order + 1

            rows.append(
                (
                    provider,
                    reference,
                    note_order,
                    str(
                        note.get("heading")
                        or ""
                    ).strip(),
                    body,
                    str(
                        note.get("source_url")
                        or source_url
                        or ""
                    ),
                    str(
                        note.get("license_name")
                        or license_name
                        or ""
                    ),
                    str(
                        note.get("license_url")
                        or license_url
                        or ""
                    ),
                )
            )

        with self.connect() as conn:
            conn.execute(
                """
                DELETE FROM context_notes
                WHERE provider=?
                  AND reference LIKE ?
                """,
                (
                    provider,
                    f"{book}.{chapter}.%",
                ),
            )

            if rows:
                conn.executemany(
                    """
                    INSERT INTO context_notes(
                        provider,
                        reference,
                        note_order,
                        heading,
                        text,
                        source_url,
                        license_name,
                        license_url
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )

            conn.execute(
                """
                INSERT INTO context_chapters(
                    provider,
                    book,
                    chapter,
                    provider_name,
                    source_url,
                    license_name,
                    license_url,
                    fetched_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, book, chapter)
                DO UPDATE SET
                    provider_name=excluded.provider_name,
                    source_url=excluded.source_url,
                    license_name=excluded.license_name,
                    license_url=excluded.license_url,
                    fetched_at=excluded.fetched_at
                """,
                (
                    provider,
                    book,
                    chapter,
                    provider_name,
                    source_url,
                    license_name,
                    license_url,
                    fetched_at,
                ),
            )

        return len(rows)

    def context_chapter_cached(
        self,
        provider: str,
        book: str,
        chapter: int,
    ) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM context_chapters
                WHERE provider=?
                  AND book=?
                  AND chapter=?
                """,
                (
                    str(provider),
                    str(book).upper(),
                    int(chapter),
                ),
            ).fetchone()

        return row is not None

    def context_chapter_meta(
        self,
        provider: str,
        book: str,
        chapter: int,
    ):
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT *
                FROM context_chapters
                WHERE provider=?
                  AND book=?
                  AND chapter=?
                """,
                (
                    str(provider),
                    str(book).upper(),
                    int(chapter),
                ),
            ).fetchone()

    def context_notes_for(
        self,
        provider: str,
        reference: str,
    ):
        reference = first_reference(
            reference
        )

        with self.connect() as conn:
            return conn.execute(
                """
                SELECT *
                FROM context_notes
                WHERE provider=?
                  AND reference=?
                ORDER BY note_order
                """,
                (
                    str(provider),
                    reference,
                ),
            ).fetchall()

    def private_notes_for(
        self,
        reference: str,
    ):
        ref = first_reference(
            reference
        )
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT *
                FROM private_notes
                WHERE reference=?
                ORDER BY id
                """,
                (ref,),
            ).fetchall()


def normalize_strongs(
    value: str,
) -> str:
    value = (
        value
        or ""
    ).strip().upper()
    if not value:
        return ""

    match = re.match(
        r"^([GH])0*(\d+)",
        value,
    )
    if not match:
        return value

    return (
        f"{match.group(1)}"
        f"{int(match.group(2))}"
    )


def normalize_crossref_source(
    value: str,
) -> str:
    value = value.strip()
    # OpenBible normally has a single source verse.
    return first_reference(
        normalize_external_reference(
            value
        )
    )


def normalize_crossref_target(
    value: str,
) -> str:
    value = value.strip()

    # Handle forms such as John.3.16-John.3.17.
    match = re.match(
        r"^([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)"
        r"-([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)$",
        value,
    )
    if match:
        start = normalize_external_reference(
            f"{match.group(1)}."
            f"{match.group(2)}."
            f"{match.group(3)}"
        )
        end = normalize_external_reference(
            f"{match.group(4)}."
            f"{match.group(5)}."
            f"{match.group(6)}"
        )
        if (
            start.split(".")[:2]
            == end.split(".")[:2]
        ):
            return (
                start
                + "-"
                + end.split(".")[-1]
            )
        return (
            start
            + " – "
            + end
        )

    return normalize_external_reference(
        value
    )


GREEK_POS = {
    "N": "sustantivo",
    "V": "verbo",
    "A": "adjetivo",
    "ADV": "adverbio",
    "CONJ": "conjunción",
    "PREP": "preposición",
    "PRT": "partícula",
    "P": "pronombre",
    "T": "artículo",
    "D": "adverbio / determinante",
    "I": "interjección",
    "R": "pronombre relativo",
    "C": "conjunción",
}

CASES = {
    "N": "nominativo",
    "G": "genitivo",
    "D": "dativo",
    "A": "acusativo",
    "V": "vocativo",
}

NUMBERS = {
    "S": "singular",
    "P": "plural",
}

GENDERS = {
    "M": "masculino",
    "F": "femenino",
    "N": "neutro",
}

TENSES = {
    "P": "presente",
    "I": "imperfecto",
    "F": "futuro",
    "A": "aoristo",
    "R": "perfecto",
    "L": "pluscuamperfecto",
    "X": "sin tiempo especificado",
}

VOICES = {
    "A": "activa",
    "M": "media",
    "P": "pasiva",
    "E": "media o pasiva",
    "D": "media deponente",
    "O": "pasiva deponente",
    "N": "media/pasiva deponente",
}

MOODS = {
    "I": "indicativo",
    "S": "subjuntivo",
    "O": "optativo",
    "M": "imperativo",
    "N": "infinitivo",
    "P": "participio",
}


def describe_morphology(
    code: str,
) -> str:
    code = (
        code
        or ""
    ).strip().upper()
    if not code:
        return ""

    # Common Greek forms such as N-NSF and V-AAI-3S.
    parts = code.split("-")
    pos = parts[0]

    labels = []
    if pos in GREEK_POS:
        labels.append(
            GREEK_POS[pos]
        )

    if pos == "V" and len(parts) >= 2:
        verb = parts[1]
        if len(verb) >= 3:
            labels.extend(
                filter(
                    None,
                    (
                        TENSES.get(
                            verb[0],
                            "",
                        ),
                        VOICES.get(
                            verb[1],
                            "",
                        ),
                        MOODS.get(
                            verb[2],
                            "",
                        ),
                    ),
                )
            )

        if len(parts) >= 3:
            pn = parts[2]
            if (
                len(pn) >= 2
                and pn[0].isdigit()
            ):
                labels.append(
                    f"{pn[0]}.ª persona"
                )
                labels.append(
                    NUMBERS.get(
                        pn[1],
                        pn[1],
                    )
                )
            elif len(pn) >= 3:
                labels.extend(
                    filter(
                        None,
                        (
                            CASES.get(
                                pn[0],
                                "",
                            ),
                            NUMBERS.get(
                                pn[1],
                                "",
                            ),
                            GENDERS.get(
                                pn[2],
                                "",
                            ),
                        ),
                    )
                )

    elif len(parts) >= 2:
        nominal = parts[1]
        if len(nominal) >= 3:
            labels.extend(
                filter(
                    None,
                    (
                        CASES.get(
                            nominal[0],
                            "",
                        ),
                        NUMBERS.get(
                            nominal[1],
                            "",
                        ),
                        GENDERS.get(
                            nominal[2],
                            "",
                        ),
                    ),
                )
            )

    if not labels:
        return code

    return (
        " · ".join(labels)
        + f"  [{code}]"
    )
