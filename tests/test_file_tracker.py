"""
Simple pytest tests for File Process Tracker
"""
import pytest
import tempfile
import shutil
from pathlib import Path
import sqlite3
from datetime import datetime

from src.database import DatabaseManager
from src.config_loader import Config
from src.file_processor import FileProcessor


@pytest.fixture
def temp_dirs():
    """Create temporary source and target directories"""
    source_dir = tempfile.mkdtemp(prefix="test_source_")
    target_dir = tempfile.mkdtemp(prefix="test_target_")

    yield source_dir, target_dir

    # Cleanup
    shutil.rmtree(source_dir, ignore_errors=True)
    shutil.rmtree(target_dir, ignore_errors=True)


@pytest.fixture
def temp_db():
    """Create a temporary database"""
    db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = db_file.name
    db_file.close()

    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def sample_files(temp_dirs):
    """Create sample files in source directory"""
    source_dir, _ = temp_dirs
    source_path = Path(source_dir)

    # Create various test files
    files = {
        "file1.txt": "Content of file 1",
        "file2.jpg": "Image data",
        "file3.mp4": "Video data",
        ".hidden_file.txt": "Hidden file",
        "temp.tmp": "Temporary file",
    }

    created_files = []
    for filename, content in files.items():
        file_path = source_path / filename
        file_path.write_text(content)
        created_files.append(file_path)

    return created_files


class TestDatabaseManager:
    """Test database operations"""

    def test_database_initialization(self, temp_db):
        """Test that database is properly initialized with tables"""
        db = DatabaseManager(temp_db)

        # Check tables exist
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

        assert "processed_files" in tables
        assert "errors" in tables

        db.close()

    def test_add_processed_file(self, temp_db):
        """Test adding a processed file to database"""
        db = DatabaseManager(temp_db)

        # Add a file
        file_id = db.add_processed_file(
            filename="test.txt",
            source_path="/source/test.txt",
            target_path="/target/test.txt",
            size=1024,
            copy_date=datetime.now(),
            file_hash="abc123"
        )

        assert file_id > 0
        assert db.is_file_processed("test.txt")
        assert not db.is_file_processed("nonexistent.txt")

        db.close()

    def test_get_unprocessed_files(self, temp_db):
        """Test filtering unprocessed files"""
        db = DatabaseManager(temp_db)

        # Add some files
        db.add_processed_file(
            filename="file1.txt",
            source_path="/source/file1.txt",
            target_path="/target/file1.txt",
            size=100,
            copy_date=datetime.now()
        )

        # Test filtering
        all_files = ["file1.txt", "file2.txt", "file3.txt"]
        unprocessed = db.get_unprocessed_files(all_files)

        assert "file1.txt" not in unprocessed
        assert "file2.txt" in unprocessed
        assert "file3.txt" in unprocessed
        assert len(unprocessed) == 2

        db.close()

    def test_log_error(self, temp_db):
        """Test error logging"""
        db = DatabaseManager(temp_db)

        error_id = db.log_error(
            filename="problem.txt",
            error_type="COPY_ERROR",
            error_message="Permission denied"
        )

        assert error_id > 0

        # Check statistics include the error
        stats = db.get_statistics()
        assert stats['total_errors'] == 1

        db.close()


