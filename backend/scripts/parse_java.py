import argparse
import json
from pathlib import Path

from app.parsers.java_parser import JavaParser


def main() -> None:
    argument_parser = argparse.ArgumentParser(
        description="Parse one Java file and print extracted entities."
    )
    argument_parser.add_argument("file_path", type=Path)
    args = argument_parser.parse_args()

    file_path = args.file_path.expanduser().resolve()
    source = file_path.read_text(encoding="utf-8-sig")
    result = JavaParser().parse(file_path.as_posix(), source)

    print(f"Entities: {len(result.entities)}")
    for entity in result.entities:
        metadata = json.dumps(
            entity.metadata,
            ensure_ascii=False,
            sort_keys=True,
        )
        print(
            f"  {entity.entity_type} "
            f"{entity.qualified_name} "
            f"lines={entity.start_line}-{entity.end_line}"
        )
        print(f"    metadata={metadata}")

    print(f"Relations: {len(result.relations)}")
    for relation in result.relations:
        print(
            f"  {relation.source_key} "
            f"-[{relation.relation_type}]-> "
            f"{relation.target_key}"
        )


if __name__ == "__main__":
    main()
