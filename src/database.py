"""
SQLite database management module
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Configure SQLite datetime adapters for Python 3.12+ compatibility
def adapt_datetime(dt):
    """Convert datetime to ISO 8601 string for SQLite storage"""
    return dt.isoformat()

def convert_datetime(s):
    """Convert ISO 8601 string from SQLite to datetime object"""
    return datetime.fromisoformat(s.decode())

# Register the adapters and converters
sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("timestamp", convert_datetime)


class DatabaseManager:
    """SQLite database manager for file tracking"""

    def __init__(self, db_path: str):
        """
        Initialize the database manager

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection: Optional[sqlite3.Connection] = None
        self._initialize_database()

    def _initialize_database(self):
        """Create tables if they don't exist"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Processed files table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT UNIQUE NOT NULL,
                    source_path TEXT NOT NULL,
                    target_path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    copy_date DATETIME NOT NULL,
                    hash TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index to improve performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_filename
                ON processed_files (filename)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_copy_date
                ON processed_files (copy_date)
            """)

            # Errors table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    filename TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            logger.info(f"Database initialized: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get a database connection

        Returns:
            SQLite connection
        """
        if self.connection is None:
            self.connection = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            self.connection.row_factory = sqlite3.Row
        return self.connection

    def close(self):
        """Close the database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.debug("Database connection closed")

    def is_file_processed(self, filename: str) -> bool:
        """
        Check if a file has already been processed

        Args:
            filename: Name of the file to check

        Returns:
            True if the file has already been processed, False otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM processed_files WHERE filename = ?",
                (filename,)
            )
            return cursor.fetchone() is not None

    def add_processed_file(
        self,
        filename: str,
        source_path: str,
        target_path: str,
        size: int,
        copy_date: datetime,
        file_hash: Optional[str] = None
    ) -> int:
        """
        Add a processed file to the database

        Args:
            filename: File name
            source_path: Full source path
            target_path: Full target path
            size: File size in bytes
            copy_date: Copy date and time
            file_hash: File hash (optional)

        Returns:
            ID of the created record

        Raises:
            sqlite3.IntegrityError: If the file already exists
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO processed_files
                (filename, source_path, target_path, size, copy_date, hash)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (filename, source_path, target_path, size, copy_date, file_hash))
            conn.commit()

            file_id = cursor.lastrowid
            logger.info(f"File registered: {filename} (ID: {file_id})")
            return file_id

    def log_error(
        self,
        filename: str,
        error_type: str,
        error_message: str
    ) -> int:
        """
        Log an error to the database

        Args:
            filename: Name of the affected file
            error_type: Type of error
            error_message: Detailed error message

        Returns:
            Error record ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO errors
                (timestamp, filename, error_type, error_message)
                VALUES (?, ?, ?, ?)
            """, (datetime.now(), filename, error_type, error_message))
            conn.commit()

            error_id = cursor.lastrowid
            logger.error(f"Error logged for {filename}: {error_type}")
            return error_id

    def get_processed_files(
        self,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the list of processed files

        Args:
            limit: Maximum number of records to return
            offset: Offset for pagination

        Returns:
            List of processed files
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT * FROM processed_files
                ORDER BY copy_date DESC
            """

            if limit:
                query += f" LIMIT {limit} OFFSET {offset}"

            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def get_unprocessed_files(
        self,
        source_files: List[str]
    ) -> List[str]:
        """
        Filter a file list to keep only unprocessed files

        Args:
            source_files: List of file names to check

        Returns:
            List of not yet processed files
        """
        if not source_files:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(source_files))
            cursor.execute(
                f"SELECT filename FROM processed_files WHERE filename IN ({placeholders})",
                source_files
            )
            processed = {row['filename'] for row in cursor.fetchall()}

            unprocessed = [f for f in source_files if f not in processed]
            logger.debug(f"Unprocessed files: {len(unprocessed)}/{len(source_files)}")
            return unprocessed

    def get_statistics(self) -> Dict[str, Any]:
        """
        Retrieve database statistics

        Returns:
            Dictionary containing statistics
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total number of processed files
            cursor.execute("SELECT COUNT(*) as count FROM processed_files")
            total_files = cursor.fetchone()['count']

            # Total size
            cursor.execute("SELECT SUM(size) as total_size FROM processed_files")
            total_size = cursor.fetchone()['total_size'] or 0

            # Number of errors
            cursor.execute("SELECT COUNT(*) as count FROM errors")
            total_errors = cursor.fetchone()['count']

            # Last copy
            cursor.execute("""
                SELECT copy_date FROM processed_files
                ORDER BY copy_date DESC LIMIT 1
            """)
            last_copy_row = cursor.fetchone()
            last_copy = last_copy_row['copy_date'] if last_copy_row else None

            return {
                'total_files': total_files,
                'total_size': total_size,
                'total_size_gb': round(total_size / (1024**3), 2) if total_size else 0,
                'total_errors': total_errors,
                'last_copy': last_copy
            }

    def check_integrity(self) -> Dict[str, Any]:
        """
        Check database integrity

        Returns:
            Integrity report
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Check for duplicates
            cursor.execute("""
                SELECT filename, COUNT(*) as count
                FROM processed_files
                GROUP BY filename
                HAVING count > 1
            """)
            duplicates = cursor.fetchall()

            # Check SQLite integrity
            cursor.execute("PRAGMA integrity_check")
            integrity_check = cursor.fetchone()[0]

            return {
                'status': 'ok' if integrity_check == 'ok' and not duplicates else 'warning',
                'integrity_check': integrity_check,
                'duplicates': [dict(row) for row in duplicates] if duplicates else [],
                'duplicate_count': len(duplicates) if duplicates else 0
            }

    def begin_transaction(self):
        """Start a transaction"""
        self._get_connection().execute("BEGIN")

    def commit_transaction(self):
        """Commit the current transaction"""
        self._get_connection().commit()

    def rollback_transaction(self):
        """Rollback the current transaction"""
        self._get_connection().rollback()
        logger.warning("Transaction rolled back")

    def __enter__(self):
        """Context manager support"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Automatic closure on context exit"""
        self.close()