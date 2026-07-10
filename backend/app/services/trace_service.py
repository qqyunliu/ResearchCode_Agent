from collections.abc import Iterable
from typing import Protocol

from app.errors import DomainError
from app.graph.types import GraphResult
from app.llm.client import LlmClient
from app.rag.context_builder import RagContext
from app.rag.graph_retriever import GraphRetrievalResult
from app.schemas.agent import ContextReferenceRead, TraceResponse
from app.schemas.graph import GraphResponse
from app.services.evidence_validator import (
    EVIDENCE_VALIDATION_FAILED_ANSWER,
    AnswerEvidenceValidator,
)
from app.services.relationship_limits import append_relationship_limits
from app.services.conversation_memory import augment_question_with_memory

TRACE_SYSTEM_PROMPT = """Answer only from the supplied indexed-code evidence.
Respond in the same language as the user's original question.
Describe the request chain, involved files, and uncertain or missing links.
Cite code claims with [n], and make every citation directly support its claim.
Treat the Stored graph edges section as authoritative relationship evidence.
Do not claim a controller calls a service unless a stored CALLS_METHOD edge or an explicit supplied code snippet proves it.
Never invent files, symbols, APIs, edges, or runtime behavior.
Clearly label every unsupported segment as: cannot be determined from indexed code."""

NO_TRACE_EVIDENCE_ANSWER = (
    "No supporting graph or code evidence was found for this trace."
)
EXPECTED_CHAIN_RELATIONS = (
    "REQUESTS_API",
    "DEFINES_API",
    "CALLS_METHOD",
)
GRAPH_EXPANSION_UNCERTAINTY = (
    "Graph expansion was unavailable; "
    "the answer uses direct search evidence only."
)


class TraceRetriever(Protocol):
    def retrieve(
        self,
        project_id: int,
        query: str,
        *,
        limit: int,
        max_depth: int,
    ) -> list[GraphRetrievalResult]: ...


class TraceGraph(Protocol):
    def expand_entities(
        self,
        project_id: int,
        entity_ids: Iterable[int],
        *,
        max_depth: int,
    ) -> GraphResult: ...


class TraceContextBuilder(Protocol):
    def build(
        self,
        results: list[GraphRetrievalResult],
        graph: GraphResult,
    ) -> RagContext: ...


