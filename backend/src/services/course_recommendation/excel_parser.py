import pandas as pd
import re

def parse_schedule_excel(path: str):
    df = pd.read_excel(path, header=None)

    meetings = []

    for row_idx in range(len(df)):
        for col_idx in range(len(df.columns)):
            if col_idx == 0:
                # The first column is the time/period label.
                continue

            cell = df.iloc[row_idx, col_idx]
            if pd.isna(cell):
                continue

            text = str(cell)

            if "\n" not in text:
                continue

            lines = [x.strip() for x in text.split("\n") if x.strip()]
            if len(lines) < 2:
                continue

            course_name = lines[0]
            instructor = lines[1].replace("[", "").replace("]", "") if len(lines) > 1 else None

            class_info = None
            if len(lines) > 2 and ("周" not in lines[2] and "节" not in lines[2]):
                class_info = lines[2].replace("[", "").replace("]", "")

            schedule_line = next((line for line in lines if "周" in line or "节" in line), "")
            brackets = re.findall(r"\[(.*?)\]", schedule_line)
            weeks = brackets[0] if len(brackets) > 0 else None
            location = brackets[1] if len(brackets) > 1 else None

            period_match = re.search(r"(\d+)-(\d+)节", schedule_line or text)
            if period_match:
                start_slot = int(period_match.group(1))
                end_slot = int(period_match.group(2))
            else:
                start_slot = 1
                end_slot = 1

            day_of_week = col_idx
            if day_of_week < 1 or day_of_week > 7:
                continue

            display_name = course_name
            if class_info:
                display_name = f"{course_name}（{class_info}）"

            meetings.append({
                "course_name": display_name,
                "instructor": instructor,
                "day_of_week": day_of_week,
                "start_slot": start_slot,
                "end_slot": end_slot,
                "weeks": weeks,
                "location": location,
                "course_id": None,
                "credits": None,
                "metadata": {
                    "raw": text
                }
            })

    return meetings