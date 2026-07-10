import logging
import re
from typing import Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from app.errors import DomainError
from app.graph.types import GraphResult
from app.llm.client import LlmClient
from app.rag.context_builder import RagContext
from app.rag.graph_context_builder import GraphContextBuilder
from app.rag.graph_retriever import GraphRagRetriever, GraphRetrievalResult
from app.retrieval.types import SearchHit
from app.schemas.agent import (
    AffectedFileRead,
    ChangePlanResponse,
    ContextReferenceRead,
)
from app.schemas.graph import GraphResponse
from app.services.evidence_validator import (
    EVIDENCE_VALIDATION_FAILED_ANSWER,
    AnswerEvidenceValidator,
)
from app.services.relationship_limits import append_relationship_limits
from app.services.conversation_memory import augment_question_with_memory

CHANGE_PLAN_SYSTEM_PROMPT = """Use only supplied indexed-code evidence.
Write all JSON text values in the same language as the user's original question.
Return one JSON object with summary, affected_files, risks, and uncertainties.
Each affected_files item must contain entity_id, file_path, reason, and suggested_changes.
Never name a file or entity absent from the evidence.
Describe a modification plan; do not generate code or a patch.
Put unsupported assumptions in uncertainties."""

NO_CHANGE_PLAN_EVIDENCE_ANSWER = (
    "No supporting code evidence was found for this change plan."
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
logger = logging.getLogger(__name__)


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
    entity_id: int | str
    file_path: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    suggested_changes: list[str]

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("entity_id", mode="before")
    @classmethod
    def normalize_entity_id(cls, value):
        if isinstance(value, str):
            match = re.search(r"(\d+)\s*$", value)
            if match:
                return int(match.group(1))
        return value

    @field_validator("suggested_changes", mode="before")
    @classmethod
    def normalize_suggested_changes(cls, value):
        if isinstance(value, str):
            return [value]
        return value


class _LlmChangePlan(BaseModel):
    summary: str = Field(min_length=1)
    affected_files: list[_LlmAffectedFile]
    risks: list[str]
    uncertainties: list[str]

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("risks", "uncertainties", mode="before")
    @classmethod
    def normalize_text_lists(cls, value):
        if isinstance(value, str):
            return [value]
        return value


class ChangePlanService:
    def __init__(
        self,
        *,
        search: ChangePlanSearch,
        graph: ChangePlanGraph,
        context_builder: GraphContextBuilder,
        llm: LlmClient,
        evidence_validator: AnswerEvidenceValidator | None = None,
    ) -> None:
        self.search = search
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
        limit: int,
        conversation_memory: str = "",
    ) -> ChangePlanResponse:
        effective_question = augment_question_with_memory(
            question,
            conversation_memory,
        )
        results = GraphRagRetriever(
            search=self.search,
            graph=self.graph,
        ).retrieve(
            project_id,
            effective_question,
            limit=limit,
            max_depth=2,
        )
        if not results:
            return self._no_evidence_response()

        retrieval_uncertainties = self._retrieval_uncertainties(results)
        seed_ids = tuple(
            dict.fromkeys(result.seed_entity_id for result in results)
        )
        graph_available = True
        try:
            graph = self.graph.expand_entities(
                project_id,
                seed_ids,
                max_depth=2,
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
        if not context.references:
            return self._no_evidence_response(
                graph_response=graph_response,
            )

        plan = self._generate(effective_question, context)
        affected_files, grounding_uncertainties = self._ground_files(
            plan,
            context,
        )
        references = [
            ContextReferenceRead.model_validate(reference)
            for reference in context.references
        ]
        relationship_uncertainties = self._relationship_uncertainties(
            graph,
        ) if graph_available else []
        answer = append_relationship_limits(
            self._answer_text(plan, affected_files),
            relationship_uncertainties,
        )
        validation = self.evidence_validator.validate(answer, references)
        if not validation.is_valid:
            repaired_plan = self._generate(
                effective_question,
                context,
                previous_response=plan,
                validation_messages=validation.uncertainties,
            )
            affected_files, repair_grounding_uncertainties = (
                self._ground_files(repaired_plan, context)
            )
            repaired_answer = append_relationship_limits(
                self._answer_text(
                    repaired_plan,
                    affected_files,
                ),
                relationship_uncertainties,
            )
            repaired_validation = self.evidence_validator.validate(
                repaired_answer,
                references,
            )
            if repaired_validation.is_valid:
                return ChangePlanResponse(
                    answer=repaired_answer,
                    affected_files=affected_files,
                    references=references,
                    graph_nodes=graph_response.nodes,
                    graph_edges=graph_response.edges,
                    uncertainties=[
                        *retrieval_uncertainties,
                        *repaired_plan.uncertainties,
                        *repair_grounding_uncertainties,
                        *relationship_uncertainties,
                    ],
                )

            return ChangePlanResponse(
                answer=EVIDENCE_VALIDATION_FAILED_ANSWER,
                affected_files=affected_files,
                references=references,
                graph_nodes=graph_response.nodes,
                graph_edges=graph_response.edges,
                uncertainties=[
                    *retrieval_uncertainties,
                    *repaired_plan.uncertainties,
                    *repair_grounding_uncertainties,
                    *relationship_uncertainties,
                    *validation.uncertainties,
                    *repaired_validation.uncertainties,
                    "Evidence validation repair limit reached.",
                ],
            )

        return ChangePlanResponse(
            answer=answer,
            affected_files=affected_files,
            references=references,
            graph_nodes=graph_response.nodes,
            graph_edges=graph_response.edges,
            uncertainties=[
                *retrieval_uncertainties,
                *plan.uncertainties,
                *grounding_uncertainties,
                *relationship_uncertainties,
            ],
        )

    def _generate(
        self,
        question: str,
        context: RagContext,
        *,
        previous_response: _LlmChangePlan | None = None,
        validation_messages: tuple[str, ...] = (),
    ) -> _LlmChangePlan:
        repair_text = ""
        if previous_response is not None:
            repair_text = (
                "Repair the previous JSON response. Use only file paths, "
                "entity IDs, line ranges, and citation evidence present in "
                "the indexed-code evidence. Do not mention unsupported "
                "files in summary, risks, uncertainties, or affected_files."
                "\n\n"
                f"Validation failures:\n"
                f"{self._bullet_list(validation_messages)}\n\n"
                f"Previous JSON response:\n"
                f"{previous_response.model_dump_json()}\n\n"
            )
        user_prompt = (
            f"Question:\n{question}\n\n"
            f"{repair_text}"
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
            normalized_response = raw_response.strip()
            if normalized_response.startswith("```"):
                first_newline = normalized_response.find("\n")
                if first_newline != -1:
                    normalized_response = normalized_response[
                        first_newline + 1:
                    ]
                if normalized_response.endswith("```"):
                    normalized_response = normalized_response[:-3].rstrip()
            return _LlmChangePlan.model_validate_json(normalized_response)
        except ValidationError as error:
            logger.warning(
                "Invalid change-plan response schema: %s",
                error.errors(include_input=False),
            )
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
            entity_id = ChangePlanService._resolve_entity_id(
                item.entity_id,
                item.file_path,
                context,
            )
            key = (entity_id, item.file_path)
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
                    entity_id=entity_id,
                    file_path=item.file_path,
                    reason=item.reason,
                    suggested_changes=item.suggested_changes,
                )
            )
        return grounded, uncertainties

    @staticmethod
    def _resolve_entity_id(
        value: int | str,
        file_path: str,
        context: RagContext,
    ) -> int | None:
        if isinstance(value, int):
            return value

        identifier = value.casefold()
        candidates = {
            reference.entity_id
            for reference in context.references
            if reference.file_path == file_path
            and reference.qualified_name.casefold() in identifier
        }
        if len(candidates) == 1:
            return candidates.pop()
        return None

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
    def _bullet_list(items: tuple[str, ...]) -> str:
        if not items:
            return "- The answer did not pass evidence validation."
        return "\n".join(f"- {item}" for item in items)

    @staticmethod
    def _relationship_uncertainties(graph: GraphResult) -> list[str]:
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
