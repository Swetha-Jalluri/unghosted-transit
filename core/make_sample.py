#!/usr/bin/env python3
"""Create sample.db from raw.db for demo and replay modes.

Trims raw.db to the last 90 minutes of data, copies labels from labels.db,
VACUUMs, and ensures the result is < 25 MB for deployment.

Usage:
    uv run python core/make_sample.py
"""
import sqlite3
import time
from pathlib import Path

# Resolve paths relative to repo root
REPO_ROOT = Path(__file__).resolve().parent.parent

RAW_DB = REPO_ROOT / "data" / "raw.db"
LABELS_DB = REPO_ROOT / "data" / "labels.db"
SAMPLE_DB = REPO_ROOT / "data" / "sample.db"

# Retention window: keep last 90 minutes of snapshots
RETENTION_MINUTES = 90
RETENTION_SECONDS = RETENTION_MINUTES * 60


def backup_database(src: Path, dst: Path) -> None:
    """Use SQLite backup API to copy src to dst."""
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()


def trim_snapshots(db_path: Path) -> None:
    """Trim pred_snap, veh_snap, dock_snap to last 90 minutes.
    
    Keeps all rows in poll_log (for reference) but deletes old snapshots.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Find cutoff timestamp (90 minutes ago from newest snapshot)
    cursor.execute("SELECT MAX(ts) as max_ts FROM pred_snap")
    result = cursor.fetchone()
    max_ts = result["max_ts"] if result and result["max_ts"] else int(time.time())
    
    cutoff_ts = max_ts - RETENTION_SECONDS
    
    print(f"Sample database retention: keeping data from ts >= {cutoff_ts} (last {RETENTION_MINUTES} minutes)")
    print(f"  Max snapshot ts: {max_ts}")
    
    # Delete old snapshots
    for table in ["pred_snap", "veh_snap", "dock_snap"]:
        cursor.execute(f"DELETE FROM {table} WHERE ts < ?", (cutoff_ts,))
        deleted = cursor.rowcount
        cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
        remaining = cursor.fetchone()["count"]
        print(f"  {table}: deleted {deleted} old rows, {remaining} rows remaining")
    
    # Keep all poll_log rows for reference
    cursor.execute("SELECT COUNT(*) as count FROM poll_log")
    poll_count = cursor.fetchone()["count"]
    print(f"  poll_log: {poll_count} rows (all kept)")
    
    conn.commit()
    conn.close()


def copy_labels(dst_db: Path) -> None:
    """Copy labels and arrivals from labels.db to sample.db.
    
    Only copies columns that exist in both source and destination schemas.
    """
    if not LABELS_DB.exists():
        print(f"Labels database not found: {LABELS_DB}")
        return
    
    labels_conn = sqlite3.connect(str(LABELS_DB))
    labels_cursor = labels_conn.cursor()
    
    sample_conn = sqlite3.connect(str(dst_db))
    sample_cursor = sample_conn.cursor()
    
    try:
        # Get source and destination column names
        labels_cursor.execute("PRAGMA table_info(labels)")
        src_columns = {col[1] for col in labels_cursor.fetchall()}
        
        sample_cursor.execute("PRAGMA table_info(labels)")
        dst_columns = {col[1] for col in sample_cursor.fetchall()}
        
        # Find common columns
        common_columns = sorted(src_columns & dst_columns)
        
        if not common_columns:
            print("  labels: no common columns, skipping")
        else:
            # Copy labels table with only common columns
            labels_cursor.execute(f"SELECT {', '.join(common_columns)} FROM labels")
            labels_rows = labels_cursor.fetchall()
            
            placeholders = ", ".join(["?"] * len(common_columns))
            
            for row in labels_rows:
                sample_cursor.execute(
                    f"INSERT OR REPLACE INTO labels ({', '.join(common_columns)}) VALUES ({placeholders})",
                    row
                )
            
            print(f"  labels: copied {len(labels_rows)} rows ({', '.join(common_columns)})")
        
        # Copy arrivals table (if it exists in sample.db)
        try:
            labels_cursor.execute("PRAGMA table_info(arrivals)")
            src_arrival_cols = {col[1] for col in labels_cursor.fetchall()}
            
            sample_cursor.execute("PRAGMA table_info(arrivals)")
            dst_arrival_cols = {col[1] for col in sample_cursor.fetchall()}
            
            common_arrival_cols = sorted(src_arrival_cols & dst_arrival_cols)
            
            if common_arrival_cols:
                labels_cursor.execute(f"SELECT {', '.join(common_arrival_cols)} FROM arrivals")
                arrivals_rows = labels_cursor.fetchall()
                
                placeholders = ", ".join(["?"] * len(common_arrival_cols))
                
                for row in arrivals_rows:
                    sample_cursor.execute(
                        f"INSERT OR REPLACE INTO arrivals ({', '.join(common_arrival_cols)}) VALUES ({placeholders})",
                        row
                    )
                
                print(f"  arrivals: copied {len(arrivals_rows)} rows")
            else:
                print("  arrivals: no common columns, skipping")
        
        except sqlite3.OperationalError:
            print("  arrivals: table does not exist in sample.db, skipping")
        
        sample_conn.commit()
    
    finally:
        labels_conn.close()
        sample_conn.close()


def vacuum_and_check_size(db_path: Path, max_mb: int = 25) -> None:
    """VACUUM database and verify size limit."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("VACUUM")
    conn.close()
    
    size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"\nDatabase size: {size_mb:.2f} MB")
    
    if size_mb > max_mb:
        print(f"WARNING: sample.db exceeds {max_mb} MB limit!")
    else:
        print(f"✓ Within {max_mb} MB limit")


def main():
    """Create sample.db from raw.db."""
    print("Creating sample.db for demo and replay modes...\n")
    
    if not RAW_DB.exists():
        print(f"ERROR: raw.db not found: {RAW_DB}")
        return 1
    
    print(f"Source: {RAW_DB}")
    print(f"Destination: {SAMPLE_DB}\n")
    
    # Backup raw.db to sample.db
    print("Step 1: Backing up raw.db to sample.db...")
    backup_database(RAW_DB, SAMPLE_DB)
    print("✓ Backup complete\n")
    
    # Trim snapshots to last 90 minutes
    print("Step 2: Trimming snapshots to last 90 minutes...")
    trim_snapshots(SAMPLE_DB)
    print()
    
    # Copy labels from labels.db
    print("Step 3: Copying labels from labels.db...")
    copy_labels(SAMPLE_DB)
    print()
    
    # VACUUM and check size
    print("Step 4: Vacuuming and checking size...")
    vacuum_and_check_size(SAMPLE_DB)
    print()
    
    print("✓ sample.db ready for demo and replay modes")
    return 0


if __name__ == "__main__":
    exit(main())
