"""
Main file processing module
"""
import os
import shutil
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from fnmatch import fnmatch
import logging

try:
    import xxhash
    XXHASH_AVAILABLE = True
except ImportError:
    XXHASH_AVAILABLE = False

from .database import DatabaseManager
from .logger import ProgressLogger

logger = logging.getLogger(__name__)


class FileProcessor:
    """Main processor for file copying and tracking"""

    def __init__(
        self,
        db_manager: DatabaseManager,
        source_dir: str,
        target_dir: str,
        batch_size: int = 10,
        compute_hash: bool = False,
        hash_algorithm: str = "xxhash",
        exclude_patterns: Optional[List[str]] = None,
        recursive: bool = True,
        dry_run: bool = False
    ):
        """
        Initialize the file processor

        Args:
            db_manager: Database manager
            source_dir: Source directory
            target_dir: Target directory
            batch_size: Number of files to process per batch
            compute_hash: Enable hash computation
            hash_algorithm: Hash algorithm (xxhash or sha256)
            exclude_patterns: File patterns to exclude
            recursive: Recursive traversal of subdirectories
            dry_run: Simulation mode
        """
        self.db = db_manager
        self.source_dir = Path(source_dir)
        self.target_dir = Path(target_dir)
        self.batch_size = batch_size
        self.compute_hash = compute_hash
        self.hash_algorithm = hash_algorithm
        self.exclude_patterns = exclude_patterns or []
        self.recursive = recursive
        self.dry_run = dry_run

        # Validation
        if not self.source_dir.exists():
            raise ValueError(f"Source directory does not exist: {self.source_dir}")

        # Create target directory if necessary
        if not self.dry_run:
            self.target_dir.mkdir(parents=True, exist_ok=True)

        # Check xxhash availability
        if self.compute_hash and self.hash_algorithm == "xxhash" and not XXHASH_AVAILABLE:
            logger.warning("xxhash not available, using sha256")
            self.hash_algorithm = "sha256"

        logger.info(f"FileProcessor initialized - Source: {self.source_dir}, Target: {self.target_dir}")

    def get_source_files(self) -> List[Path]:
        """
        List all files in the source directory

        Returns:
            List of file paths
        """
        files = []

        if self.recursive:
            # Recursive traversal
            pattern = "**/*"
        else:
            # Non-recursive traversal
            pattern = "*"

        for path in self.source_dir.glob(pattern):
            if path.is_file() and not self._is_excluded(path):
                files.append(path)

        # Alphabetical sort
        files.sort(key=lambda p: p.name)

        logger.debug(f"Files found in source: {len(files)}")
        return files

    def _is_excluded(self, file_path: Path) -> bool:
        """
        Check if a file should be excluded

        Args:
            file_path: Path of the file to check

        Returns:
            True if the file should be excluded
        """
        filename = file_path.name

        for pattern in self.exclude_patterns:
            if fnmatch(filename, pattern):
                logger.debug(f"File excluded by pattern '{pattern}': {filename}")
                return True

        return False

    def _compute_file_hash(self, file_path: Path) -> str:
        """
        Compute the hash of a file

        Args:
            file_path: File path

        Returns:
            Hexadecimal hash of the file
        """
        if self.hash_algorithm == "xxhash" and XXHASH_AVAILABLE:
            hash_obj = xxhash.xxh64()
        else:
            hash_obj = hashlib.sha256()

        # Read in blocks for large files
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hash_obj.update(chunk)

        return hash_obj.hexdigest()

    def _copy_file(self, source: Path, target: Path) -> Tuple[bool, Optional[str]]:
        """
        Copy a file from source to target

        Args:
            source: Source path
            target: Target path

        Returns:
            Tuple (success, error message if failed)
        """
        try:
            # Check if file already exists
            if target.exists():
                return False, f"File already exists in target: {target}"

            if not self.dry_run:
                # Create parent directory if necessary
                target.parent.mkdir(parents=True, exist_ok=True)

                # Copy file
                shutil.copy2(source, target)

                # Verify copy
                if not target.exists():
                    return False, "Copy failed (file not created)"

                source_size = source.stat().st_size
                target_size = target.stat().st_size
                if source_size != target_size:
                    target.unlink()  # Delete corrupted copy
                    return False, f"Incorrect size after copy ({source_size} != {target_size})"

            logger.info(f"File copied: {source} -> {target}")
            return True, None

        except PermissionError as e:
            return False, f"Insufficient permissions: {str(e)}"
        except OSError as e:
            return False, f"System error: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"

    def process_batch(self) -> Dict[str, Any]:
        """
        Process a batch of files

        Returns:
            Processing statistics
        """
        start_time = datetime.now()
        stats = {
            'processed': 0,
            'skipped': 0,
            'errors': 0,
            'total_size': 0,
            'files_processed': [],
            'files_skipped': [],
            'files_errors': []
        }

        # Get the list of source files
        source_files = self.get_source_files()
        if not source_files:
            logger.info("No files to process in source directory")
            return stats

        # Filter already processed files
        filenames = [f.name for f in source_files]
        unprocessed_names = self.db.get_unprocessed_files(filenames)

        # Select files to process
        files_to_process = []
        for file_path in source_files:
            if file_path.name in unprocessed_names:
                files_to_process.append(file_path)
                if len(files_to_process) >= self.batch_size:
                    break

        if not files_to_process:
            logger.info("All files have already been processed")
            return stats

        logger.info(f"Starting processing of {len(files_to_process)} files")

        # Progress logger
        progress = ProgressLogger(logger, len(files_to_process), "Processing files")

        # Process each file
        for file_path in files_to_process:
            filename = file_path.name
            target_path = self.target_dir / filename
            file_size = file_path.stat().st_size

            # Log current file
            size_mb = file_size / (1024 * 1024)
            logger.info(f"Processing: {filename} ({size_mb:.2f} MB)")

            # Final check in DB (just in case)
            if self.db.is_file_processed(filename):
                logger.debug(f"File already in database (skip): {filename}")
                stats['skipped'] += 1
                stats['files_skipped'].append(filename)
                progress.update(1, f"Skip: {filename}")
                continue

            # Copy file
            success, error_msg = self._copy_file(file_path, target_path)

            if not success:
                # Copy error
                logger.error(f"Error copying {filename}: {error_msg}")

                if not self.dry_run:
                    self.db.log_error(filename, "COPY_ERROR", error_msg)

                stats['errors'] += 1
                stats['files_errors'].append({'file': filename, 'error': error_msg})
                progress.update(1, f"Error: {filename}")
                continue

            # Compute hash if requested
            file_hash = None
            if self.compute_hash and not self.dry_run:
                logger.debug(f"Computing hash for {filename}")
                try:
                    file_hash = self._compute_file_hash(target_path)
                except Exception as e:
                    logger.warning(f"Error computing hash: {str(e)}")

            # Register in database
            if not self.dry_run:
                try:
                    self.db.add_processed_file(
                        filename=filename,
                        source_path=str(file_path),
                        target_path=str(target_path),
                        size=file_size,
                        copy_date=datetime.now(),
                        file_hash=file_hash
                    )
                    logger.info(f"File registered in database: {filename}")
                except Exception as e:
                    # DB error - delete copied file
                    logger.error(f"Database error for {filename}: {str(e)}")
                    if target_path.exists():
                        target_path.unlink()
                        logger.warning(f"File deleted due to database error: {target_path}")

                    self.db.log_error(filename, "DB_ERROR", str(e))
                    stats['errors'] += 1
                    stats['files_errors'].append({'file': filename, 'error': str(e)})
                    progress.update(1, f"DB Error: {filename}")
                    continue

            # Success
            stats['processed'] += 1
            stats['total_size'] += file_size
            stats['files_processed'].append(filename)
            progress.update(1, f"OK: {filename}")

        # End processing
        progress.complete()

        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()
        stats['duration'] = duration

        # Summary
        total_size_mb = stats['total_size'] / (1024 * 1024)
        logger.info(
            f"Batch complete: {stats['processed']} processed, "
            f"{stats['skipped']} skipped, {stats['errors']} errors "
            f"({total_size_mb:.2f} MB in {duration:.2f}s)"
        )

        return stats

    def verify_target_files(self) -> List[str]:
        """
        Verify files present in the target directory

        Returns:
            List of files present in target
        """
        if not self.target_dir.exists():
            return []

        target_files = [f.name for f in self.target_dir.iterdir() if f.is_file()]
        logger.info(f"Files in target: {len(target_files)}")
        return target_files

    def clean_target_orphans(self) -> int:
        """
        Delete files from target that are not in the database

        Returns:
            Number of deleted files
        """
        target_files = self.verify_target_files()
        if not target_files:
            return 0

        # Check which files are in database
        processed = []
        for filename in target_files:
            if self.db.is_file_processed(filename):
                processed.append(filename)

        # Identify orphans
        orphans = set(target_files) - set(processed)

        if not orphans:
            logger.info("No orphan files in target")
            return 0

        # Delete orphans
        deleted = 0
        for filename in orphans:
            file_path = self.target_dir / filename
            if not self.dry_run:
                try:
                    file_path.unlink()
                    logger.info(f"Orphan file deleted: {filename}")
                    deleted += 1
                except Exception as e:
                    logger.error(f"Error deleting {filename}: {str(e)}")
            else:
                logger.info(f"[DRY-RUN] Orphan file to delete: {filename}")
                deleted += 1

        return deleted