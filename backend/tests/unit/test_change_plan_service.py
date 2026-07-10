import json

import pytest

from app.errors import DomainError
from app.graph.types import GraphEdge, GraphNode, GraphResult
from app.rag.graph_context_builder import GraphContextBuilder
from app.retrieval.types import SearchHit
from app.services.change_plan_service import (
    CHANGE_PLAN_SYSTEM_PROMPT,
    NO_CHANGE_PLAN_EVIDENCE_ANSWER,
    ChangePlanService,
)


def controller_hit() -> SearchHit:
    return SearchHit(
        entity_id=5,
        entity_type="java_method",
        name="getAlert",
        qualified_name="AlertController.getAlert",
        file_path="backend/src/AlertController.java",
        start_line=4,
        end_line=7,
        content="return alertService.findById(id);",
        metadata={},
        score=0.9,
        source="hybrid",
    )


def related_graph() -> GraphResult:
    return GraphResult(
        nodes=(
            GraphNode(
                entity_id=5,
                label="AlertController.getAlert",
                entity_type="java_method",
                qualified_name="AlertController.getAlert",
                file_path="backend/src/AlertController.java",
                start_line=4,
                end_line=7,
                content="return alertService.findById(id);",
                metadata={},
            ),
            GraphNode(
                entity_id=10,
                label="AlertService.findById",
                entity_type="java_method",
                qualified_name="AlertService.findById",
                file_path="backend/src/AlertService.java",
                start_line=3,
                end_line=5,
                content="return null;",
                metadata={},
            ),
        ),
        edges=(
            GraphEdge(
                relation_id=9,
                source_id=5,
                target_id=10,
                relation_type="CALLS_METHOD",
                confidence=0.8,
                metadata={},
            ),
        ),
    )


class FakeSearch:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.calls: list[tuple[int, str, int]] = []

    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        self.calls.append((project_id, query, limit))
        return self.hits


class FakeGraph:
    def __init__(self, result: GraphResult) -> None:
        self.result = result
        self.traverse_calls: list[
            tuple[int, int, int, tuple[str, ...] | None]
        ] = []
        self.expand_calls: list[tuple[int, tuple[int, ...], int]] = []

    def traverse(
        self,
        project_id: int,
        entity_id: int,
        *,
        max_depth: int,
        relation_types: tuple[str, ...] | None,
    ) -> GraphResult:
        self.traverse_calls.append(
            (project_id, entity_id, max_depth, relation_types)
        )
        return self.result

    def expand_entities(
        self,
        project_id: int,
        entity_ids,
        *,
        max_depth: int,
    ) -> GraphResult:
        self.expand_calls.append(
            (project_id, tuple(entity_ids), max_depth)
        )
        return self.result


class FakeLlm:
    def __init__(self, response: str | list[str]) -> None:
        self.responses = (
            [response] if isinstance(response, str) else list(response)
        )
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.responses[
            min(len(self.calls) - 1, len(self.responses) - 1)
        ]


def llm_json(
    *,
    affected_files: list[dict] | None = None,
    summary: str = "Add risk_score to the alert flow.",
) -> str:
    return json.dumps(
        {
            "summary": summary,
            "affected_files": affected_files
            if affected_files is not None
            else [
                {
                    "entity_id": 5,
                    "file_path": "backend/src/AlertController.java",
                    "reason": "The controller exposes the alert API.",
                    "suggested_changes": [
                        "Return the new risk_score field."
                    ],
                },
                {
                    "entity_id": 10,
                    "file_path": "backend/src/AlertService.java",
                    "reason": "The service supplies alert data.",
                    "suggested_changes": [
                        "Populate risk_score from available data."
                    ],
                },
            ],
            "risks": ["Clients may require compatibility handling."],
            "uncertainties": ["The persistence model was not retrieved."],
        }
    )


def make_service(
    llm_response: str | list[str],
) -> tuple[ChangePlanService, FakeSearch, FakeGraph, FakeLlm]:
    search = FakeSearch([controller_hit()])
    graph = FakeGraph(related_graph())
    llm = FakeLlm(llm_response)
    return (
        ChangePlanService(
            search=search,
            graph=graph,
            context_builder=GraphContextBuilder(),
            llm=llm,
        ),
        search,
        graph,
        llm,
    )


