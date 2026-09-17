"""
Seed script (Section 9.2, point 17) — "copies each vertical's
committed synthetic data into its staging folder and runs the shared
ingestion function once, populating the KB and relational tables for
local development."

Usage (from inside the backend container, or any environment with
DATABASE_URL and STAGING_ROOT correctly configured):

    python seed.py

Safe to re-run: ingest_staging_folder()'s hash-based change detection
(Section 6.3) means files already seeded and unchanged are skipped,
not re-embedded, on subsequent runs.
"""

import shutil
from pathlib import Path

from app.core.ingestion import ingest_staging_folder, STAGING_ROOT
from app.verticals.contract_tracking.seed_local import seed_contract_tracking
from app.verticals.internal_mobility.seed_local import seed_internal_mobility
from app.verticals.meeting_action_items.seed_local import seed_meeting_action_items

# Synthetic data committed to the repo under backend/seed_data/,
# copied into each vertical's staging folder before ingestion. Only
# "dummy" has real seed data right now (Section 6.1's synthetic
# corpora for the four real verticals get added by each vertical
# owner once their own vertical is built).
SEED_DATA_ROOT = Path(__file__).parent / "seed_data"

# internal_mobility is handled by seed_internal_mobility() (dedicated
# structured seeding — it must NOT go through the generic copy-to-
# staging path, see that function's docstring), so it is intentionally
# absent from VERTICALS_TO_SEED, which only drives the generic
# staging-folder path. contract_tracking is likewise handled by its
# own seed_contract_tracking() (Section 6.4: scheduled ingestion IS
# the analysis trigger, so seeding must run the real extraction
# pipeline, not generic chunk-and-embed) — see
# app.verticals.contract_tracking.seed_local.
VERTICALS_TO_SEED = [
    {"vertical": "dummy", "source_type": "postmortem"},
    {"vertical": "post_incident", "source_type": "postmortem"},
]


def seed_vertical(vertical: str, source_type: str) -> None:
    source_dir = SEED_DATA_ROOT / vertical
    target_dir = STAGING_ROOT / vertical

    if not source_dir.exists():
        print(f"  No seed data found for '{vertical}' at {source_dir}, skipping.")
        return

    target_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for file in sorted(source_dir.iterdir()):
        if file.is_file():
            shutil.copy(file, target_dir / file.name)
            copied += 1
    print(f"  Copied {copied} file(s) into {target_dir}")

    summary = ingest_staging_folder(vertical=vertical, source_type=source_type)
    print(f"  Ingested: processed={len(summary['processed'])}, "
          f"skipped={len(summary['skipped'])}, errors={summary['errors']}")

    if vertical == "post_incident":
        from app.verticals.post_incident.graph import _parse_header_metadata, _content_hash
        from app.core.ingestion import extract_text
        conn = get_connection()
        synced_incidents = 0
        try:
            with conn.cursor() as cur:
                for file in sorted(source_dir.iterdir()):
                    if not file.is_file() or file.name.startswith("."):
                        continue
                    text = extract_text(file)
                    meta = _parse_header_metadata(text)
                    c_hash = _content_hash(text)
                    cur.execute("SELECT id FROM incidents WHERE content_hash = %s LIMIT 1;", (c_hash,))
                    if cur.fetchone() is None:
                        cur.execute(
                            """
                            INSERT INTO incidents (title, root_cause_tag, service, date, doc_id, content_hash)
                            VALUES (%s, %s, %s, %s, %s, %s);
                            """,
                            (meta["title"] or file.stem, meta["root_cause_tag"], meta["service"], meta["date"] or None, None, c_hash),
                        )
                        synced_incidents += 1
            conn.commit()
        finally:
            conn.close()
        print(f"  Synced {synced_incidents} relational incident row(s).")


def main():
    print("Seeding knowledge base from committed synthetic data...")
    for entry in VERTICALS_TO_SEED:
        print(f"\n{entry['vertical']}:")
        seed_vertical(entry["vertical"], entry["source_type"])


    # meeting_action_items doesn't fit the generic staging-folder
    # pattern above (its KB content is a byproduct of real LLM
    # extraction, not raw chunked text) — seeded separately.
    print("\nmeeting_action_items:")
    seed_meeting_action_items()

    print("\ninternal_mobility:")
    seed_internal_mobility()

    # contract_tracking is likewise a byproduct of real extraction
    # (Section 6.4) — seeded by running that same pipeline.
    print("\ncontract_tracking:")
    seed_contract_tracking()

    print("\nSeeding complete.")


if __name__ == "__main__":
    main()