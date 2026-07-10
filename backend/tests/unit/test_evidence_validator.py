from app.schemas.agent import ContextReferenceRead
from app.services.evidence_validator import AnswerEvidenceValidator


def reference(
    *,
    citation: int = 1,
    file_path: str = "backend/src/AlertController.java",
    start_line: int = 4,
    end_line: int = 7,
) -> ContextReferenceRead:
    return ContextReferenceRead(
        citation=citation,
        entity_id=5,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        entity_type="java_method",
        qualified_name="AlertController.getAlert",
    )


def test_accepts_answer_with_known_citation_and_path() -> None:
    validator = AnswerEvidenceValidator()

    result = validator.validate(
        "Implemented in backend/src/AlertController.java:4-7 [1].",
        [reference()],
    )

    assert result.is_valid is True
    assert result.invalid_citations == ()
    assert result.invalid_paths == ()
    assert result.uncertainties == ()


def test_rejects_unknown_citation_id() -> None:
    validator = AnswerEvidenceValidator()

    result = validator.validate(
        "Implemented in AlertController [2].",
        [reference()],
    )

    assert result.is_valid is False
    assert result.invalid_citations == (2,)
    assert result.invalid_paths == ()
    assert result.uncertainties == (
        "Answer cited unsupported reference [2].",
    )


def test_rejects_unknown_file_path() -> None:
    validator = AnswerEvidenceValidator()

    result = validator.validate(
        "Implemented in backend/src/AlertController.java/AlertService.java [1].",
        [reference()],
    )

    assert result.is_valid is False
    assert result.invalid_citations == ()
    assert result.invalid_paths == (
        "backend/src/AlertController.java/AlertService.java",
    )


def test_rejects_unknown_standalone_file_name() -> None:
    validator = AnswerEvidenceValidator()

    result = validator.validate(
        "Implemented in GhostController.java [1].",
        [reference()],
    )

    assert result.is_valid is False
    assert result.invalid_paths == ("GhostController.java",)


def test_accepts_unique_known_standalone_file_name() -> None:
    validator = AnswerEvidenceValidator()

    result = validator.validate(
        "Implemented in AlertController.java [1].",
        [reference()],
    )

    assert result.is_valid is True


def test_rejects_known_file_path_with_out_of_range_lines() -> None:
    validator = AnswerEvidenceValidator()

    result = validator.validate(
        "Implemented in backend/src/AlertController.java:100-120 [1].",
        [reference()],
    )

    assert result.is_valid is False
    assert result.invalid_paths == (
        "backend/src/AlertController.java:100-120",
    )
