import pytest

from app.parsers.python_parser import PythonParser

SOURCE = '''\
@registered
class Detector:
    @cached
    def predict(
        self,
        values,
        /,
        threshold=0.5,
        *extra,
        device="cpu",
        **options,
    ):
        return values


async def train(data, /, epochs=1, *extra, device, **options):
    def prepare(batch):
        return batch

    return prepare(data)
'''


def test_python_parser_supports_only_python() -> None:
    parser = PythonParser()

    assert parser.supports("python") is True
    assert parser.supports("java") is False


def test_python_parser_extracts_qualified_entities() -> None:
    result = PythonParser().parse("algorithm/detector.py", SOURCE)
    entities = {
        (entity.entity_type, entity.qualified_name): entity
        for entity in result.entities
    }

    assert set(entities) == {
        ("python_class", "Detector"),
        ("python_function", "Detector.predict"),
        ("python_function", "train"),
        ("python_function", "train.prepare"),
    }
    assert entities[("python_class", "Detector")].metadata == {
        "decorators": ["registered"],
        "bases": [],
    }
    assert entities[("python_function", "Detector.predict")].metadata == {
        "arguments": [
            "self",
            "values",
            "threshold",
            "*extra",
            "device",
            "**options",
        ],
        "decorators": ["cached"],
        "is_async": False,
    }
    assert entities[("python_function", "train")].metadata == {
        "arguments": [
            "data",
            "epochs",
            "*extra",
            "device",
            "**options",
        ],
        "decorators": [],
        "is_async": True,
    }


def test_python_parser_preserves_lines_and_source_content() -> None:
    result = PythonParser().parse("algorithm/detector.py", SOURCE)
    entities = {
        entity.qualified_name: entity for entity in result.entities
    }
    method = entities["Detector.predict"]
    nested = entities["train.prepare"]

    assert method.start_line == 4
    assert method.end_line == 13
    assert method.content.startswith("    def predict(")
    assert method.content.endswith("        return values")
    assert nested.start_line == 17
    assert nested.end_line == 18
    assert nested.content == (
        "    def prepare(batch):\n"
        "        return batch"
    )


def test_python_parser_links_class_to_direct_method() -> None:
    result = PythonParser().parse("algorithm/detector.py", SOURCE)

    assert len(result.relations) == 1
    relation = result.relations[0]
    assert relation.source_key.startswith("python_class:Detector:")
    assert relation.target_key.startswith(
        "python_function:Detector.predict:"
    )
    assert relation.relation_type == "CONTAINS"
    assert relation.confidence == 1.0


def test_python_parser_propagates_syntax_error() -> None:
    with pytest.raises(SyntaxError):
        PythonParser().parse("broken.py", "def broken(:\n")
