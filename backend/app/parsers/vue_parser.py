import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tree_sitter_language_pack import PackConfig, configure, get_parser

from app.parsers.base import FrontendRequestCandidate, ParseResult

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
            entities.extend(extractor.candidates)
        return ParseResult(frontend_request_candidates=tuple(entities))

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
        self.candidates: list[FrontendRequestCandidate] = []

    def visit(self, node: object) -> None:
        if node.kind() == "call_expression":
            candidate = self._request_candidate(node)
            if candidate is not None:
                self.candidates.append(candidate)
        for child in self._named_children(node):
            self.visit(child)

    def _request_candidate(
        self,
        node: object,
    ) -> FrontendRequestCandidate | None:
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
            argument_nodes = self._named_children(arguments)
            if method in _HTTP_METHODS and client in {
                "axios", "request", "http", "service",
            }:
                if not argument_nodes:
                    return None
                return self._candidate(
                    node,
                    f"{client}.{method}",
                    argument_nodes[0],
                    method.upper(),
                )
            if method == "request":
                return self._object_request_candidate(
                    node,
                    f"{client}.request",
                    argument_nodes,
                )
            return None

        if function.kind() != "identifier":
            return None
        client = self._text(function)
        argument_nodes = self._named_children(arguments)
        if client == "fetch":
            if not argument_nodes:
                return None
            method = "GET"
            if len(argument_nodes) > 1 and argument_nodes[1].kind() == "object":
                method_node = self._object_values(argument_nodes[1]).get("method")
                if method_node is not None:
                    method = self._text(method_node)
            return self._candidate(node, "fetch", argument_nodes[0], method)
        if client == "axios":
            return self._object_request_candidate(node, "axios", argument_nodes)
        if client != "request":
            return None
        return self._object_request_candidate(node, "request", argument_nodes)

    def _object_request_candidate(
        self,
        node: object,
        callee: str,
        argument_nodes: list[object],
    ) -> FrontendRequestCandidate | None:
        if not argument_nodes or argument_nodes[0].kind() != "object":
            return None
        values = self._object_values(argument_nodes[0])
        path_node = values.get("url")
        if path_node is None:
            return None
        method_node = values.get("method")
        return self._candidate(
            node,
            callee,
            path_node,
            self._text(method_node) if method_node is not None else None,
        )

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

    def _candidate(
        self,
        node: object,
        callee: str,
        url_node: object,
        method_expression: str | None,
    ) -> FrontendRequestCandidate:
        start_line = self.block.start_line + node.start_position().row
        end_line = self.block.start_line + node.end_position().row
        return FrontendRequestCandidate(
            file_path=self.file_path,
            start_line=start_line,
            end_line=end_line,
            start_byte=node.start_byte(),
            content=self._text(node),
            callee=callee,
            url_expression=self._text(url_node),
            method_expression=method_expression,
        )

    def _text(self, node: object) -> str:
        return self.source_bytes[node.start_byte() : node.end_byte()].decode("utf-8")

    @staticmethod
    def _named_children(node: object) -> list[object]:
        return [
            node.named_child(index)
            for index in range(node.named_child_count())
        ]
