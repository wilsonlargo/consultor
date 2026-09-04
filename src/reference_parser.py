import re
import unicodedata

BOOKS_ES = {
    "genesis": ("GEN","Génesis"), "exodo": ("EXO","Éxodo"), "levitico": ("LEV","Levítico"),
    "numeros": ("NUM","Números"), "deuteronomio": ("DEU","Deuteronomio"), "josue": ("JOS","Josué"),
    "jueces": ("JDG","Jueces"), "rut": ("RUT","Rut"), "1 samuel": ("1SA","1 Samuel"),
    "2 samuel": ("2SA","2 Samuel"), "1 reyes": ("1KI","1 Reyes"), "2 reyes": ("2KI","2 Reyes"),
    "1 cronicas": ("1CH","1 Crónicas"), "2 cronicas": ("2CH","2 Crónicas"), "esdras": ("EZR","Esdras"),
    "nehemias": ("NEH","Nehemías"), "ester": ("EST","Ester"), "job": ("JOB","Job"),
    "salmos": ("PSA","Salmos"), "salmo": ("PSA","Salmos"), "proverbios": ("PRO","Proverbios"),
    "eclesiastes": ("ECC","Eclesiastés"), "cantares": ("SNG","Cantares"),
    "cantar de los cantares": ("SNG","Cantares"), "isaias": ("ISA","Isaías"),
    "jeremias": ("JER","Jeremías"), "lamentaciones": ("LAM","Lamentaciones"),
    "ezequiel": ("EZK","Ezequiel"), "daniel": ("DAN","Daniel"), "oseas": ("HOS","Oseas"),
    "joel": ("JOL","Joel"), "amos": ("AMO","Amós"), "abdias": ("OBA","Abdías"),
    "jonas": ("JON","Jonás"), "miqueas": ("MIC","Miqueas"), "nahum": ("NAM","Nahúm"),
    "habacuc": ("HAB","Habacuc"), "sofonias": ("ZEP","Sofonías"), "hageo": ("HAG","Hageo"),
    "zacarias": ("ZEC","Zacarías"), "malaquias": ("MAL","Malaquías"), "mateo": ("MAT","Mateo"),
    "marcos": ("MRK","Marcos"), "lucas": ("LUK","Lucas"), "juan": ("JHN","Juan"),
    "hechos": ("ACT","Hechos"), "romanos": ("ROM","Romanos"), "1 corintios": ("1CO","1 Corintios"),
    "2 corintios": ("2CO","2 Corintios"), "galatas": ("GAL","Gálatas"), "efesios": ("EPH","Efesios"),
    "filipenses": ("PHP","Filipenses"), "colosenses": ("COL","Colosenses"),
    "1 tesalonicenses": ("1TH","1 Tesalonicenses"), "2 tesalonicenses": ("2TH","2 Tesalonicenses"),
    "1 timoteo": ("1TI","1 Timoteo"), "2 timoteo": ("2TI","2 Timoteo"), "tito": ("TIT","Tito"),
    "filemon": ("PHM","Filemón"), "hebreos": ("HEB","Hebreos"), "santiago": ("JAS","Santiago"),
    "1 pedro": ("1PE","1 Pedro"), "2 pedro": ("2PE","2 Pedro"), "1 juan": ("1JN","1 Juan"),
    "2 juan": ("2JN","2 Juan"), "3 juan": ("3JN","3 Juan"), "judas": ("JUD","Judas"),
    "apocalipsis": ("REV","Apocalipsis"),
}

ALIASES = {
    "gn":"GEN","gen":"GEN","ex":"EXO","exo":"EXO","lv":"LEV","num":"NUM","dt":"DEU","jos":"JOS",
    "jue":"JDG","sal":"PSA","sl":"PSA","prov":"PRO","is":"ISA","jer":"JER","ez":"EZK","dn":"DAN",
    "mt":"MAT","mat":"MAT","mc":"MRK","mr":"MRK","mrk":"MRK","lc":"LUK","luk":"LUK",
    "jn":"JHN","jhn":"JHN","hch":"ACT","act":"ACT","rom":"ROM","1 co":"1CO","1co":"1CO",
    "2 co":"2CO","2co":"2CO","gal":"GAL","ef":"EPH","fil":"PHP","col":"COL","1 ts":"1TH",
    "1ts":"1TH","2 ts":"2TH","2ts":"2TH","1 ti":"1TI","1ti":"1TI","2 ti":"2TI","2ti":"2TI",
    "tit":"TIT","flm":"PHM","heb":"HEB","stg":"JAS","1 pe":"1PE","1pe":"1PE","2 pe":"2PE",
    "2pe":"2PE","1 jn":"1JN","1jn":"1JN","2 jn":"2JN","2jn":"2JN","3 jn":"3JN","3jn":"3JN",
    "jud":"JUD","ap":"REV","rev":"REV",
}

