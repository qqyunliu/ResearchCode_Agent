import re
from collections import defaultdict
from collections.abc import Iterable

from app.parsers.base import EntityCandidate, FrontendRequestCandidate
from app.services.scanner import ScanIssueCandidate, ScannedFile
from app.utils.api_normalizer import normalize_api_path

_OBJECT = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)"
    r"\s*=\s*\{(?P<body>.*?)\}",
    re.DOTALL,
)
_PROPERTY = re.compile(
    r"(?P<name>[A-Za-z_$][\w$]*)\s*:\s*(?P<value>['\"](?:\\.|[^'\"])*['\"])",
)
_WRAPPER = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)"
    r"\s*=\s*(?:\((?P<params>[^)]*)\)|(?P<single>[A-Za-z_$][\w$]*))"
    r"\s*=>\s*",
)
_HTTP_CALL = re.compile(
    r"\b[A-Za-z_$][\w$]*\.(?P<method>get|post|put|patch|delete)"
    r"\s*\(\s*(?P<url>(?:[A-Za-z_$][\w$]*\.)?url)\b",
    re.IGNORECASE,
)
_REASON_CODES = {
    "dynamic_url": "FRONTEND_REQUEST_DYNAMIC_URL",
    "dynamic_method": "FRONTEND_REQUEST_DYNAMIC_METHOD",
    "ambiguous_constant": "FRONTEND_REQUEST_AMBIGUOUS_CONSTANT",
    "unknown_wrapper": "FRONTEND_REQUEST_UNKNOWN_WRAPPER",
}


class FrontendRequestResolver:
    def __init__(self, files: tuple[ScannedFile, ...]) -> None:
        frontend_files = tuple(
            file
            for file in files
            if file.language in {"vue", "javascript", "typescript"}
        )
        self.constants = self._constant_catalog(frontend_files)
        self.wrappers = self._wrapper_catalog(frontend_files)

    def resolve(
        self,
        candidates: Iterable[FrontendRequestCandidate],
    ) -> tuple[list[EntityCandidate], list[ScanIssueCandidate]]:
        entities: list[EntityCandidate] = []
        warnings: list[ScanIssueCandidate] = []
        for candidate in candidates:
            path, path_reason = self._resolve_path(candidate.url_expression)
            method, method_reason = self._resolve_method(candidate)
            if path is None or method is None:
                reason = path_reason or method_reason
                warnings.append(
                    ScanIssueCandidate(
                        file_path=candidate.file_path,
                        issue_type="analysis_warning",
                        reason_code=_REASON_CODES[reason],
                        message=(
                            "Frontend request was not indexed: "
                            f"{reason}."
                        ),
                    )
                )
                continue
            resolution = (
                "wrapper_default_method"
                if candidate.method_expression is None
                and candidate.callee.rsplit(".", 1)[-1]
                in self.wrappers
                else "static_request"
            )
            qualified_name = f"{method} {path}"
            entities.append(
                EntityCandidate(
                    local_key=(
                        f"frontend_api_call:{candidate.file_path}:"
                        f"{candidate.start_line}:{candidate.start_byte}:"
                        f"{candidate.callee}"
                    ),
                    entity_type="frontend_api_call",
                    name=qualified_name,
                    qualified_name=qualified_name,
                    file_path=candidate.file_path,
                    start_line=candidate.start_line,
                    end_line=candidate.end_line,
                    content=candidate.content,
                    metadata={
                        "client": candidate.callee,
                        "callee": candidate.callee,
                        "http_method": method,
                        "path": path,
                        "normalized_path": normalize_api_path(path),
                        "resolution": resolution,
                    },
                )
            )
        return entities, warnings

    def _resolve_path(self, expression: str) -> tuple[str | None, str | None]:
        literal = self._literal(expression)
        if literal is not None:
            return literal, None
        parts = expression.strip().split(".")
        if len(parts) < 2:
            return None, "dynamic_url"
        key = (parts[-2], parts[-1])
        values = self.constants.get(key, ())
        if len(values) == 1:
            return values[0], None
        if len(values) > 1:
            return None, "ambiguous_constant"
        return None, "dynamic_url"

    def _resolve_method(
        self,
        candidate: FrontendRequestCandidate,
    ) -> tuple[str | None, str | None]:
        if candidate.method_expression is not None:
            method = self._literal(candidate.method_expression)
            if method is None:
                method = candidate.method_expression
            method = method.upper()
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                return method, None
            return None, "dynamic_method"
        wrapper = candidate.callee.rsplit(".", 1)[-1]
        methods = self.wrappers.get(wrapper, ())
        if len(methods) == 1:
            return methods[0], None
        return None, "unknown_wrapper"

    @staticmethod
    def _literal(expression: str) -> str | None:
        value = expression.strip()
        if len(value) < 2 or value[0] not in {"'", '"', "`"}:
            return None
        if value[-1] != value[0]:
            return None
        raw = value[1:-1]
        if value[0] == "`" and not re.sub(r"\$\{.*?\}", "", raw).strip():
            return None
        return bytes(raw, "utf-8").decode("unicode_escape")

    @classmethod
    def _constant_catalog(
        cls,
        files: tuple[ScannedFile, ...],
    ) -> dict[tuple[str, str], tuple[str, ...]]:
        values: dict[tuple[str, str], set[str]] = defaultdict(set)
        for file in files:
            for object_match in _OBJECT.finditer(file.content):
                object_name = object_match.group("name")
                for property_match in _PROPERTY.finditer(
                    object_match.group("body")
                ):
                    value = cls._literal(property_match.group("value"))
                    if value is not None:
                        values[(object_name, property_match.group("name"))].add(value)
        return {key: tuple(sorted(value)) for key, value in values.items()}

    @classmethod
    def _wrapper_catalog(
        cls,
        files: tuple[ScannedFile, ...],
    ) -> dict[str, tuple[str, ...]]:
        values: dict[str, set[str]] = defaultdict(set)
        for file in files:
            for wrapper in _WRAPPER.finditer(file.content):
                body_start = wrapper.end()
                if (
                    body_start >= len(file.content)
                    or file.content[body_start] != "{"
                ):
                    body = file.content[body_start:].split(";", 1)[0]
                else:
                    body = cls._braced_body(file.content, body_start)
                if body is None:
                    continue
                matches = list(_HTTP_CALL.finditer(body))
                if len(matches) == 1:
                    values[wrapper.group("name")].add(
                        matches[0].group("method").upper()
                    )
        return {key: tuple(sorted(value)) for key, value in values.items()}

    @staticmethod
    def _braced_body(source: str, start: int) -> str | None:
        depth = 0
        quote: str | None = None
        escaped = False
        for index in range(start, len(source)):
            character = source[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                continue
            if character in {"'", '"', "`"}:
                quote = character
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    return source[start + 1 : index]
        return None
