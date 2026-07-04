from app.parsers.base import ParseResult, SourceParser
from app.parsers.java_parser import JavaParser
from app.parsers.python_parser import PythonParser
from app.parsers.vue_parser import VueParser
from app.services.scanner import ScannedFile


class ParserRegistry:
    def __init__(self, parsers: tuple[SourceParser, ...] | None = None) -> None:
        self.parsers = parsers or (
            JavaParser(),
            VueParser(),
            PythonParser(),
        )

    def parse(self, scanned_file: ScannedFile) -> ParseResult:
        for parser in self.parsers:
            if parser.supports(scanned_file.language):
                return parser.parse(
                    scanned_file.file_path,
                    scanned_file.content,
                )
        return ParseResult()
