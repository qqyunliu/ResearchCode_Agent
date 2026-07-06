import subprocess
import sys
from types import SimpleNamespace

from scripts.show_conversation import format_conversation


def test_script_imports_in_a_fresh_python_process() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import scripts.show_conversation"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_format_conversation_prints_chronological_summary() -> None:
    conversation = SimpleNamespace(
        id=4,
        project_id=2,
        messages=[
            SimpleNamespace(
                role="user",
                task_type=None,
                content="Where is the API?",
                metadata_json="{}",
            ),
            SimpleNamespace(
                role="assistant",
                task_type="CODE_QA",
                content="In AlertController [1].",
                metadata_json=(
                    '{"references":[{"entity_id":5}],'
                    '"graph_nodes":[],"graph_edges":[],'
                    '"uncertainties":["Confirm service."]}'
                ),
            ),
        ],
    )

    output = format_conversation(conversation)

    assert "Conversation 4 - Project 2" in output
    assert "[user]" in output
    assert "[assistant - CODE_QA]" in output
    assert "References: 1" in output
    assert "Graph: 0 nodes, 0 edges" in output
    assert "Uncertainties: Confirm service." in output
