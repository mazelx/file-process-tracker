#!/usr/bin/env python3
"""
File Process Tracker - Main script
File processing tracking and management system
"""
import sys
import click
from pathlib import Path
from datetime import datetime
import json as json_module

from src.config_loader import Config
from src.database import DatabaseManager
from src.file_processor import FileProcessor
from src.logger import setup_logging


@click.command()
@click.option(
    '--batch-size',
    type=int,
    help='Number of files to process in this batch'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Simulation mode - shows what would be done without doing it'
)
@click.option(
    '--compute-hash',
    is_flag=True,
    help='Enable hash computation for integrity verification'
)
@click.option(
    '--hash-algorithm',
    type=click.Choice(['xxhash', 'sha256']),
    help='Hash algorithm to use'
)
@click.option(
    '--exclude',
    multiple=True,
    help='File pattern to exclude (can be used multiple times)'
)
@click.option(
    '--log-level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']),
    help='Log level'
)
@click.option(
    '--config',
    type=click.Path(exists=True),
    default='config/config.yaml',
    help='Configuration file to use'
)
@click.option(
    '--check-integrity',
    is_flag=True,
    help='Check database integrity'
)
@click.option(
    '--list-processed',
    is_flag=True,
    help='List already processed files'
)
@click.option(
    '--stats',
    is_flag=True,
    help='Display processing statistics'
)
@click.option(
    '--clean-orphans',
    is_flag=True,
    help='Delete files from target that are not in the database'
)
@click.option(
    '--json',
    is_flag=True,
    help='JSON format output'
)
def main(
    batch_size,
    dry_run,
    compute_hash,
    hash_algorithm,
    exclude,
    log_level,
    config,
    check_integrity,
    list_processed,
    stats,
    clean_orphans,
    json: bool
):
    """
    File Process Tracker - File processing tracking system

    Batch copy files from a source directory to a target directory,
    with database recording to avoid duplicates.
    """
    try:
        # Load configuration
        cfg = Config(config)

        # Apply CLI overrides
        cli_overrides = {
            'batch_size': batch_size,
            'dry_run': dry_run,
            'compute_hash': compute_hash,
            'hash_algorithm': hash_algorithm,
            'exclude': exclude,
            'log_level': log_level,
        }
        cfg.apply_cli_overrides(**cli_overrides)

        # Logging configuration
        if not json:
            logger = setup_logging(
                level=cfg.log_level,
                log_file=cfg.log_file,
                log_format=cfg.log_format,
                max_bytes=cfg.log_max_bytes,
                rotation_count=cfg.log_rotation_count,
                console=True
            )

            if dry_run or cfg.dry_run:
                logger.info("=== DRY-RUN MODE ENABLED ===")

            logger.debug(cfg.summary())

        # Database connection
        with DatabaseManager(cfg.database_path) as db:

            # Integrity check mode
            if check_integrity:
                result = db.check_integrity()
                if json:
                    print(json_module.dumps(result, indent=2, default=str))
                else:
                    logger.info("=== Integrity Check ===")
                    logger.info(f"Status: {result['status']}")
                    logger.info(f"SQLite integrity: {result['integrity_check']}")
                    if result['duplicates']:
                        logger.warning(f"Duplicates detected: {result['duplicate_count']}")
                        for dup in result['duplicates']:
                            logger.warning(f"  - {dup['filename']} ({dup['count']} times)")
                return

            # List processed files mode
            if list_processed:
                files = db.get_processed_files(limit=100)
                if json:
                    print(json_module.dumps(files, indent=2, default=str))
                else:
                    logger.info(f"=== Last processed files ({len(files)}) ===")
                    for f in files:
                        size_mb = f['size'] / (1024 * 1024)
                        logger.info(
                            f"  {f['filename']} - {size_mb:.2f} MB - "
                            f"{f['copy_date']}"
                        )
                return

            # Statistics mode
            if stats:
                statistics = db.get_statistics()
                if json:
                    print(json_module.dumps(statistics, indent=2, default=str))
                else:
                    logger.info("=== Statistics ===")
                    logger.info(f"Processed files: {statistics['total_files']}")
                    logger.info(f"Total size: {statistics['total_size_gb']} GB")
                    logger.info(f"Logged errors: {statistics['total_errors']}")
                    if statistics['last_copy']:
                        logger.info(f"Last copy: {statistics['last_copy']}")
                return

            # File processor initialization
            processor = FileProcessor(
                db_manager=db,
                source_dir=cfg.source_dir,
                target_dir=cfg.target_dir,
                batch_size=cfg.batch_size,
                compute_hash=cfg.compute_hash,
                hash_algorithm=cfg.hash_algorithm,
                exclude_patterns=cfg.exclude_patterns,
                recursive=cfg.recursive,
                dry_run=cfg.dry_run
            )

            # Orphan cleanup mode
            if clean_orphans:
                if not json:
                    logger.info("=== Orphan Files Cleanup ===")
                deleted = processor.clean_target_orphans()
                if json:
                    print(json_module.dumps({'deleted': deleted}, indent=2))
                else:
                    logger.info(f"Orphan files deleted: {deleted}")
                return

            # Normal processing mode - file copying
            if not json:
                logger.info("=== Starting Processing ===")

            result = processor.process_batch()

            # Display results
            if json:
                # Remove file lists to lighten JSON output
                compact_result = {
                    'processed': result['processed'],
                    'skipped': result['skipped'],
                    'errors': result['errors'],
                    'total_size_mb': result['total_size'] / (1024 * 1024),
                    'duration': result.get('duration', 0)
                }
                print(json_module.dumps(compact_result, indent=2))
            else:
                logger.info("=== Processing Summary ===")
                logger.info(f"Processed files: {result['processed']}")
                logger.info(f"Skipped files: {result['skipped']}")
                logger.info(f"Errors: {result['errors']}")

                total_size_mb = result['total_size'] / (1024 * 1024)
                if total_size_mb > 1024:
                    total_size_gb = total_size_mb / 1024
                    logger.info(f"Total size copied: {total_size_gb:.2f} GB")
                else:
                    logger.info(f"Total size copied: {total_size_mb:.2f} MB")

                if result.get('duration'):
                    logger.info(f"Duration: {result['duration']:.2f} seconds")

                # Error details if present
                if result['files_errors']:
                    logger.warning("Error details:")
                    for error_info in result['files_errors']:
                        logger.warning(f"  - {error_info['file']}: {error_info['error']}")

            # Exit code
            if result['errors'] > 0:
                sys.exit(1)

    except FileNotFoundError as e:
        if not json:
            click.echo(f"Error: {str(e)}", err=True)
        else:
            print(json_module.dumps({'error': str(e)}, indent=2))
        sys.exit(1)

    except ValueError as e:
        if not json:
            click.echo(f"Configuration error: {str(e)}", err=True)
        else:
            print(json_module.dumps({'error': str(e)}, indent=2))
        sys.exit(1)

    except Exception as e:
        if not json:
            click.echo(f"Unexpected error: {str(e)}", err=True)
        else:
            print(json_module.dumps({'error': str(e), 'type': type(e).__name__}, indent=2))
        sys.exit(2)


if __name__ == "__main__":
    main()