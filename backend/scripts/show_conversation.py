import argparse
import json

from app.core.database import SessionLocal
from app.models import Conversation


def format_conversation(conversation) -> str:
    lines = [
        f"Conversation {conversation.id} - Project {conversation.project_id}",
        "",
    ]
    for message in conversation.messages:
        heading = message.role
        if message.task_type:
            heading += f" - {message.task_type}"
        lines.extend([f"[{heading}]", message.content])
        if message.role == "assistant":
            metadata = json.loads(message.metadata_json)
            references = metadata.get("references", [])
            nodes = metadata.get("graph_nodes", [])
            edges = metadata.get("graph_edges", [])
            uncertainties = metadata.get("uncertainties", [])
            lines.append(f"References: {len(references)}")
            lines.append(
                f"Graph: {len(nodes)} nodes, {len(edges)} edges"
            )
            lines.append(
                "Uncertainties: "
                + (", ".join(uncertainties) if uncertainties else "none")
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show a saved Agent conversation without calling an LLM."
    )
    parser.add_argument("conversation_id", type=int)
    args = parser.parse_args()
    with SessionLocal() as session:
        conversation = session.get(Conversation, args.conversation_id)
        if conversation is None:
            parser.error(
                f"conversation {args.conversation_id} does not exist"
            )
        print(format_conversation(conversation))


if __name__ == "__main__":
    main()
