from collections.abc import Iterable
from typing import Protocol

from app.errors import DomainError
from app.graph.types import GraphResult
from app.llm.client import LlmClient
from app.rag.context_builder import RagContext
from app.rag.graph_retriever import GraphRetrievalResult
from app.schemas.agent import ContextReferenceRead, TraceResponse
from app.schemas.graph import GraphResponse

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
    ) -> None:
        self.retriever = retriever
        self.graph = graph
        self.context_builder = context_builder
        self.llm = llm

    def answer(
        self,
        project_id: int,
        question: str,
        *,
        limit: int,
        max_depth: int,
    ) -> TraceResponse:
        results = self.retriever.retrieve(
            project_id,
            question,
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

        seed_ids = tuple(
            dict.fromkeys(result.seed_entity_id for result in results)
        )
        graph = self.graph.expand_entities(
            project_id,
            seed_ids,
            max_depth=max_depth,
        )
        context = self.context_builder.build(results, graph)
        graph_response = GraphResponse.from_result(graph)
        uncertainties = self._uncertainties(graph)
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
            f"Question:\n{question}\n\n"
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

        return TraceResponse(
            answer=answer,
            references=[
                ContextReferenceRead.model_validate(reference)
                for reference in context.references
            ],
            graph_nodes=graph_response.nodes,
            graph_edges=graph_response.edges,
            uncertainties=uncertainties,
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
    def _uncertainty_text(uncertainties: list[str]) -> str:
        if not uncertainties:
            return "No missing chain relation types were detected."
        return "\n".join(f"- {item}" for item in uncertainties)
