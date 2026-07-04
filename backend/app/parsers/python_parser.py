import ast
from dataclasses import dataclass

from app.parsers.base import (
    EntityCandidate,
    ParseResult,
    RelationCandidate,
    source_slice,
)


@dataclass(frozen=True, slots=True)
class _Scope:
    kind: str
    name: str
    local_key: str


class PythonParser:
    def supports(self, language: str) -> bool:
        return language == "python"

    def parse(self, file_path: str, source: str) -> ParseResult:
        tree = ast.parse(source, filename=file_path)
        visitor = _PythonEntityVisitor(file_path=file_path, source=source)
        visitor.visit(tree)
        return ParseResult(
            entities=tuple(visitor.entities),
            relations=tuple(visitor.relations),
        )


class _PythonEntityVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str, source: str) -> None:
        self.file_path = file_path
        self.source = source
        self.entities: list[EntityCandidate] = []
        self.relations: list[RelationCandidate] = []
        self.scopes: list[_Scope] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = self._qualified_name(node.name)
        local_key = self._local_key(
            "python_class",
            qualified_name,
            node.lineno,
        )
        candidate = EntityCandidate(
            local_key=local_key,
            entity_type="python_class",
            name=node.name,
            qualified_name=qualified_name,
            file_path=self.file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            content=source_slice(
                self.source,
                node.lineno,
                node.end_lineno or node.lineno,
            ),
            metadata={
                "decorators": self._decorators(node.decorator_list),
                "bases": [ast.unparse(base) for base in node.bases],
            },
        )
        self.entities.append(candidate)

        self.scopes.append(
            _Scope(
                kind="class",
                name=node.name,
                local_key=local_key,
            )
        )
        self.generic_visit(node)
        self.scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, is_async=True)

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        is_async: bool,
    ) -> None:
        qualified_name = self._qualified_name(node.name)
        local_key = self._local_key(
            "python_function",
            qualified_name,
            node.lineno,
        )
        candidate = EntityCandidate(
            local_key=local_key,
            entity_type="python_function",
            name=node.name,
            qualified_name=qualified_name,
            file_path=self.file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            content=source_slice(
                self.source,
                node.lineno,
                node.end_lineno or node.lineno,
            ),
            metadata={
                "arguments": self._arguments(node.args),
                "decorators": self._decorators(node.decorator_list),
                "is_async": is_async,
            },
        )
        self.entities.append(candidate)

        if self.scopes and self.scopes[-1].kind == "class":
            self.relations.append(
                RelationCandidate(
                    source_key=self.scopes[-1].local_key,
                    target_key=local_key,
                    relation_type="CONTAINS",
                    confidence=1.0,
                    metadata={},
                )
            )

        self.scopes.append(
            _Scope(
                kind="function",
                name=node.name,
                local_key=local_key,
            )
        )
        self.generic_visit(node)
        self.scopes.pop()

    def _qualified_name(self, name: str) -> str:
        scope_names = [scope.name for scope in self.scopes]
        return ".".join([*scope_names, name])

    @staticmethod
    def _local_key(
        entity_type: str,
        qualified_name: str,
        start_line: int,
    ) -> str:
        return f"{entity_type}:{qualified_name}:{start_line}"

    @staticmethod
    def _decorators(
        decorators: list[ast.expr],
    ) -> list[str]:
        return [ast.unparse(decorator) for decorator in decorators]

    @staticmethod
    def _arguments(arguments: ast.arguments) -> list[str]:
        names = [
            argument.arg
            for argument in [*arguments.posonlyargs, *arguments.args]
        ]
        if arguments.vararg is not None:
            names.append(f"*{arguments.vararg.arg}")
        names.extend(argument.arg for argument in arguments.kwonlyargs)
        if arguments.kwarg is not None:
            names.append(f"**{arguments.kwarg.arg}")
        return names
