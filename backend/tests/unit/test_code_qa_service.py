from types import SimpleNamespace

import pytest

from app.llm.client import OpenAICompatibleLlmClient
from app.rag.context_builder import RagContextBuilder
from app.retrieval.types import SearchHit
from app.services.code_qa_service import CodeQaService


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


class FakeLlm:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.answer


def alert_hit() -> SearchHit:
    return SearchHit(
        entity_id=5,
        entity_type="java_method",
        name="getAlert",
        qualified_name="AlertController.getAlert",
        file_path="backend/src/AlertController.java",
        start_line=4,
        end_line=7,
        content="Alert getAlert(Long id) { return null; }",
        metadata={},
        score=1.0,
        source="hybrid",
    )


def test_answers_from_cited_retrieval_context() -> None:
    search = FakeSearch([alert_hit()])
    llm = FakeLlm("It is implemented in AlertController [1].")
    service = CodeQaService(
        search=search,
        context_builder=RagContextBuilder(),
        llm=llm,
    )
    question = "Where is the alert API implemented?"

    response = service.answer(
        project_id=1,
        question=question,
        limit=5,
    )

    assert search.calls == [(1, question, 5)]
    assert len(llm.calls) == 1
    system_prompt, user_prompt = llm.calls[0]
    assert "same language as the user's original question" in system_prompt
    assert "Answer only from the supplied code context." in system_prompt
    assert "Cite claims with [n]." in system_prompt
    assert "Do not invent files, symbols, APIs, or behavior." in system_prompt
    assert "If context is insufficient" in system_prompt
    assert (
        "Treat each context block as independent evidence."
        in system_prompt
    )
    assert (
        "Do not claim that one symbol calls, injects, delegates to, "
        "supports, or is connected to another unless a supplied code "
        "snippet explicitly shows that relationship."
        in system_prompt
    )
    assert (
        "Distinguish a declaration from an observed call relationship."
        in system_prompt
    )
    assert (
        "Ignore retrieved blocks that are not needed to answer the question."
        in system_prompt
    )
    assert (
        "Every citation must directly support the sentence that uses it."
        in system_prompt
    )
    assert question in user_prompt
    assert "[1] backend/src/AlertController.java:4-7" in user_prompt
    assert response.answer == (
        "It is implemented in AlertController [1]."
    )
    assert response.references[0].citation == 1
    assert response.references[0].file_path.endswith(
        "AlertController.java"
    )


def test_no_hits_returns_deterministic_answer_without_calling_llm() -> None:
    search = FakeSearch([])
    llm = FakeLlm("must not be used")
    service = CodeQaService(
        search=search,
        context_builder=RagContextBuilder(),
        llm=llm,
    )

    response = service.answer(
        project_id=1,
        question="Where is missing code?",
        limit=5,
    )

    assert response.answer == (
        "No supporting code was found for this question."
    )
    assert response.references == []
    assert llm.calls == []


def test_chinese_original_question_is_kept_in_final_prompt() -> None:
    search = FakeSearch([alert_hit()])
    llm = FakeLlm("告警接口位于 AlertController [1]。")
    service = CodeQaService(
        search=search,
        context_builder=RagContextBuilder(),
        llm=llm,
    )
    question = "告警列表 API 在哪里实现？"

    response = service.answer(1, question, 5)

    assert search.calls == [(1, question, 5)]
    assert f"Question:\n{question}" in llm.calls[0][1]
    assert response.answer.startswith("告警接口")


def test_openai_compatible_client_sends_deterministic_chat_request() -> None:
    create_calls: list[dict[str, object]] = []

    class Completions:
        def create(self, **kwargs):
            create_calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="answer [1]")
                    )
                ]
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions())
    )
    client = OpenAICompatibleLlmClient(
        model="mimo-v2.5",
        api_key="test-key",
        base_url="https://api.xiaomimimo.com/v1",
        client=fake_client,
    )

    answer = client.complete("system", "user")

    assert answer == "answer [1]"
    assert create_calls == [
        {
            "model": "mimo-v2.5",
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
        }
    ]


def test_openai_compatible_client_requires_api_key() -> None:
    with pytest.raises(
        ValueError,
        match="RCA_LLM_API_KEY is required",
    ):
        OpenAICompatibleLlmClient(
            model="mimo-v2.5",
            api_key=None,
            base_url="https://api.xiaomimimo.com/v1",
        )