class TraceService:
    def __init__(
        self,
        *,
        retriever: TraceRetriever,
        graph: TraceGraph,
        context_builder: TraceContextBuilder,
        llm: LlmClient,
        evidence_validator: AnswerEvidenceValidator | None = None,
    ) -> None:
        self.retriever = retriever
        self.graph = graph
        self.context_builder = context_builder
        self.llm = llm
        self.evidence_validator = (
            evidence_validator or AnswerEvidenceValidator()
        )

    def answer(
        self,
        project_id: int,
        question: str,
        *,
        limit: int,
        max_depth: int,
        conversation_memory: str = "",
    ) -> TraceResponse:
        effective_question = augment_question_with_memory(
            question,
            conversation_memory,
        )
        results = self.retriever.retrieve(
            project_id,
            effective_question,
            limit=limit,
            max_depth=max_depth,
        )
        if not results:
            return TraceResponse(
                answer=NO_TRACE_EVIDENCE_ANSWER,
                references=[],
                graph_nodes=[],
                graph_edges=[],
                uncertainties=[NO_TRACE_EVIDENCE_ANSWER],
            )

        retrieval_uncertainties = self._retrieval_uncertainties(results)
        seed_ids = tuple(
            dict.fromkeys(result.seed_entity_id for result in results)
        )
        graph_available = True
        try:
            graph = self.graph.expand_entities(
                project_id,
                seed_ids,
                max_depth=max_depth,
            )
        except Exception:
            graph = GraphResult()
            graph_available = False
            retrieval_uncertainties = list(
                dict.fromkeys(
                    (
                        *retrieval_uncertainties,
                        GRAPH_EXPANSION_UNCERTAINTY,
                    )
                )
            )
        context = self.context_builder.build(results, graph)
        graph_response = GraphResponse.from_result(graph)
        uncertainties = [
            *retrieval_uncertainties,
            *(
                self._uncertainties(graph)
                if graph_available
                else []
            ),
        ]
        if not context.references:
            return TraceResponse(
                answer=NO_TRACE_EVIDENCE_ANSWER,
                references=[],
                graph_nodes=graph_response.nodes,
                graph_edges=graph_response.edges,
                uncertainties=[
                    *uncertainties,
                    "Retrieved evidence exceeded the context budget.",
                ],
            )

        user_prompt = (
            f"Question:\n{effective_question}\n\n"
            f"Known uncertainties:\n"
            f"{self._uncertainty_text(uncertainties)}\n\n"
            f"Indexed-code evidence:\n{context.text}"
        )
        try:
            answer = self.llm.complete(
                TRACE_SYSTEM_PROMPT,
                user_prompt,
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="LLM_REQUEST_FAILED",
                message="The trace language-model request failed.",
                status_code=502,
            ) from error

        references = [
            ContextReferenceRead.model_validate(reference)
            for reference in context.references
        ]
        answer = append_relationship_limits(answer, uncertainties)
        validation = self.evidence_validator.validate(answer, references)
        if validation.is_valid:
            return TraceResponse(
                answer=answer,
                references=references,
                graph_nodes=graph_response.nodes,
                graph_edges=graph_response.edges,
                uncertainties=uncertainties,
            )

        repaired_answer = self.llm.complete(
            TRACE_SYSTEM_PROMPT,
            self._repair_prompt(
                question=effective_question,
                context_text=context.text,
                previous_answer=answer,
                validation_messages=validation.uncertainties,
                uncertainties=uncertainties,
            ),
        )
        repaired_answer = append_relationship_limits(
            repaired_answer,
            uncertainties,
        )
        repaired_validation = self.evidence_validator.validate(
            repaired_answer,
            references,
        )
        if repaired_validation.is_valid:
            return TraceResponse(
                answer=repaired_answer,
                references=references,
                graph_nodes=graph_response.nodes,
                graph_edges=graph_response.edges,
                uncertainties=uncertainties,
            )

        return TraceResponse(
            answer=EVIDENCE_VALIDATION_FAILED_ANSWER,
            references=references,
            graph_nodes=graph_response.nodes,
            graph_edges=graph_response.edges,
            uncertainties=[
                *uncertainties,
                *validation.uncertainties,
                *repaired_validation.uncertainties,
                "Evidence validation repair limit reached.",
            ],
        )

    @staticmethod
    def _uncertainties(graph: GraphResult) -> list[str]:
        present = {edge.relation_type for edge in graph.edges}
        return [
            (
                f"No stored {relation_type} edge was found; that "
                "chain segment cannot be determined from indexed code."
            )
            for relation_type in EXPECTED_CHAIN_RELATIONS
            if relation_type not in present
        ]

    @staticmethod
    def _retrieval_uncertainties(
        results: list[GraphRetrievalResult],
    ) -> list[str]:
        return list(
            dict.fromkeys(
                uncertainty
                for result in results
                for uncertainty in result.uncertainties
            )
        )

    @staticmethod
    def _uncertainty_text(uncertainties: list[str]) -> str:
        if not uncertainties:
            return "No missing chain relation types were detected."
        return "\n".join(f"- {item}" for item in uncertainties)

    @staticmethod
    def _repair_prompt(
        *,
        question: str,
        context_text: str,
        previous_answer: str,
        validation_messages: tuple[str, ...],
        uncertainties: list[str],
    ) -> str:
        return (
            "Repair the previous answer so it uses only the supplied "
            "indexed-code evidence and only the listed citation IDs and "
            "file paths. Do not add any file path, line range, citation, "
            "edge, or runtime relationship that is absent from the "
            "evidence.\n\n"
            f"Question:\n{question}\n\n"
            f"Known uncertainties:\n"
            f"{TraceService._uncertainty_text(uncertainties)}\n\n"
            f"Validation failures:\n"
            f"{TraceService._bullet_list(validation_messages)}\n\n"
            f"Previous answer:\n{previous_answer}\n\n"
            f"Indexed-code evidence:\n{context_text}"
        )

    @staticmethod
    def _bullet_list(items: tuple[str, ...]) -> str:
        if not items:
            return "- The answer did not pass evidence validation."
        return "\n".join(f"- {item}" for item in items)
