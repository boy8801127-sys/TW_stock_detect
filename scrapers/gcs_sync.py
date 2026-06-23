# scrapers/gcs_sync.py
"""
Sync the local results/ directory with a GCS bucket so daily archive files
(e.g. 2026-06-23_taifex_vix.json) survive across Cloud Run Job executions,
which otherwise start from a fresh, empty filesystem every run.

No-op everywhere (including local dev) unless RESULTS_GCS_BUCKET is set.
Only dated archive files (YYYY-MM-DD_<prefix>.json) are synced; "latest_*"
files are per-run scratch state and don't need to round-trip.
"""
import os
import re
import glob

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
BUCKET_NAME = os.getenv("RESULTS_GCS_BUCKET", "").strip()
ARCHIVE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}_.+\.json$")


def _client():
    from google.cloud import storage
    return storage.Client()


def download_results():
    """Pull any archive files we don't already have locally, so today's run
    can compute day-over-day deltas against them."""
    if not BUCKET_NAME:
        return
    os.makedirs(RESULTS_DIR, exist_ok=True)
    try:
        bucket = _client().bucket(BUCKET_NAME)
        for blob in bucket.list_blobs(prefix="results/"):
            name = os.path.basename(blob.name)
            if not ARCHIVE_RX.match(name):
                continue
            dest = os.path.join(RESULTS_DIR, name)
            if os.path.exists(dest):
                continue
            blob.download_to_filename(dest)
    except Exception as e:
        print(f"[gcs_sync] download_results failed (continuing without history): {e}")


def upload_results():
    """Push today's freshly written archive files up so future runs can see them."""
    if not BUCKET_NAME:
        return
    try:
        bucket = _client().bucket(BUCKET_NAME)
        for fp in glob.glob(os.path.join(RESULTS_DIR, "*.json")):
            name = os.path.basename(fp)
            if not ARCHIVE_RX.match(name):
                continue
            blob = bucket.blob(f"results/{name}")
            if blob.exists():
                continue
            blob.upload_from_filename(fp)
    except Exception as e:
        print(f"[gcs_sync] upload_results failed: {e}")
