import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tree_sitter_language_pack import PackConfig, configure, get_parser

from app.parsers.base import EntityCandidate, ParseResult, RelationCandidate
from app.utils.api_normalizer import normalize_api_path

_ANNOTATION_NAME = re.compile(r"@(?:[\w.]+\.)?(\w+)")
_STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')
_NAMED_PATH = re.compile(
    r"\b(?:value|path)\s*=\s*"
    r'(\{(?:[^{}"]|"(?:\\.|[^"\\])*")*\}|"(?:\\.|[^"\\])*")',
    re.DOTALL,
)
_POSITIONAL_PATH = re.compile(
    r'^\s*(\{(?:[^{}"]|"(?:\\.|[^"\\])*")*\}|"(?:\\.|[^"\\])*")',
    re.DOTALL,
)
_REQUEST_METHOD = re.compile(r"RequestMethod\.([A-Z]+)")

_SHORTCUT_METHODS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}
_MAPPING_ANNOTATIONS = {"RequestMapping", *_SHORTCUT_METHODS}
_CONTROLLER_ANNOTATIONS = {"Controller", "RestController"}
_CACHE_DIR = Path(tempfile.gettempdir()) / "research-code-agent-tree-sitter"


@dataclass(frozen=True, slots=True)
class _Annotation:
    name: str
    text: str


class JavaParser:
    def supports(self, language: str) -> bool:
        return language == "java"

    def parse(self, file_path: str, source: str) -> ParseResult:
        source_bytes = source.encode("utf-8")
        configure(PackConfig(cache_dir=str(_CACHE_DIR)))
        tree = get_parser("java").parse(source)
        extractor = _JavaExtractor(file_path, source, source_bytes)
        extractor.visit(tree.root_node())
        return ParseResult(
            entities=tuple(extractor.entities),
            relations=tuple(extractor.relations),
        )


