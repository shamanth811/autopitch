"""Load SEC Form D private-placement data into the local benchmark database.

    python scripts/ingest_formd.py --quarters 8

Downloads the most recent quarterly data sets from sec.gov (about 3 MB each), keeps rounds that
could be a startup raise, and writes them to AUTOPITCH_FORMD_DB_PATH. Re-running is safe: rows
are keyed by filing, so they are replaced, not duplicated. Needs only AUTOPITCH_SEC_USER_AGENT;
there is no API key and no model call.
"""

from __future__ import annotations

import argparse
import logging

from autopitch.config import get_settings
from autopitch.retrieval.formd import (
    FormDStore,
    download_quarter,
    list_quarter_urls,
    make_client,
    parse_quarter,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quarters", type=int, default=8, help="How many recent quarters to load")
    parser.add_argument("--only", nargs="*", help="Specific quarters, e.g. 2025q3 2025q4")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    client = make_client(settings.sec_user_agent)
    available = list_quarter_urls(client)
    if not available:
        logging.error("no Form D data sets found on the SEC index page")
        return 1
    wanted = args.only or sorted(available, reverse=True)[: args.quarters]

    store = FormDStore(settings.formd_db_path)
    for quarter in sorted(wanted):
        if quarter not in available:
            logging.warning("%s is not published; skipping", quarter)
            continue
        rounds = parse_quarter(download_quarter(client, available[quarter]))
        store.upsert(rounds)
        logging.info("%s: kept %d startup-like raises", quarter, len(rounds))

    total, first, last = store.coverage()
    logging.info(
        "done: %d raises in %s, filed %s to %s", total, settings.formd_db_path, first, last
    )
    for industry, n in store.industry_counts():
        logging.info("  %-40s %d", industry, n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
