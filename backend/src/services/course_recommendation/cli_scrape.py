from __future__ import annotations

import argparse
import warnings
from typing import Optional

from .tis_client import (
    TisClientError,
    fetch_all_term_schedules,
    fetch_course_offerings,
    fetch_term_list,
    fetch_term_schedule,
    infer_term_status,
)

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module="openpyxl"
)


def _pick_default_term(term_id: Optional[str]) -> Optional[str]:
    if term_id:
        return term_id

    terms = fetch_term_list()
    if not terms:
        return None

    enriched = []
    for term in terms:
        term.status = infer_term_status(term)
        enriched.append(term)

    # Prefer current term, fallback to latest
    current = [t for t in enriched if t.status == "current"]
    if current:
        return current[0].term_id

    return enriched[0].term_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape TIS data on-demand")
    parser.add_argument("--terms", action="store_true", help="fetch term list")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="fetch schedule for a term",
    )
    parser.add_argument(
        "--offerings",
        action="store_true",
        help="fetch course offerings for a term",
    )
    parser.add_argument(
        "--term-id",
        type=str,
        help="term id, e.g. 2025-2026-2",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="fetch terms and schedule",
    )

    args = parser.parse_args()

    try:
        if args.all or args.terms:
            terms = fetch_term_list()
            if not terms:
                print("[TIS] No term list. Set TIS_TERM_LIST_URL.")
            else:
                for term in terms:
                    term.status = infer_term_status(term)
                print(f"[TIS] Terms fetched: {len(terms)}")

        if args.schedule:
            term_id = _pick_default_term(args.term_id)
            if not term_id:
                print(
                    "[TIS] No term id available. Provide --term-id or set "
                    "TIS_TERM_LIST_URL."
                )
            else:
                schedule = fetch_term_schedule(term_id, download_excel=True)
                print(
                    f"[TIS] Schedule fetched for {term_id}: "
                    f"{len(schedule.meetings)} meetings"
                )
        elif args.all or not (args.offerings or args.terms):
            schedules = fetch_all_term_schedules()
            print(
                f"[TIS] Interactive scrape finished: "
                f"{len(schedules)} term schedule exports"
            )

        if args.offerings:
            term_id = _pick_default_term(args.term_id)
            if not term_id:
                print(
                    "[TIS] No term id available. Provide --term-id or set "
                    "TIS_TERM_LIST_URL."
                )
            else:
                offerings = fetch_course_offerings(term_id)
                print(
                    f"[TIS] Course offerings fetched for {term_id}: "
                    f"{len(offerings)} items"
                )

    except TisClientError as exc:
        print(f"[TIS] Error: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