class TestFileProcessor:
    """Test file processing operations"""

    def test_get_source_files_with_exclusions(self, temp_dirs, sample_files, temp_db):
        """Test file listing with exclusion patterns"""
        source_dir, target_dir = temp_dirs
        db = DatabaseManager(temp_db)

        processor = FileProcessor(
            db_manager=db,
            source_dir=source_dir,
            target_dir=target_dir,
            exclude_patterns=["*.tmp", ".*"],
            recursive=False,
            dry_run=True
        )

        files = processor.get_source_files()
        filenames = [f.name for f in files]

        # Should include regular files
        assert "file1.txt" in filenames
        assert "file2.jpg" in filenames
        assert "file3.mp4" in filenames

        # Should exclude hidden and tmp files
        assert ".hidden_file.txt" not in filenames
        assert "temp.tmp" not in filenames

        db.close()

    def test_process_batch_dry_run(self, temp_dirs, sample_files, temp_db):
        """Test batch processing in dry-run mode"""
        source_dir, target_dir = temp_dirs
        db = DatabaseManager(temp_db)

        processor = FileProcessor(
            db_manager=db,
            source_dir=source_dir,
            target_dir=target_dir,
            batch_size=2,
            exclude_patterns=["*.tmp", ".*"],
            dry_run=True
        )

        stats = processor.process_batch()

        # Check statistics
        assert stats['processed'] == 2  # batch_size = 2
        assert stats['skipped'] == 0
        assert stats['errors'] == 0

        # In dry-run, files should NOT be copied
        target_path = Path(target_dir)
        assert len(list(target_path.iterdir())) == 0

        # Database should NOT have records in dry-run
        assert not db.is_file_processed("file1.txt")

        db.close()

    def test_process_batch_real(self, temp_dirs, sample_files, temp_db):
        """Test actual batch processing"""
        source_dir, target_dir = temp_dirs
        db = DatabaseManager(temp_db)

        processor = FileProcessor(
            db_manager=db,
            source_dir=source_dir,
            target_dir=target_dir,
            batch_size=2,
            exclude_patterns=["*.tmp", ".*"],
            dry_run=False
        )

        # First batch
        stats1 = processor.process_batch()
        assert stats1['processed'] == 2

        # Check files were copied
        target_path = Path(target_dir)
        target_files = list(target_path.iterdir())
        assert len(target_files) == 2

        # Check database records
        assert db.is_file_processed("file1.txt")
        assert db.is_file_processed("file2.jpg")

        # Second batch (remaining file)
        stats2 = processor.process_batch()
        assert stats2['processed'] == 1  # Only file3.mp4 left

        # Third batch (no files left)
        stats3 = processor.process_batch()
        assert stats3['processed'] == 0

        db.close()

    def test_duplicate_prevention(self, temp_dirs, sample_files, temp_db):
        """Test that already processed files are not reprocessed"""
        source_dir, target_dir = temp_dirs
        db = DatabaseManager(temp_db)

        # First, add a file to the database manually
        db.add_processed_file(
            filename="file1.txt",
            source_path=str(Path(source_dir) / "file1.txt"),
            target_path=str(Path(target_dir) / "file1.txt"),
            size=100,
            copy_date=datetime.now()
        )

        processor = FileProcessor(
            db_manager=db,
            source_dir=source_dir,
            target_dir=target_dir,
            batch_size=10,
            exclude_patterns=["*.tmp", ".*"],
            dry_run=False
        )

        stats = processor.process_batch()

        # file1.txt should be skipped, only file2.jpg and file3.mp4 processed
        assert stats['processed'] == 2
        assert not db.is_file_processed("file4.txt")  # Doesn't exist

        db.close()

    def test_clean_orphans(self, temp_dirs, temp_db):
        """Test cleaning orphan files from target"""
        source_dir, target_dir = temp_dirs
        target_path = Path(target_dir)

        # Create an orphan file directly in target
        orphan_file = target_path / "orphan.txt"
        orphan_file.write_text("I should be deleted")

        # Create a tracked file
        tracked_file = target_path / "tracked.txt"
        tracked_file.write_text("I should stay")

        # Add tracked file to database
        db = DatabaseManager(temp_db)
        db.add_processed_file(
            filename="tracked.txt",
            source_path="/source/tracked.txt",
            target_path=str(tracked_file),
            size=100,
            copy_date=datetime.now()
        )

        processor = FileProcessor(
            db_manager=db,
            source_dir=source_dir,
            target_dir=target_dir,
            dry_run=False
        )

        deleted = processor.clean_target_orphans()

        assert deleted == 1
        assert not orphan_file.exists()
        assert tracked_file.exists()

        db.close()


class TestConfiguration:
    """Test configuration loading"""

    def test_config_validation(self):
        """Test configuration validation"""
        # This should raise an error for missing config file
        with pytest.raises(FileNotFoundError):
            Config("nonexistent.yaml")

    def test_config_defaults(self, tmp_path):
        """Test default configuration values"""
        # Create minimal config
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text("""
source_dir: /test/source
target_dir: /test/target
database:
  path: test.db
processing:
  batch_size: 5
""")

        config = Config(str(config_file))

        assert config.source_dir == "/test/source"
        assert config.target_dir == "/test/target"
        assert config.batch_size == 5
        assert config.recursive is True  # Default
        assert config.compute_hash is False  # Default
        assert config.dry_run is False  # Default


class TestStatistics:
    """Test statistics and reporting"""

    def test_get_statistics(self, temp_db):
        """Test statistics calculation"""
        db = DatabaseManager(temp_db)

        # Add some test data
        for i in range(3):
            db.add_processed_file(
                filename=f"file{i}.txt",
                source_path=f"/source/file{i}.txt",
                target_path=f"/target/file{i}.txt",
                size=1024 * (i + 1),  # 1KB, 2KB, 3KB
                copy_date=datetime.now()
            )

        # Add an error
        db.log_error("error_file.txt", "COPY_ERROR", "Test error")

        stats = db.get_statistics()

        assert stats['total_files'] == 3
        assert stats['total_size'] == 6144  # 1024 + 2048 + 3072
        assert stats['total_errors'] == 1
        assert stats['last_copy'] is not None

        db.close()

    def test_check_integrity(self, temp_db):
        """Test database integrity check"""
        db = DatabaseManager(temp_db)

        # Add normal file
        db.add_processed_file(
            filename="good.txt",
            source_path="/source/good.txt",
            target_path="/target/good.txt",
            size=100,
            copy_date=datetime.now()
        )

        integrity = db.check_integrity()

        assert integrity['status'] == 'ok'
        assert integrity['integrity_check'] == 'ok'
        assert len(integrity['duplicates']) == 0

        db.close()


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])