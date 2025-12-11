"""
Configuration loading and management module
"""
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)


class Config:
    """Configuration manager for File Process Tracker"""

    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Initialize the configuration

        Args:
            config_path: Path to the YAML configuration file
        """
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}

        # Load environment variables from .env
        load_dotenv()

        # Load configuration
        self._load_config()
        self._apply_env_overrides()
        self._validate_config()

    def _load_config(self):
        """Load the YAML configuration file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        logger.info(f"Configuration loaded from: {self.config_path}")

    def _apply_env_overrides(self):
        """Apply overrides from environment variables"""
        env_mappings = {
            'SOURCE_DIR': ('source_dir',),
            'TARGET_DIR': ('target_dir',),
            'DATABASE_PATH': ('database', 'path'),
            'BATCH_SIZE': ('processing', 'batch_size'),
            'COMPUTE_HASH': ('hash', 'compute'),
            'HASH_ALGORITHM': ('hash', 'algorithm'),
            'LOG_LEVEL': ('logging', 'level'),
            'LOG_FILE': ('logging', 'file'),
            'DRY_RUN': ('execution', 'dry_run'),
            'RECURSIVE': ('processing', 'recursive'),
        }

        for env_var, config_path in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                self._set_nested_value(config_path, self._parse_value(env_value))
                logger.debug(f"Environment variable applied: {env_var}")

    def _parse_value(self, value: str) -> Any:
        """
        Parse a string value to appropriate Python type

        Args:
            value: Value to parse

        Returns:
            Parsed value
        """
        # Boolean
        if value.lower() in ('true', 'yes', '1'):
            return True
        elif value.lower() in ('false', 'no', '0'):
            return False

        # Number
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        return value

    def _set_nested_value(self, path: tuple, value: Any):
        """
        Set a value in the nested configuration

        Args:
            path: Path to the value (tuple of keys)
            value: Value to set
        """
        current = self.config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value

    def _validate_config(self):
        """Validate the loaded configuration"""
        required_fields = [
            ('source_dir',),
            ('target_dir',),
            ('database', 'path'),
            ('processing', 'batch_size'),
        ]

        for field_path in required_fields:
            value = self.get_nested_value(field_path)
            if value is None:
                field_name = '.'.join(field_path)
                raise ValueError(f"Required configuration field missing: {field_name}")

        # Path validation
        source_dir = Path(self.source_dir)
        if not source_dir.exists():
            logger.warning(f"Source directory does not exist: {source_dir}")

        # batch_size validation
        if self.batch_size <= 0:
            raise ValueError(f"batch_size must be positive: {self.batch_size}")

        logger.debug("Configuration validated successfully")

    def get_nested_value(self, path: tuple, default: Any = None) -> Any:
        """
        Retrieve a value from the nested configuration

        Args:
            path: Path to the value (tuple of keys)
            default: Default value if not found

        Returns:
            Found value or default value
        """
        current = self.config
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def apply_cli_overrides(self, **kwargs):
        """
        Apply overrides from CLI arguments

        Args:
            **kwargs: CLI arguments to apply
        """
        cli_mappings = {
            'batch_size': ('processing', 'batch_size'),
            'dry_run': ('execution', 'dry_run'),
            'compute_hash': ('hash', 'compute'),
            'hash_algorithm': ('hash', 'algorithm'),
            'log_level': ('logging', 'level'),
            'exclude': ('exclude_patterns',),
            'include': ('include_patterns',),
        }

        for cli_arg, config_path in cli_mappings.items():
            if cli_arg in kwargs and kwargs[cli_arg] is not None:
                value = kwargs[cli_arg]

                # Special handling for exclude and include (lists)
                if cli_arg == 'exclude':
                    current_excludes = self.get_nested_value(('exclude_patterns',), [])
                    if not isinstance(current_excludes, list):
                        current_excludes = []
                    value = current_excludes + list(value)
                elif cli_arg == 'include':
                    current_includes = self.get_nested_value(('include_patterns',), [])
                    if not isinstance(current_includes, list):
                        current_includes = []
                    value = current_includes + list(value)

                self._set_nested_value(config_path, value)
                logger.debug(f"CLI override applied: {cli_arg} = {value}")

    # Properties for easy access to common configurations

    @property
    def source_dir(self) -> str:
        """Source directory for files"""
        return self.config.get('source_dir', '')

    @property
    def target_dir(self) -> str:
        """Target directory for copies"""
        return self.config.get('target_dir', '')

    @property
    def database_path(self) -> str:
        """Database path"""
        return self.get_nested_value(('database', 'path'), 'data/file_tracker.db')

    @property
    def batch_size(self) -> int:
        """Number of files to process per batch"""
        return self.get_nested_value(('processing', 'batch_size'), 10)

    @property
    def recursive(self) -> bool:
        """Recursive traversal of subdirectories"""
        return self.get_nested_value(('processing', 'recursive'), True)

    @property
    def compute_hash(self) -> bool:
        """Enable hash computation"""
        return self.get_nested_value(('hash', 'compute'), False)

    @property
    def hash_algorithm(self) -> str:
        """Hash algorithm to use"""
        return self.get_nested_value(('hash', 'algorithm'), 'xxhash')

    @property
    def exclude_patterns(self) -> List[str]:
        """File patterns to exclude"""
        return self.get_nested_value(('exclude_patterns',), [])

    @property
    def include_patterns(self) -> List[str]:
        """File patterns to include"""
        return self.get_nested_value(('include_patterns',), [])

    @property
    def dry_run(self) -> bool:
        """Simulation mode without actual copy"""
        return self.get_nested_value(('execution', 'dry_run'), False)

    @property
    def log_level(self) -> str:
        """Log level"""
        return self.get_nested_value(('logging', 'level'), 'INFO')

    @property
    def log_file(self) -> str:
        """Log file"""
        return self.get_nested_value(('logging', 'file'), 'logs/file_processor.log')

    @property
    def log_rotation_count(self) -> int:
        """Number of log files to keep"""
        return self.get_nested_value(('logging', 'rotation_count'), 7)

    @property
    def log_max_bytes(self) -> int:
        """Maximum size of a log file"""
        return self.get_nested_value(('logging', 'max_bytes'), 10485760)

    @property
    def log_format(self) -> str:
        """Log message format"""
        return self.get_nested_value(
            ('logging', 'format'),
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Return the complete configuration as a dictionary

        Returns:
            Complete configuration
        """
        return self.config.copy()

    def summary(self) -> str:
        """
        Generate a summary of the active configuration

        Returns:
            Formatted configuration summary
        """
        summary = [
            "Active configuration:",
            f"  Source: {self.source_dir}",
            f"  Target: {self.target_dir}",
            f"  Database: {self.database_path}",
            f"  Batch size: {self.batch_size}",
            f"  Dry-run mode: {self.dry_run}",
            f"  Hash enabled: {self.compute_hash}",
            f"  Recursive: {self.recursive}",
            f"  Log level: {self.log_level}",
        ]

        if self.exclude_patterns:
            summary.append(f"  Exclusions: {', '.join(self.exclude_patterns)}")

        if self.include_patterns:
            summary.append(f"  Inclusions: {', '.join(self.include_patterns)}")

        return '\n'.join(summary)