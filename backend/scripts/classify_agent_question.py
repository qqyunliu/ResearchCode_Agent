import argparse

from app.agent.planner import SimpleAgentPlanner


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Classify a question without embeddings or an LLM."
        )
    )
    parser.add_argument("question")
    args = parser.parse_args()

    try:
        task_type = SimpleAgentPlanner().plan(args.question)
    except ValueError as error:
        parser.error(str(error))
    print(f"Task type: {task_type.value}")


if __name__ == "__main__":
    main()
