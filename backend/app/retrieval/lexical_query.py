"""Deterministic lexical-term parsing for keyword retrieval."""

from __future__ import annotations

from collections.abc import Iterator
import re
import unicodedata


_API_PATH_RE = re.compile(r"/(?:[\w{}:.-]+/)*[\w{}:.-]+", re.UNICODE)
_DOT_SEPARATOR_RE = re.compile(r"\.+")
_COMPONENT_SEPARATOR_RE = re.compile(r"[_$-]+")
_CAMEL_STRUCTURE_RE = re.compile(r"[a-z\d][A-Z]|[A-Z]{2,}[a-z]")
_CAMEL_COMPONENT_RE = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+|[^\W\d_]+",
    re.UNICODE,
)

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "for",
        "in",
        "is",
        "of",
        "the",
        "to",
        "what",
        "where",
        "which",
    }
)
_SAFE_STANDALONE_SYMBOLS = frozenset({"%", "_", "$"})


def parse_lexical_terms(query: str, *, max_terms: int = 12) -> tuple[str, ...]:
    """Return ordered, normalized lexical terms extracted from *query*.

    API paths and structured identifiers remain searchable as complete terms;
    their individual components are appended to improve partial matching.
    """

    if max_terms < 1:
        raise ValueError("max_terms must be at least 1")

    query = unicodedata.normalize("NFC", query)
    stripped_query = query.strip()
    if stripped_query in _SAFE_STANDALONE_SYMBOLS:
        return (stripped_query,)

    terms: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> bool:
        normalized = candidate.casefold()
        if not normalized or normalized in _STOPWORDS or normalized in seen:
            return False
        seen.add(normalized)
        terms.append(normalized)
        return len(terms) >= max_terms

    path_spans: list[tuple[int, int]] = []
    for match in _API_PATH_RE.finditer(query):
        path_spans.append(match.span())
        if add(match.group()):
            return tuple(terms)
        for segment in match.group().split("/"):
            segment = segment.strip("{}")
            if not segment:
                continue
            if add(segment):
                return tuple(terms)
            for component in _camel_components(segment):
                if add(component):
                    return tuple(terms)

    path_span_index = 0
    for word_start, token in _iter_identifier_tokens(query):
        while (
            path_span_index < len(path_spans)
            and path_spans[path_span_index][1] <= word_start
        ):
            path_span_index += 1
        if (
            path_span_index < len(path_spans)
            and path_spans[path_span_index][0] <= word_start
            < path_spans[path_span_index][1]
        ):
            continue
        if add(token):
            return tuple(terms)

        dotted_segments = _DOT_SEPARATOR_RE.split(token)
        is_structured = (
            len(dotted_segments) > 1
            or "_" in token
            or "$" in token
            or "-" in token
            or _CAMEL_STRUCTURE_RE.search(token) is not None
        )
        if not is_structured:
            continue

        for segment in dotted_segments:
            if len(dotted_segments) > 1 and add(segment):
                return tuple(terms)
            for structure_component in _COMPONENT_SEPARATOR_RE.split(segment):
                if not structure_component:
                    continue
                for camel_component in _camel_components(structure_component):
                    if add(camel_component):
                        return tuple(terms)

    return tuple(terms)


def _camel_components(identifier: str) -> tuple[str, ...]:
    if not identifier.isascii():
        return (identifier,)
    return tuple(match.group() for match in _CAMEL_COMPONENT_RE.finditer(identifier))


def _iter_identifier_tokens(query: str) -> Iterator[tuple[int, str]]:
    position = 0
    while position < len(query):
        if not _is_identifier_start(query[position]):
            position += 1
            continue

        start = position
        position += 1
        while position < len(query):
            character = query[position]
            if _is_identifier_continue(character):
                position += 1
                continue
            if (
                character in ".-"
                and position + 1 < len(query)
                and _is_identifier_start(query[position + 1])
            ):
                position += 1
                continue
            break
        yield start, query[start:position]


def _is_identifier_start(character: str) -> bool:
    category = unicodedata.category(character)
    return category.startswith("L") or category in {"Nl", "Sc", "Pc"}


def _is_identifier_continue(character: str) -> bool:
    category = unicodedata.category(character)
    return _is_identifier_start(character) or category.startswith(("M", "N")) or category == "Cf"
