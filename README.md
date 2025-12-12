# File Process Tracker

## Description

File Process Tracker is a tracking and management system for processing multimedia files (photos and videos). It allows batch copying of files from a source folder to a processing folder, while maintaining a complete history of operations in an SQLite database.

## Purpose

This project addresses the need to:
- Process multimedia files in controlled batches
- Maintain a history of already processed files to avoid duplicates
- Allow external processing of files in the target folder
- Ensure complete traceability of operations

## Workflow

1. **Initial copy**: The script copies N files from the source folder to the target folder
2. **Recording**: Each successful copy is recorded in the database
3. **External processing**: Files in target are processed by an external system (out of scope)
4. **Deletion**: Processed files are deleted from the target folder
5. **Iteration**: The script can be run again to copy the next N unprocessed files

## Technical Features

### Environment
- **Language**: Python 3.13+
- **Database**: SQLite (local)
- **System**: Local processing only (no network)

### File Types
- **Photos**: ~5 MB per file
- **Videos**: up to 5-10 GB per file
- **Volume**: ~10,000 files/year over potential 10 years

### Performance
- Optional hashing (disabled by default for large files)
- Configurable batch processing
- Support for hierarchical folder structures (year/month)

## Installation

### Option 1: Docker Deployment (Recommended for NAS)

**Perfect for NAS or servers with older Python versions**

#### Prerequisites
- Docker installed

#### Steps

1. **Create deployment package**
   ```bash
   ./package.sh
   ```

2. **Transfer to your NAS**
   - Upload `file-tracker-deploy.zip` to your NAS
   - Extract the archive

3. **Configure**
   ```bash
   cp .env.nas.example .env
   vi .env  # Edit with your paths
   ```

4. **Build and run**
   ```bash
   # First time - build the Docker image
   ./run.sh --build

   # Run the processing
   ./run.sh

   # With options
   ./run.sh --dry-run
   ./run.sh --batch-size 50
   ./run.sh --include "*.jpg"
   ```

### Option 2: Native Python Installation

#### Prerequisites
- Python 3.8 or higher
- pip for dependency installation

#### Installing Dependencies

```bash
# Clone the project
git clone [repo-url]
cd file-process-tracker

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -e .
```

## Configuration

### Main Configuration File

The `config/config.yaml` file contains default settings:

```yaml
# Paths
source_dir: "/path/to/source"
target_dir: "/path/to/target"

# Processing
batch_size: 10  # Number of files to copy per execution
compute_hash: false  # Hash calculation (false recommended for large files)
hash_algorithm: "xxhash"  # Faster than sha256

# Filters
exclude_patterns:
  - "*.tmp"
  - ".*"  # Hidden files
  - "*.part"  # Partial files

# Options
dry_run: false  # Simulation mode
recursive: true  # Recursive subfolder traversal

# Logging
log_level: "INFO"
log_file: "logs/file_processor.log"
log_rotation_count: 7  # Number of log files to keep
```

### Environment Variables

Create a `.env` file to override configuration:

```bash
SOURCE_DIR=/my/source/folder
TARGET_DIR=/my/target/folder
BATCH_SIZE=20
```

## Usage

### With Docker (Recommended)

```bash
# Basic processing
./run.sh

# Dry-run mode (simulation)
./run.sh --dry-run

# Process specific number of files
./run.sh --batch-size 50

# Filter files by pattern
./run.sh --include "*.jpg"
./run.sh --include "*.mp4" --include "*.mov"

# View statistics
./run.sh --stats

# List processed files
./run.sh --list-processed

# Check database integrity
./run.sh --check-integrity

# Clean orphaned files in target
./run.sh --clean-orphans
```

### With Native Python

#### Basic Command

```bash
python main.py
```

#### Command Line Options

```bash
# Specify the number of files to process
python main.py --batch-size 20

# Dry-run mode (simulation)
python main.py --dry-run

# Detailed log level
python main.py --log-level DEBUG

# Exclude additional patterns
python main.py --exclude "*.log" --exclude "temp_*"

# Include only specific patterns
python main.py --include "*.jpg" --include "*.png"

# Enable hash calculation
python main.py --compute-hash

# Help
python main.py --help
```

#### Usage Examples

```bash
# First run: copy 10 files
python main.py

# Weekly execution with 50 files
python main.py --batch-size 50

# Test without actual copy
python main.py --dry-run --batch-size 10

# With hash for integrity verification
python main.py --compute-hash --hash-algorithm sha256

# Process only JPG files
python main.py --include "*.jpg"
```

## Database Structure

### `processed_files` Table

| Column | Type | Description |
|---------|------|-------------|
| id | INTEGER | Auto-incremented primary key |
| filename | TEXT | File name (unique) |
| source_path | TEXT | Full source path |
| target_path | TEXT | Full destination path |
| size | INTEGER | Size in bytes |
| copy_date | DATETIME | Copy date and time |
| hash | TEXT | File hash (optional) |

### `errors` Table

| Column | Type | Description |
|---------|------|-------------|
| id | INTEGER | Auto-incremented primary key |
| timestamp | DATETIME | Error date and time |
| filename | TEXT | Affected file name |
| error_type | TEXT | Error type |
| error_message | TEXT | Detailed message |

## Project Structure

```
file-process-tracker/
├── config/
│   └── config.yaml          # Default configuration
├── src/
│   ├── __init__.py
│   ├── database.py          # SQLite management
│   ├── file_processor.py    # Copy logic
│   ├── config_loader.py     # Configuration loading
│   └── logger.py            # Logging configuration
├── logs/                     # Logs with rotation
├── data/                     # SQLite database
├── tests/                    # Unit tests
├── .env.example              # Configuration example (native)
├── .env.nas.example          # Configuration example (Docker)
├── Dockerfile                # Docker image definition
├── .dockerignore             # Docker build exclusions
├── run.sh                    # Docker run script
├── package.sh                # Deployment packaging script
├── main.py                   # Entry point
├── pyproject.toml            # Project configuration
└── README.md                 # This documentation
```

## Logs

Logs are generated in the `logs/` folder with automatic rotation:
- Format: `file_processor.log`, `file_processor.log.1`, etc.
- Retention: Maximum 7 files
- Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

Log example:
```
2024-12-11 10:30:15 INFO - Starting batch processing (10 files)
2024-12-11 10:30:16 INFO - Copying: photo_001.jpg (5.2 MB)
2024-12-11 10:30:17 INFO - File copied and recorded: photo_001.jpg
2024-12-11 10:30:25 WARNING - File already processed: photo_002.jpg
2024-12-11 10:35:45 INFO - Batch completed: 9/10 files copied successfully
```

## Error Handling

- **File exists in target**: Skip with warning
- **File already in database**: Silent skip
- **Copy error**: Transaction rollback, log in errors table
- **Insufficient disk space**: Batch stop, notification
- **Insufficient permissions**: Log error, proceed to next file

## Maintenance

### Integrity Check

```bash
# Check database consistency
python main.py --check-integrity

# List processed files
python main.py --list-processed

# Statistics
python main.py --stats
```

### Backup

The SQLite database is stored in `data/file_tracker.db`. Remember to back it up regularly:

```bash
cp data/file_tracker.db data/backup/file_tracker_$(date +%Y%m%d).db
```

## Limitations

- Local processing only (no network support for performance reasons)
- Unique identification by filename (files must not be renamed)
- No automatic database purging
- No GUI or REST API

## Possible Enhancements

- Automatic source file partitioning by date support
- Background hash calculation
- Email notification at batch end
- Recovery mode after interruption

## License

[To be defined]

## Contact

[To be defined]