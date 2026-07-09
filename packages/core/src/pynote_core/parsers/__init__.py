"""Source loaders.

Each loader takes a path to bytes-on-disk and yields ParsedParts. The registry
is a plain dict keyed by `Source.kind`. New kinds (DOCX, web, audio, image, note)
plug in by adding to `LOADERS` in M8/M9.

Currently registered:
  - pdf   : page-per-part, header/footer hygiene + font-based heading detection
  - pptx  : slide-per-part, title as heading, tables + speaker notes
  - xlsx  : sheet-per-part, tab-serialized rows, sheet name as heading
  - csv   : single part, dialect-sniffed, tab-serialized rows
"""

from collections.abc import Callable, Iterable
from pathlib import Path

from pynote_core.parsers.pdf import parse_pdf
from pynote_core.parsers.pptx import parse_pptx
from pynote_core.parsers.spreadsheet import parse_csv, parse_spreadsheet
from pynote_core.parsers.types import ParsedPart

Loader = Callable[[Path], Iterable[ParsedPart]]

LOADERS: dict[str, Loader] = {
    "pdf": parse_pdf,
    "pptx": parse_pptx,
    "xlsx": parse_spreadsheet,
    "csv": parse_csv,
}


def parse(kind: str, path: Path) -> list[ParsedPart]:
    """Dispatch to the loader for `kind`. Returns a fully materialized list."""
    loader = LOADERS.get(kind)
    if loader is None:
        raise ValueError(f"No loader registered for kind={kind!r}")
    return list(loader(path))


__all__ = ["LOADERS", "Loader", "ParsedPart", "parse"]
