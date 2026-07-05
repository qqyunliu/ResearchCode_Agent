import pytest

from app.agent.planner import SimpleAgentPlanner
from app.agent.types import TaskType


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Where is getAlert implemented?", TaskType.CODE_QA),
        ("getAlert 在哪个文件里实现？", TaskType.CODE_QA),
        ("Explain AlertController", TaskType.CODE_QA),
        ("Where does the alert trend data come from?", TaskType.TRACE_CHAIN),
        ("告警趋势图的数据从哪里来？", TaskType.TRACE_CHAIN),
        ("Show the frontend backend call chain", TaskType.TRACE_CHAIN),
        (
            "Add risk_score; which files need changes?",
            TaskType.CHANGE_PLAN,
        ),
        ("新增 risk_score 需要改哪些文件？", TaskType.CHANGE_PLAN),
        ("What is the impact and risk of changing this API?", TaskType.CHANGE_PLAN),
    ],
)
def test_plan_classifies_question(
    question: str,
    expected: TaskType,
) -> None:
    assert SimpleAgentPlanner().plan(question) is expected


def test_change_plan_has_priority_over_trace_keywords() -> None:
    result = SimpleAgentPlanner().plan(
        "修改前后端调用链需要改哪些文件？"
    )

    assert result is TaskType.CHANGE_PLAN


def test_unknown_question_falls_back_to_code_qa() -> None:
    assert SimpleAgentPlanner().plan("Tell me about this symbol") is (
        TaskType.CODE_QA
    )


@pytest.mark.parametrize("question", ["", " ", "\r\n\t"])
def test_blank_question_is_rejected(question: str) -> None:
    with pytest.raises(
        ValueError,
        match="question must not be blank",
    ):
        SimpleAgentPlanner().plan(question)
