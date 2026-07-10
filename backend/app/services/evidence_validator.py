from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas.agent import ContextReferenceRead


EVIDENCE_VALIDATION_FAILED_ANSWER = (
    "The model answer did not pass evidence validation, so it was "
    "not returned. Please ask a narrower question or rebuild the "
    "index if the evidence looks incomplete."
)
_CITATION_PATTERN = re.compile(r"(?<!\w)\[(\d+)\]")
_CODE_FILE_EXTENSIONS = (
    "java",
    "py",
    "vue",
    "ts",
    "tsx",
    "js",
    "jsx",
    "json",
    "md",
    "xml",
    "yaml",
    "yml",
)
_PATH_PATTERN = re.compile(
    r"(?P<path>"
    r"(?:[A-Za-z0-9_.-]+[\\/])+"
    r"[A-Za-z0-9_.-]+"
    r"\.(?:"
    + "|".join(_CODE_FILE_EXTENSIONS)
    + r")"
    r"(?:[\\/][A-Za-z0-9_.-]+\.(?:"
    + "|".join(_CODE_FILE_EXTENSIONS)
    + r"))*"
    r")"
    r"(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?"
)
_STANDALONE_FILE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.\\/:-])"
    r"(?P<path>[A-Za-z0-9_.-]+\.(?:"
    + "|".join(_CODE_FILE_EXTENSIONS)
    + r"))"
    r"(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?"
)


@dataclass(frozen=True, slots=True)
class AnswerEvidenceValidationResult:
    invalid_citations: tuple[int, ...] = ()
    invalid_paths: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.invalid_citations and not self.invalid_paths

    @property
    def uncertainties(self) -> tuple[str, ...]:
        messages = [
            f"Answer cited unsupported reference [{citation}]."
            for citation in self.invalid_citations
        ]
        messages.extend(
            f"Answer mentioned unsupported file evidence: {path}."
            for path in self.invalid_paths
        )
        return tuple(messages)


class AnswerEvidenceValidator:
    def validate(
        self,
        answer: str,
        references: Sequence[ContextReferenceRead],
    ) -> AnswerEvidenceValidationResult:
        allowed_citations = {reference.citation for reference in references}
        allowed_paths = {
            self._normalize_path(reference.file_path)
            for reference in references
        }

        invalid_citations = tuple(
            dict.fromkeys(
                citation
                for citation in self._citations(answer)
                if citation not in allowed_citations
            )
        )
        invalid_paths = tuple(
            dict.fromkeys(
                location
                for location, path, start, end in self._path_locations(
                    answer
                )
                if not self._path_is_supported(path, allowed_paths)
                or not self._line_range_is_supported(
                    path,
                    start,
                    end,
                    references,
                )
            )
        )
        return AnswerEvidenceValidationResult(
            invalid_citations=invalid_citations,
            invalid_paths=invalid_paths,
        )

    @staticmethod
    def _citations(answer: str) -> tuple[int, ...]:
        return tuple(
            int(match.group(1))
            for match in _CITATION_PATTERN.finditer(answer)
        )

    @staticmethod
    def _path_locations(
        answer: str,
    ) -> tuple[tuple[str, str, int | None, int | None], ...]:
        locations: list[tuple[str, str, int | None, int | None]] = []
        occupied_spans: list[tuple[int, int]] = []
        for match in _PATH_PATTERN.finditer(answer):
            path = match.group("path")
            start_text = match.group("start")
            end_text = match.group("end")
            start = int(start_text) if start_text is not None else None
            end = int(end_text) if end_text is not None else start
            locations.append((match.group(0), path, start, end))
            occupied_spans.append(match.span())

        for match in _STANDALONE_FILE_PATTERN.finditer(answer):
            if any(
                span_start <= match.start() < span_end
                for span_start, span_end in occupied_spans
            ):
                continue
            path = match.group("path")
            start_text = match.group("start")
            end_text = match.group("end")
            start = int(start_text) if start_text is not None else None
            end = int(end_text) if end_text is not None else start
            locations.append((match.group(0), path, start, end))
        return tuple(locations)

    @classmethod
    def _path_is_supported(
        cls,
        path: str,
        allowed_paths: set[str],
    ) -> bool:
        normalized_path = cls._normalize_path(path)
        if normalized_path in allowed_paths:
            return True
        if "/" in normalized_path:
            return False
        return any(
            allowed_path.rsplit("/", 1)[-1] == normalized_path
            for allowed_path in allowed_paths
        )

    @classmethod
    def _line_range_is_supported(
        cls,
        path: str,
        start: int | None,
        end: int | None,
        references: Sequence[ContextReferenceRead],
    ) -> bool:
        if start is None or end is None:
            return True
        normalized_path = cls._normalize_path(path)
        return any(
            cls._reference_matches_path(reference, normalized_path)
            and reference.start_line <= start
            and end <= reference.end_line
            for reference in references
        )

    @classmethod
    def _reference_matches_path(
        cls,
        reference: ContextReferenceRead,
        normalized_path: str,
    ) -> bool:
        reference_path = cls._normalize_path(reference.file_path)
        if reference_path == normalized_path:
            return True
        if "/" in normalized_path:
            return False
        return reference_path.rsplit("/", 1)[-1] == normalized_path

    @staticmethod
    def _normalize_path(path: str) -> str:
        return path.replace("\\", "/").strip().rstrip(".,;:)")
