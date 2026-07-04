import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tree_sitter_language_pack import PackConfig, configure, get_parser

from app.parsers.base import EntityCandidate, ParseResult
from app.utils.api_normalizer import normalize_api_path

_SCRIPT_BLOCK = re.compile(
    r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_LANG_ATTRIBUTE = re.compile(
    r"""\blang\s*=\s*["'](?P<lang>[^"']+)["']""",
    re.IGNORECASE,
)
_TEMPLATE_SUBSTITUTION = re.compile(r"\$\{.*?\}", re.DOTALL)
_CACHE_DIR = Path(tempfile.gettempdir()) / "research-code-agent-tree-sitter"
_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@dataclass(frozen=True, slots=True)
class _SourceBlock:
    source: str
    language: str
    start_line: int


@dataclass(frozen=True, slots=True)
class _RequestCall:
    client: str
    http_method: str
    path: str


class VueParser:
    def supports(self, language: str) -> bool:
        return language in {"vue", "javascript", "typescript"}

    def parse(self, file_path: str, source: str) -> ParseResult:
        entities: list[EntityCandidate] = []
        for block in self._source_blocks(file_path, source):
            configure(PackConfig(cache_dir=str(_CACHE_DIR)))
            tree = get_parser(block.language).parse(block.source)
            extractor = _RequestExtractor(file_path, block)
            extractor.visit(tree.root_node())
            entities.extend(extractor.entities)
        return ParseResult(entities=tuple(entities))

    @staticmethod
    def _source_blocks(file_path: str, source: str) -> list[_SourceBlock]:
        if Path(file_path).suffix.lower() != ".vue":
            language = (
                "typescript"
                if Path(file_path).suffix.lower() in {".ts", ".tsx"}
                else "javascript"
            )
            return [_SourceBlock(source, language, 1)]

        blocks = []
        for match in _SCRIPT_BLOCK.finditer(source):
            lang_match = _LANG_ATTRIBUTE.search(match.group("attrs"))
            lang = lang_match.group("lang").lower() if lang_match else "js"
            language = "typescript" if lang in {"ts", "typescript"} else "javascript"
            start_line = source[: match.start("body")].count("\n") + 1
            blocks.append(_SourceBlock(match.group("body"), language, start_line))
        return blocks


class _RequestExtractor:
    def __init__(self, file_path: str, block: _SourceBlock) -> None:
        self.file_path = file_path
        self.block = block
        self.source_bytes = block.source.encode("utf-8")
        self.entities: list[EntityCandidate] = []

    def visit(self, node: object) -> None:
        if node.kind() == "call_expression":
            request = self._request_call(node)
            if request is not None:
                self._add_entity(node, request)
        for child in self._named_children(node):
            self.visit(child)

    def _request_call(self, node: object) -> _RequestCall | None:
        function = node.child_by_field_name("function")
        arguments = node.child_by_field_name("arguments")
        if function is None or arguments is None:
            return None

        if function.kind() == "member_expression":
            client_node = function.child_by_field_name("object")
            method_node = function.child_by_field_name("property")
            if client_node is None or method_node is None:
                return None
            client = self._text(client_node)
            method = self._text(method_node).lower()
            if client not in {"axios", "request"} or method not in _HTTP_METHODS:
                return None
            argument_nodes = self._named_children(arguments)
            if not argument_nodes:
                return None
            path = self._static_path(argument_nodes[0])
            if path is None:
                return None
            return _RequestCall(client, method.upper(), path)

        if function.kind() != "identifier" or self._text(function) != "request":
            return None
        argument_nodes = self._named_children(arguments)
        if not argument_nodes or argument_nodes[0].kind() != "object":
            return None
        values = self._object_values(argument_nodes[0])
        path_node = values.get("url")
        method_node = values.get("method")
        if path_node is None or method_node is None:
            return None
        path = self._static_path(path_node)
        method = self._static_string(method_node)
        if path is None or method is None or method.lower() not in _HTTP_METHODS:
            return None
        return _RequestCall("request", method.upper(), path)

    def _object_values(self, node: object) -> dict[str, object]:
        values = {}
        for child in self._named_children(node):
            if child.kind() != "pair":
                continue
            key_node = child.child_by_field_name("key")
            value_node = child.child_by_field_name("value")
            if key_node is None or value_node is None:
                continue
            key = self._text(key_node).strip("\"'")
            values[key] = value_node
        return values

    def _static_path(self, node: object) -> str | None:
        if node.kind() == "string":
            return self._static_string(node)
        if node.kind() != "template_string":
            return None
        raw = self._text(node)[1:-1]
        literal_text = _TEMPLATE_SUBSTITUTION.sub("", raw)
        if not literal_text.strip():
            return None
        return raw

    def _static_string(self, node: object) -> str | None:
        if node.kind() != "string":
            return None
        raw = self._text(node)
        if len(raw) < 2 or raw[0] not in {"'", '"'}:
            return None
        return self._decode_escapes(raw[1:-1])

    @staticmethod
    def _decode_escapes(value: str) -> str:
        escapes = {
            "\\\\": "\\",
            "\\/": "/",
            '\\"': '"',
            "\\'": "'",
            "\\n": "\n",
            "\\r": "\r",
            "\\t": "\t",
        }
        return re.sub(
            r"""\\[\\/"'nrt]""",
            lambda match: escapes.get(match.group(0), match.group(0)),
            value,
        )

    def _add_entity(self, node: object, request: _RequestCall) -> None:
        start_line = self.block.start_line + node.start_position().row
        end_line = self.block.start_line + node.end_position().row
        qualified_name = f"{request.http_method} {request.path}"
        local_key = (
            f"frontend_api_call:{request.http_method}:{request.path}:"
            f"{start_line}:{node.start_byte()}"
        )
        self.entities.append(
            EntityCandidate(
                local_key=local_key,
                entity_type="frontend_api_call",
                name=qualified_name,
                qualified_name=qualified_name,
                file_path=self.file_path,
                start_line=start_line,
                end_line=end_line,
                content=self._text(node),
                metadata={
                    "client": request.client,
                    "http_method": request.http_method,
                    "path": request.path,
                    "normalized_path": normalize_api_path(request.path),
                },
            )
        )

    def _text(self, node: object) -> str:
        return self.source_bytes[node.start_byte() : node.end_byte()].decode("utf-8")

    @staticmethod
    def _named_children(node: object) -> list[object]:
        return [
            node.named_child(index)
            for index in range(node.named_child_count())
        ]
