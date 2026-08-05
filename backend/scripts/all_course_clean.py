from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_JSON_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "tis_download"
    / "full_course_table"
    / "all_courses_merged.json"
)


def classify_course(course: dict[str, Any]) -> str:
    schedule_text = str(course.get("上课信息") or "")
    return "lab" if "机房" in schedule_text else "theory"


def clean_courses(json_path: Path) -> tuple[int, int]:
    with json_path.open("r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)

    if not isinstance(data, list):
        raise ValueError("Expected the JSON file to contain a list of course records.")

    updated_count = 0
    total_count = 0

    for item in data:
        if not isinstance(item, dict):
            continue

        total_count += 1
        new_type = classify_course(item)
        if item.get("课程种类") != new_type:
            item["课程种类"] = new_type
            updated_count += 1

    with json_path.open("w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, ensure_ascii=False, indent=2)
        file_handle.write("\n")

    return total_count, updated_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add the 课程种类 field to all courses in all_courses_merged.json."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help="Path to all_courses_merged.json (defaults to the repository data file).",
    )
    args = parser.parse_args()

    total_count, updated_count = clean_courses(args.input)
    print(f"Processed {total_count} course records; updated {updated_count} entries in {args.input}.")


if __name__ == "__main__":
    main()