USFM_TO_ES = {usfm: display for usfm, display in BOOKS_ES.values()}
USFM_TO_OSIS = {
    "GEN":"Gen","EXO":"Exod","LEV":"Lev","NUM":"Num","DEU":"Deut","JOS":"Josh","JDG":"Judg","RUT":"Ruth",
    "1SA":"1Sam","2SA":"2Sam","1KI":"1Kgs","2KI":"2Kgs","1CH":"1Chr","2CH":"2Chr","EZR":"Ezra",
    "NEH":"Neh","EST":"Esth","JOB":"Job","PSA":"Ps","PRO":"Prov","ECC":"Eccl","SNG":"Song","ISA":"Isa",
    "JER":"Jer","LAM":"Lam","EZK":"Ezek","DAN":"Dan","HOS":"Hos","JOL":"Joel","AMO":"Amos","OBA":"Obad",
    "JON":"Jonah","MIC":"Mic","NAM":"Nah","HAB":"Hab","ZEP":"Zeph","HAG":"Hag","ZEC":"Zech","MAL":"Mal",
    "MAT":"Matt","MRK":"Mark","LUK":"Luke","JHN":"John","ACT":"Acts","ROM":"Rom","1CO":"1Cor","2CO":"2Cor",
    "GAL":"Gal","EPH":"Eph","PHP":"Phil","COL":"Col","1TH":"1Thess","2TH":"2Thess","1TI":"1Tim","2TI":"2Tim",
    "TIT":"Titus","PHM":"Phlm","HEB":"Heb","JAS":"Jas","1PE":"1Pet","2PE":"2Pet","1JN":"1John",
    "2JN":"2John","3JN":"3John","JUD":"Jude","REV":"Rev",
}

USFM_RE = re.compile(r"^(?P<book>(?:[1-3])?[A-Z]{2,3})\.(?P<chapter>\d+)(?:\.(?P<verses>\d+(?:-\d+)?))?$")

def _normalize(text):
    text = text.strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text)

def split_usfm(reference):
    m = USFM_RE.fullmatch(reference.upper().strip())
    if not m:
        raise ValueError(f"Referencia USFM inválida: {reference}")
    return m.group("book"), m.group("chapter"), m.group("verses")

def parse_reference(text):
    if not text or not text.strip():
        raise ValueError("Escribe una cita bíblica.")
    candidate = text.strip().upper().replace(" ", "")
    if USFM_RE.fullmatch(candidate):
        book, _, _ = split_usfm(candidate)
        if book not in USFM_TO_ES:
            raise ValueError(f"No reconozco el libro USFM: {book}.")
        return candidate

    normalized = _normalize(text).replace("–","-").replace("—","-")
    m = re.match(r"^(?P<book>.+?)\s+(?P<chapter>\d+)(?::(?P<verses>\d+(?:-\d+)?))?$", normalized)
    if not m:
        raise ValueError("Ejemplos válidos: 'Marcos 8:31', '1 Corintios 13:4-7' o 'MRK.8.31'.")

    book_text = m.group("book").strip()
    entry = BOOKS_ES.get(book_text)
    book = entry[0] if entry else ALIASES.get(book_text)
    if not book:
        raise ValueError(f"No reconozco el libro bíblico: '{m.group('book')}'.")

    out = f"{book}.{m.group('chapter')}"
    if m.group("verses"):
        out += f".{m.group('verses')}"
    return out

def to_spanish_reference(reference):
    book, chapter, verses = split_usfm(reference)
    name = USFM_TO_ES.get(book, book)
    return f"{name} {chapter}:{verses}" if verses else f"{name} {chapter}"

def to_osis_reference(reference):
    book, chapter, verses = split_usfm(reference)
    name = USFM_TO_OSIS.get(book, book)
    return f"{name}.{chapter}.{verses}" if verses else f"{name}.{chapter}"
