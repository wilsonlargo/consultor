from urllib.parse import urlencode
from .reference_parser import to_osis_reference, to_spanish_reference


SOURCES = [
    ("BibleGateway — DHH", "BG", ["DHH"]),
    ("BibleGateway — NTV", "BG", ["NTV"]),
    ("BibleGateway — NVI", "BG", ["NVI"]),
    ("BibleGateway — DHH + NTV + NVI", "BG", ["DHH", "NTV", "NVI"]),
    ("BibleGateway — RVR1960", "BG", ["RVR1960"]),
    ("STEP — NVI", "STEP", "SpaNVI"),
    ("STEP — Griego SBLGNT", "STEP", "SBLG"),
    ("STEP — NVI + Griego", "STEP_PARALLEL", None),
]


def biblegateway_url(reference, versions):
    query = urlencode({
        "search": to_spanish_reference(reference),
        "version": ";".join(versions),
    })
    return f"https://www.biblegateway.com/passage/?{query}"


def step_url(reference, version):
    q = f"version={version}@reference={to_osis_reference(reference)}"
    return f"https://www.stepbible.org/?{urlencode({'q': q})}"


def step_parallel_url(reference):
    q = f"version=SpaNVI|version=SBLG@reference={to_osis_reference(reference)}"
    return f"https://www.stepbible.org/?{urlencode({'q': q})}"


def build_url(source_index, reference):
    label, kind, data = SOURCES[source_index]
    if kind == "BG":
        return biblegateway_url(reference, data)
    if kind == "STEP":
        return step_url(reference, data)
    return step_parallel_url(reference)