class _JavaExtractor:
    def __init__(self, file_path: str, source: str, source_bytes: bytes) -> None:
        self.file_path = file_path
        self.source = source
        self.source_bytes = source_bytes
        self.entities: list[EntityCandidate] = []
        self.relations: list[RelationCandidate] = []

    def visit(self, node: object, enclosing_classes: tuple[str, ...] = ()) -> None:
        if node.kind() == "class_declaration":
            self._visit_class(node, enclosing_classes)
            return
        for child in self._named_children(node):
            self.visit(child, enclosing_classes)

    def _visit_class(
        self,
        node: object,
        enclosing_classes: tuple[str, ...],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self._text(name_node)
        qualified_name = ".".join((*enclosing_classes, name))
        start_line, end_line = self._lines(node)
        local_key = f"java_class:{qualified_name}:{start_line}"
        annotations = self._annotations(node)
        annotation_names = [annotation.name for annotation in annotations]

        self.entities.append(
            EntityCandidate(
                local_key=local_key,
                entity_type="java_class",
                name=name,
                qualified_name=qualified_name,
                file_path=self.file_path,
                start_line=start_line,
                end_line=end_line,
                content=self._text(node),
                metadata={
                    "annotations": annotation_names,
                    "is_controller": bool(
                        _CONTROLLER_ANNOTATIONS.intersection(annotation_names)
                    ),
                    "is_service": "Service" in annotation_names,
                },
            )
        )

        base_paths = self._class_paths(annotations)
        is_controller = bool(
            _CONTROLLER_ANNOTATIONS.intersection(annotation_names)
        )
        body = node.child_by_field_name("body")
        if body is None:
            return
        for child in self._named_children(body):
            if child.kind() == "method_declaration":
                self._visit_method(
                    child,
                    qualified_name,
                    local_key,
                    base_paths,
                    is_controller,
                )
            elif child.kind() == "class_declaration":
                self._visit_class(child, (*enclosing_classes, name))

    def _visit_method(
        self,
        node: object,
        class_name: str,
        class_key: str,
        base_paths: list[str],
        is_controller: bool,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self._text(name_node)
        qualified_name = f"{class_name}.{name}"
        start_line, end_line = self._lines(node)
        local_key = f"java_method:{qualified_name}:{start_line}"
        annotations = self._annotations(node)
        parameters = node.child_by_field_name("parameters")
        return_type = node.child_by_field_name("type")

        self.entities.append(
            EntityCandidate(
                local_key=local_key,
                entity_type="java_method",
                name=name,
                qualified_name=qualified_name,
                file_path=self.file_path,
                start_line=start_line,
                end_line=end_line,
                content=self._text(node),
                metadata={
                    "annotations": [
                        annotation.name for annotation in annotations
                    ],
                    "parameters": self._text(parameters) if parameters else "()",
                    "return_type": (
                        self._text(return_type) if return_type else None
                    ),
                },
            )
        )
        self.relations.append(
            RelationCandidate(
                source_key=class_key,
                target_key=local_key,
                relation_type="CONTAINS",
                confidence=1.0,
                metadata={},
            )
        )

        if not is_controller:
            return
        for annotation in annotations:
            if annotation.name not in _MAPPING_ANNOTATIONS:
                continue
            paths = self._annotation_paths(annotation.text)
            methods = self._annotation_methods(annotation)
            for base_path in base_paths:
                for method_path in paths:
                    path = self._join_paths(base_path, method_path)
                    for http_method in methods:
                        self._add_api(
                            node,
                            class_name,
                            name,
                            local_key,
                            http_method,
                            path,
                        )

    def _add_api(
        self,
        node: object,
        class_name: str,
        method_name: str,
        method_key: str,
        http_method: str,
        path: str,
    ) -> None:
        start_line, end_line = self._lines(node)
        qualified_name = f"{http_method} {path}"
        local_key = (
            f"backend_api:{http_method}:{path}:"
            f"{class_name}.{method_name}:{start_line}"
        )
        self.entities.append(
            EntityCandidate(
                local_key=local_key,
                entity_type="backend_api",
                name=qualified_name,
                qualified_name=qualified_name,
                file_path=self.file_path,
                start_line=start_line,
                end_line=end_line,
                content=self._text(node),
                metadata={
                    "http_method": http_method,
                    "path": path,
                    "normalized_path": normalize_api_path(path),
                    "controller_class": class_name,
                    "handler_method": method_name,
                },
            )
        )
        self.relations.append(
            RelationCandidate(
                source_key=local_key,
                target_key=method_key,
                relation_type="DEFINES_API",
                confidence=1.0,
                metadata={},
            )
        )

    def _annotations(self, node: object) -> list[_Annotation]:
        modifiers = next(
            (
                child
                for child in self._named_children(node)
                if child.kind() == "modifiers"
            ),
            None,
        )
        if modifiers is None:
            return []
        annotations = []
        for child in self._named_children(modifiers):
            if child.kind() not in {"annotation", "marker_annotation"}:
                continue
            text = self._text(child)
            match = _ANNOTATION_NAME.search(text)
            if match:
                annotations.append(_Annotation(match.group(1), text))
        return annotations

    def _class_paths(self, annotations: list[_Annotation]) -> list[str]:
        paths = [
            path
            for annotation in annotations
            if annotation.name == "RequestMapping"
            for path in self._annotation_paths(annotation.text)
        ]
        return paths or ["/"]

    @staticmethod
    def _annotation_methods(annotation: _Annotation) -> list[str]:
        shortcut = _SHORTCUT_METHODS.get(annotation.name)
        if shortcut:
            return [shortcut]
        methods = _REQUEST_METHOD.findall(annotation.text)
        return methods or ["ANY"]

    @staticmethod
    def _annotation_paths(annotation_text: str) -> list[str]:
        arguments_start = annotation_text.find("(")
        if arguments_start == -1:
            return ["/"]
        arguments = annotation_text[arguments_start + 1 : annotation_text.rfind(")")]
        match = _NAMED_PATH.search(arguments) or _POSITIONAL_PATH.match(arguments)
        if not match:
            return ["/"]
        paths = [
            json.loads(literal)
            for literal in _STRING_LITERAL.findall(match.group(1))
        ]
        return paths or ["/"]

    @staticmethod
    def _join_paths(base_path: str, method_path: str) -> str:
        segments = [
            segment.strip("/")
            for segment in (base_path, method_path)
            if segment.strip("/")
        ]
        return f"/{'/'.join(segments)}" if segments else "/"

    def _text(self, node: object) -> str:
        return self.source_bytes[node.start_byte() : node.end_byte()].decode("utf-8")

    @staticmethod
    def _lines(node: object) -> tuple[int, int]:
        return node.start_position().row + 1, node.end_position().row + 1

    @staticmethod
    def _named_children(node: object) -> list[object]:
        return [
            node.named_child(index)
            for index in range(node.named_child_count())
        ]
