"""Re-export of pynote_core.citations — kept so existing M3 imports work."""

from pynote_core.citations import (
    ParsedAnswer,
    ResolvedCitation,
    citation_to_jsonable,
    fidelity,
    pack_search_results,
    parse_response,
)

__all__ = [
    "ParsedAnswer",
    "ResolvedCitation",
    "citation_to_jsonable",
    "fidelity",
    "pack_search_results",
    "parse_response",
]
