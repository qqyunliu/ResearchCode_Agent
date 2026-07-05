from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.errors import DomainError
from app.graph.types import GraphResult
from app.llm.client import LlmClient
from app.rag.context_builder import RagContext
from app.rag.graph_context_builder import GraphContextBuilder
from app.rag.graph_retriever import GraphRagRetriever
from app.retrieval.types import SearchHit
from app.schemas.agent import (
    AffectedFileRead,
    ChangePlanResponse,
    ContextReferenceRead,
)
from app.schemas.graph import GraphResponse

CHANGE_PLAN_SYSTEM_PROMPT = """Use only supplied indexed-code evidence.
Return one JSON object with summary, affected_files, risks, and uncertainties.
Each affected_files item must contain entity_id, file_path, reason, and suggested_changes.
Never name a file or entity absent from the evidence.
Describe a modification plan; do not generate code or a patch.
Put unsupported assumptions in uncertainties."""

NO_CHANGE_PLAN_EVIDENCE_ANSWER = (
    "No supporting code evidence was found for this change plan."
)


class ChangePlanSearch(Protocol):
    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]: ...


class ChangePlanGraph(Protocol):
    def traverse(
        self,
        project_id: int,
        entity_id: int,
        *,
        max_depth: int,
        relation_types: tuple[str, ...] | None,
    ) -> GraphResult: ...

    def expand_entities(
        self,
        project_id: int,
        entity_ids,
        *,
        max_depth: int,
    ) -> GraphResult: ...


class _LlmAffectedFile(BaseModel):
    entity_id: int
    file_path: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    suggested_changes: list[str]

    model_config = ConfigDict(str_strip_whitespace=True)


class _LlmChangePlan(BaseModel):
    summary: str = Field(min_length=1)
    affected_files: list[_LlmAffectedFile]
    risks: list[str]
    uncertainties: list[str]

    model_config = ConfigDict(str_strip_whitespace=True)


class ChangePlanService:
    def __init__(
        self,
        *,
        search: ChangePlanSearch,
        graph: ChangePlanGraph,
        context_builder: GraphContextBuilder,
        llm: LlmClient,
    ) -> None:
        self.search = search
        self.graph = graph
        self.context_builder = context_builder
        self.llm = llm

    def answer(
        self,
        project_id: int,
        question: str,
        limit: int,
    ) -> ChangePlanResponse:
        results = GraphRagRetriever(
            search=self.search,
            graph=self.graph,
        ).retrieve(
            project_id,
            question,
            limit=limit,
            max_depth=2,
        )
        if not results:
            return self._no_evidence_response()

        seed_ids = tuple(
            dict.fromkeys(result.seed_entity_id for result in results)
        )
        graph = self.graph.expand_entities(
            project_id,
            seed_ids,
            max_depth=2,
        )
        context = self.context_builder.build(results, graph)
        graph_response = GraphResponse.from_result(graph)
        if not context.references:
            return self._no_evidence_response(
                graph_response=graph_response,
            )

        plan = self._generate(question, context)
        affected_files, grounding_uncertainties = self._ground_files(
            plan,
            context,
        )
        return ChangePlanResponse(
            answer=self._answer_text(plan, affected_files),
            affected_files=affected_files,
            references=[
                ContextReferenceRead.model_validate(reference)
                for reference in context.references
            ],
            graph_nodes=graph_response.nodes,
            graph_edges=graph_response.edges,
            uncertainties=[
                *plan.uncertainties,
                *grounding_uncertainties,
            ],
        )

    def _generate(
        self,
        question: str,
        context: RagContext,
    ) -> _LlmChangePlan:
        user_prompt = (
            f"Question:\n{question}\n\n"
            f"Indexed-code evidence:\n{context.text}\n\n"
            "Return JSON only."
        )
        try:
            raw_response = self.llm.complete(
                CHANGE_PLAN_SYSTEM_PROMPT,
                user_prompt,
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="LLM_REQUEST_FAILED",
                message=(
                    "The change-plan language-model request failed."
                ),
                status_code=502,
            ) from error

        try:
            return _LlmChangePlan.model_validate_json(raw_response)
        except ValidationError as error:
            raise DomainError(
                code="CHANGE_PLAN_RESPONSE_INVALID",
                message=(
                    "The language model returned an invalid "
                    "change-plan response."
                ),
                status_code=502,
            ) from error

    @staticmethod
    def _ground_files(
        plan: _LlmChangePlan,
        context: RagContext,
    ) -> tuple[list[AffectedFileRead], list[str]]:
        evidence = {
            (reference.entity_id, reference.file_path)
            for reference in context.references
        }
        grounded: list[AffectedFileRead] = []
        uncertainties: list[str] = []
        seen: set[tuple[int, str]] = set()
        for item in plan.affected_files:
            key = (item.entity_id, item.file_path)
            if key not in evidence:
                uncertainties.append(
                    (
                        f"Ungrounded file {item.file_path} "
                        f"(entity {item.entity_id}) was removed "
                        "from the change plan."
                    )
                )
                continue
            if key in seen:
                continue
            seen.add(key)
            grounded.append(
                AffectedFileRead(
                    entity_id=item.entity_id,
                    file_path=item.file_path,
                    reason=item.reason,
                    suggested_changes=item.suggested_changes,
                )
            )
        return grounded, uncertainties

    @staticmethod
    def _answer_text(
        plan: _LlmChangePlan,
        affected_files: list[AffectedFileRead],
    ) -> str:
        sections = [plan.summary]
        if affected_files:
            sections.append(
                "Affected files:\n"
                + "\n".join(
                    f"- {item.file_path}: {item.reason}"
                    for item in affected_files
                )
            )
        if plan.risks:
            sections.append(
                "Risks:\n"
                + "\n".join(f"- {risk}" for risk in plan.risks)
            )
        return "\n\n".join(sections)

    @staticmethod
    def _no_evidence_response(
        *,
        graph_response: GraphResponse | None = None,
    ) -> ChangePlanResponse:
        return ChangePlanResponse(
            answer=NO_CHANGE_PLAN_EVIDENCE_ANSWER,
            affected_files=[],
            references=[],
            graph_nodes=graph_response.nodes if graph_response else [],
            graph_edges=graph_response.edges if graph_response else [],
            uncertainties=[NO_CHANGE_PLAN_EVIDENCE_ANSWER],
        )
