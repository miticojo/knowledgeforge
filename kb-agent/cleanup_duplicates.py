"""Cleanup script: remove duplicate document ingestions from Spanner.

For each unique document title, keeps only the MOST RECENT doc_id
(by created_at timestamp) and deletes all older duplicates.

Usage:
  GOOGLE_CLOUD_PROJECT=<your-gcp-project> \
  SPANNER_INSTANCE=<your-spanner-instance> \
  SPANNER_DATABASE=<your-spanner-database> \
  python cleanup_duplicates.py [--dry-run]
"""
import sys
from services.spanner_client import get_database

DRY_RUN = "--dry-run" in sys.argv

db = get_database()

# 1. Find duplicate titles
print("=== Scanning for duplicate documents ===")
with db.snapshot() as snap:
    result = snap.execute_sql("""
        SELECT title, COUNT(*) AS cnt
        FROM Documents
        GROUP BY title
        HAVING COUNT(*) > 1
    """)
    duplicates = [(row[0], row[1]) for row in result]

if not duplicates:
    print("No duplicates found. Database is clean.")
    sys.exit(0)

for title, count in duplicates:
    print(f"  '{title}': {count} copies")

# 2. For each duplicate title, keep the newest, delete the rest
total_deleted = 0
for title, count in duplicates:
    with db.snapshot() as snap:
        result = snap.execute_sql(
            "SELECT doc_id, created_at FROM Documents WHERE title = @title ORDER BY created_at DESC",
            params={"title": title},
            param_types={"title": __import__("google.cloud.spanner_v1", fromlist=["param_types"]).param_types.STRING},
        )
        doc_ids = [(row[0], row[1]) for row in result]

    keep_id = doc_ids[0][0]
    delete_ids = [d[0] for d in doc_ids[1:]]
    print(f"\n  Keeping: {keep_id} (newest)")
    print(f"  Deleting: {len(delete_ids)} older copies")

    if DRY_RUN:
        print("  [DRY RUN] Skipping deletion")
        continue

    # Delete in batches (Spanner transaction limit)
    BATCH_SIZE = 50
    for i in range(0, len(delete_ids), BATCH_SIZE):
        batch = delete_ids[i:i + BATCH_SIZE]

        def _delete_batch(transaction, ids=batch):
            for old_id in ids:
                transaction.execute_update(f"DELETE FROM ChunkMentions WHERE doc_id = '{old_id}'")
                transaction.execute_update(f"DELETE FROM DocumentMentions WHERE doc_id = '{old_id}'")
                transaction.execute_update(f"DELETE FROM DocumentChunks WHERE doc_id = '{old_id}'")
                transaction.execute_update(f"DELETE FROM Documents WHERE doc_id = '{old_id}'")

        db.run_in_transaction(_delete_batch)
        total_deleted += len(batch)
        print(f"    Batch {i // BATCH_SIZE + 1}: deleted {len(batch)} docs ({total_deleted} total)")

print(f"\n=== Cleanup complete: {total_deleted} duplicate documents removed ===")