def test_change_plan_uses_search_graph_and_one_llm_call() -> None:
    service, search, graph, llm = make_service(llm_json())

    response = service.answer(
        project_id=1,
        question="Add risk_score",
        limit=5,
    )

    assert search.calls == [(1, "Add risk_score", 5)]
    assert len(graph.traverse_calls) == 1
    assert graph.expand_calls == [(1, (5,), 2)]
    assert len(llm.calls) == 1
    system_prompt, user_prompt = llm.calls[0]
    assert "same language as the user's original question" in system_prompt
    assert system_prompt == CHANGE_PLAN_SYSTEM_PROMPT
    assert "Question:\nAdd risk_score" in user_prompt
    assert "AlertController.java" in user_prompt
    assert "AlertService.java" in user_prompt
    assert "Stored graph edges (authoritative):" in user_prompt
    assert "CALLS_METHOD" in user_prompt
    assert [item.entity_id for item in response.affected_files] == [5, 10]
    assert "Clients may require compatibility handling." in response.answer
    assert len(response.references) == 2
    assert len(response.graph_nodes) == 2
    assert len(response.graph_edges) == 1
    assert "The persistence model was not retrieved." in (
        response.uncertainties
    )
    assert any(
        "No stored REQUESTS_API edge was found" in item
        for item in response.uncertainties
    )


def test_change_plan_normalizes_common_mimo_field_shapes() -> None:
    payload = json.loads(llm_json(affected_files=[{
        "entity_id": "Entity 5",
        "file_path": "backend/src/AlertController.java",
        "reason": "The controller exposes the alert API.",
        "suggested_changes": "Return the risk_score field.",
    }]))
    payload["risks"] = "Clients may require compatibility handling."
    payload["uncertainties"] = "The persistence model was not retrieved."
    service, _, _, _ = make_service(
        "```json\n" + json.dumps(payload) + "\n```"
    )

    response = service.answer(1, "Add risk_score", 5)

    assert response.affected_files[0].entity_id == 5
    assert response.affected_files[0].suggested_changes == [
        "Return the risk_score field."
    ]


def test_change_plan_resolves_named_entity_ids_from_evidence() -> None:
    payload = json.loads(llm_json(affected_files=[{
        "entity_id": "AlertController.getAlert",
        "file_path": "backend/src/AlertController.java",
        "reason": "The controller exposes the alert API.",
        "suggested_changes": ["Return the risk_score field."],
    }]))
    service, _, _, _ = make_service(json.dumps(payload))

    response = service.answer(1, "Add risk_score", 5)

    assert [item.entity_id for item in response.affected_files] == [5]


def test_ungrounded_affected_file_is_removed_and_reported() -> None:
    service, _, _, _ = make_service(
        llm_json(
            affected_files=[
                {
                    "entity_id": 5,
                    "file_path": "backend/src/AlertController.java",
                    "reason": "Retrieved controller.",
                    "suggested_changes": ["Expose risk_score."],
                },
                {
                    "entity_id": 999,
                    "file_path": "backend/src/InventedDto.java",
                    "reason": "Assumed DTO.",
                    "suggested_changes": ["Add a field."],
                },
            ]
        )
    )

    response = service.answer(1, "Add risk_score", 5)

    assert [item.entity_id for item in response.affected_files] == [5]
    assert all(
        item.file_path != "backend/src/InventedDto.java"
        for item in response.affected_files
    )
    assert any(
        "InventedDto.java" in uncertainty
        and "removed" in uncertainty
        for uncertainty in response.uncertainties
    )


def test_path_must_match_the_retrieved_entity() -> None:
    service, _, _, _ = make_service(
        llm_json(
            affected_files=[
                {
                    "entity_id": 5,
                    "file_path": "backend/src/Wrong.java",
                    "reason": "Mismatched path.",
                    "suggested_changes": ["Change it."],
                }
            ]
        )
    )

    response = service.answer(1, "Add risk_score", 5)

    assert response.affected_files == []
    assert any("Wrong.java" in item for item in response.uncertainties)


def test_no_evidence_skips_graph_context_and_llm() -> None:
    search = FakeSearch([])
    graph = FakeGraph(GraphResult())
    llm = FakeLlm(llm_json())
    service = ChangePlanService(
        search=search,
        graph=graph,
        context_builder=GraphContextBuilder(),
        llm=llm,
    )

    response = service.answer(1, "unknown change", 5)

    assert response.answer == NO_CHANGE_PLAN_EVIDENCE_ANSWER
    assert response.affected_files == []
    assert response.references == []
    assert response.graph_nodes == []
    assert response.graph_edges == []
    assert response.uncertainties == [NO_CHANGE_PLAN_EVIDENCE_ANSWER]
    assert graph.traverse_calls == []
    assert graph.expand_calls == []
    assert llm.calls == []


