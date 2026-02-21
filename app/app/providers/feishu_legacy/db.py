import sqlite3
from pathlib import Path


def get_conn(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str):
    conn = get_conn(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
          key TEXT PRIMARY KEY,
          value TEXT,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS folder_mappings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          local_rel_dir TEXT UNIQUE,
          remote_folder_token TEXT UNIQUE,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS file_mappings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          local_rel_path TEXT UNIQUE,
          remote_token TEXT UNIQUE,
          remote_type TEXT DEFAULT 'docx',
          local_hash TEXT,
          remote_hash TEXT,
          local_mtime REAL,
          remote_modified_time TEXT,
          status TEXT DEFAULT 'active',
          conflict INTEGER DEFAULT 0,
          last_synced_at DATETIME,
          extra_json TEXT,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tombstones (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          side TEXT,
          local_rel_path TEXT,
          remote_token TEXT,
          reason TEXT,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS retry_queue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          op_type TEXT,
          payload_json TEXT,
          attempt_count INTEGER DEFAULT 0,
          next_retry_at DATETIME,
          last_error TEXT,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_type TEXT,
          status TEXT,
          started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          finished_at DATETIME,
          summary_json TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          level TEXT,
          module TEXT,
          message TEXT,
          detail TEXT,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute("CREATE INDEX IF NOT EXISTS idx_file_mappings_remote_token ON file_mappings(remote_token)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_file_mappings_path ON file_mappings(local_rel_path)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_retry_next ON retry_queue(next_retry_at)")

    conn.commit()
    conn.close()
