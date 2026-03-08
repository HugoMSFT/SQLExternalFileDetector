"""External File Detection package for SQL DDL generation."""

__version__ = "1.0.0"

from .file_detector import FileDetector
from .sql_generator import SQLGenerator
from .external_file_detector import ExternalFileDetectorApp
from .storage_handlers import StorageHandler, StorageFactory

__all__ = [
    "FileDetector",
    "SQLGenerator",
    "ExternalFileDetectorApp",
    "StorageHandler",
    "StorageFactory",
]