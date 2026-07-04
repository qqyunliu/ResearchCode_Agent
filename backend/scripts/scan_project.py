import argparse
from collections import Counter
from pathlib import Path

from app.services.scanner import ProjectScanner


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan a local project without writing to the database."
    )
    parser.add_argument("root_path", type=Path)
    args = parser.parse_args()

    result = ProjectScanner().scan(args.root_path)
    language_counts = Counter(item.language for item in result.files)
    total_lines = sum(item.line_count for item in result.files)

    print(f"Files: {len(result.files)}")
    print(f"Lines: {total_lines}")
    print("Languages:")
    for language, count in sorted(language_counts.items()):
        print(f"  {language}: {count}")

    print(f"Issues: {len(result.issues)}")
    for issue in result.issues:
        print(
            f"  {issue.file_path}: "
            f"{issue.reason_code} - {issue.message}"
        )


if __name__ == "__main__":
    main()
