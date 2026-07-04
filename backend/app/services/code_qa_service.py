from typing import Protocol

from app.llm.client import LlmClient
from app.rag.context_builder import RagContextBuilder
from app.retrieval.types import SearchHit
from app.schemas.agent import CodeQaResponse, ContextReferenceRead

SYSTEM_PROMPT = """Answer only from the supplied code context.
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
    ) -> None:
        self.search = search
        self.context_builder = context_builder
        self.llm = llm

    def answer(
        self,
        project_id: int,
        question: str,
        limit: int,
    ) -> CodeQaResponse:
        hits = self.search.search(project_id, question, limit)
        if not hits:
            return CodeQaResponse(
                answer=NO_SUPPORTING_CODE_ANSWER,
                references=[],
            )

        context = self.context_builder.build(hits)
        if not context.references:
            return CodeQaResponse(
                answer=NO_SUPPORTING_CODE_ANSWER,
                references=[],
            )

        user_prompt = (
            f"Question:\n{question}\n\n"
            f"Code context:\n{context.text}"
        )
        answer = self.llm.complete(SYSTEM_PROMPT, user_prompt)
        return CodeQaResponse(
            answer=answer,
            references=[
                ContextReferenceRead.model_validate(reference)
                for reference in context.references
            ],
        )
