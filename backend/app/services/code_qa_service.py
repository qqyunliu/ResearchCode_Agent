from typing import Protocol

from app.llm.client import LlmClient
from app.rag.context_builder import RagContextBuilder
from app.retrieval.types import SearchHit
from app.schemas.agent import CodeQaResponse, ContextReferenceRead
from app.services.evidence_validator import (
    EVIDENCE_VALIDATION_FAILED_ANSWER,
    AnswerEvidenceValidator,
)
from app.services.conversation_memory import augment_question_with_memory

SYSTEM_PROMPT = """Answer only from the supplied code context.
Respond in the same language as the user's original question.
Cite claims with [n].
Every citation must directly support the sentence that uses it.
Treat each context block as independent evidence.
Do not claim that one symbol calls, injects, delegates to, supports, or is connected to another unless a supplied code snippet explicitly shows that relationship.
Distinguish a declaration from an observed call relationship.
Ignore retrieved blocks that are not needed to answer the question.
Do not invent files, symbols, APIs, or behavior.
Do not invent relationships.
If context is insufficient, state exactly what cannot be determined."""

NO_SUPPORTING_CODE_ANSWER = (
    "No supporting code was found for this question."
)


class CodeSearch(Protocol):
    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]: ...


class CodeQaService:
    def __init__(
        self,
        *,
        search: CodeSearch,
        context_builder: RagContextBuilder,
        llm: LlmClient,
        evidence_validator: AnswerEvidenceValidator | None = None,
    ) -> None:
        self.search = search
        self.context_builder = context_builder
        self.llm = llm
        self.evidence_validator = (
            evidence_validator or AnswerEvidenceValidator()
        )

    def answer(
        self,
        project_id: int,
        question: str,
        limit: int,
        conversation_memory: str = "",
    ) -> CodeQaResponse:
        effective_question = augment_question_with_memory(
            question,
            conversation_memory,
        )
        hits = self.search.search(project_id, effective_question, limit)
        retrieval_uncertainties = self._retrieval_uncertainties(hits)
        if not hits:
            return CodeQaResponse(
                answer=NO_SUPPORTING_CODE_ANSWER,
                references=[],
                uncertainties=retrieval_uncertainties,
            )

        context = self.context_builder.build(hits)
        if not context.references:
            return CodeQaResponse(
                answer=NO_SUPPORTING_CODE_ANSWER,
                references=[],
                uncertainties=retrieval_uncertainties,
            )

        user_prompt = (
            f"Question:\n{effective_question}\n\n"
            f"Code context:\n{context.text}"
        )
        answer = self.llm.complete(SYSTEM_PROMPT, user_prompt)
        references = [
            ContextReferenceRead.model_validate(reference)
            for reference in context.references
        ]
        validation = self.evidence_validator.validate(
            answer,
            references,
        )
        if validation.is_valid:
            return CodeQaResponse(
                answer=answer,
                references=references,
                uncertainties=retrieval_uncertainties,
            )

        repaired_answer = self.llm.complete(
            SYSTEM_PROMPT,
            self._repair_prompt(
                question=effective_question,
                context_text=context.text,
                previous_answer=answer,
                validation_messages=validation.uncertainties,
            ),
        )
        repaired_validation = self.evidence_validator.validate(
            repaired_answer,
            references,
        )
        if repaired_validation.is_valid:
            return CodeQaResponse(
                answer=repaired_answer,
                references=references,
                uncertainties=retrieval_uncertainties,
            )

        return CodeQaResponse(
            answer=EVIDENCE_VALIDATION_FAILED_ANSWER,
            references=references,
            uncertainties=[
                *retrieval_uncertainties,
                *validation.uncertainties,
                *repaired_validation.uncertainties,
                "Evidence validation repair limit reached.",
            ],
        )

    @staticmethod
    def _retrieval_uncertainties(hits: list[SearchHit]) -> list[str]:
        return list(
            dict.fromkeys(
                uncertainty
                for hit in hits
                for uncertainty in hit.uncertainties
            )
        )

    @staticmethod
    def _repair_prompt(
        *,
        question: str,
        context_text: str,
        previous_answer: str,
        validation_messages: tuple[str, ...],
    ) -> str:
        return (
            "Repair the previous answer so it uses only the supplied "
            "code context and only the listed citation IDs and file "
            "paths. Do not add any file path, line range, or citation "
            "that is absent from the context.\n\n"
            f"Question:\n{question}\n\n"
            f"Validation failures:\n"
            f"{CodeQaService._bullet_list(validation_messages)}\n\n"
            f"Previous answer:\n{previous_answer}\n\n"
            f"Code context:\n{context_text}"
        )

    @staticmethod
    def _bullet_list(items: tuple[str, ...]) -> str:
        if not items:
            return "- The answer did not pass evidence validation."
        return "\n".join(f"- {item}" for item in items)