def test_conversation_memory_augments_change_plan_retrieval_and_prompt() -> None:
    service, search, _, llm = make_service(llm_json())
    memory = "Conversation context (not code evidence):\nUser: Change the alert response"

    service.answer(
        project_id=1,
        question="Apply the same idea here",
        limit=5,
        conversation_memory=memory,
    )

    assert memory in search.calls[0][1]
    assert "Current question:\nApply the same idea here" in llm.calls[0][1]


def test_graph_expansion_failure_uses_direct_evidence() -> None:
    class ExpansionFailingGraph(FakeGraph):
        def expand_entities(
            self,
            project_id,
            entity_ids,
            *,
            max_depth,
        ):
            raise TimeoutError("sqlite graph query timed out")

    graph = ExpansionFailingGraph(related_graph())
    llm = FakeLlm(
        llm_json(
            affected_files=[
                {
                    "entity_id": 5,
                    "file_path": "backend/src/AlertController.java",
                    "reason": "The controller is direct evidence.",
                    "suggested_changes": ["Update the response."],
                }
            ]
        )
    )
    service = ChangePlanService(
        search=FakeSearch([controller_hit()]),
        graph=graph,
        context_builder=GraphContextBuilder(),
        llm=llm,
    )

    response = service.answer(1, "Add risk_score", 5)

    assert len(llm.calls) == 1
    assert [item.entity_id for item in response.affected_files] == [5]
    assert response.references[0].entity_id == 5
    assert response.graph_nodes == []
    assert response.graph_edges == []
    assert (
        "Graph expansion was unavailable; "
        "the answer uses direct search evidence only."
    ) in response.uncertainties
    assert all(
        "No stored " not in uncertainty
        for uncertainty in response.uncertainties
    )


def test_malformed_json_becomes_domain_error() -> None:
    service, _, _, _ = make_service("not-json")

    with pytest.raises(DomainError) as raised:
        service.answer(1, "Add risk_score", 5)

    assert raised.value.code == "CHANGE_PLAN_RESPONSE_INVALID"
    assert raised.value.status_code == 502


def test_invalid_json_shape_becomes_domain_error() -> None:
    service, _, _, _ = make_service('{"summary": 3}')

    with pytest.raises(DomainError) as raised:
        service.answer(1, "Add risk_score", 5)

    assert raised.value.code == "CHANGE_PLAN_RESPONSE_INVALID"


def test_llm_failure_becomes_domain_error() -> None:
    class FailingLlm:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise RuntimeError("provider unavailable")

    service = ChangePlanService(
        search=FakeSearch([controller_hit()]),
        graph=FakeGraph(related_graph()),
        context_builder=GraphContextBuilder(),
        llm=FailingLlm(),
    )

    with pytest.raises(DomainError) as raised:
        service.answer(1, "Add risk_score", 5)

    assert raised.value.code == "LLM_REQUEST_FAILED"
    assert raised.value.status_code == 502


def test_references_are_retained_when_model_lists_no_files() -> None:
    service, _, _, _ = make_service(llm_json(affected_files=[]))

    response = service.answer(1, "Assess the change", 5)

    assert response.affected_files == []
    assert [reference.entity_id for reference in response.references] == [
        5,
        10,
    ]


def test_change_plan_blocks_answer_when_repair_still_fails_validation() -> None:
    service, _, _, llm = make_service(
        [
            llm_json(
                summary=(
                    "Add risk_score in "
                    "backend/src/AlertController.java/Ghost.java."
                )
            ),
            llm_json(
                summary=(
                    "Still change "
                    "backend/src/AlertController.java/Ghost.java."
                )
            ),
        ]
    )

    response = service.answer(1, "Add risk_score", 5)

    assert len(llm.calls) == 2
    assert response.answer == (
        "The model answer did not pass evidence validation, so it was "
        "not returned. Please ask a narrower question or rebuild the "
        "index if the evidence looks incomplete."
    )
    assert response.references
    assert response.affected_files
    assert any(
        "Evidence validation repair limit reached" in uncertainty
        for uncertainty in response.uncertainties
    )


def test_change_plan_answer_includes_deterministic_relationship_limits() -> None:
    service, _, _, _ = make_service(llm_json())

    response = service.answer(1, "Add risk_score", 5)

    assert "Indexed relationship limits:" in response.answer
    assert (
        "No stored REQUESTS_API edge was found" in response.answer
    )
    assert "No stored DEFINES_API edge was found" in response.answer
