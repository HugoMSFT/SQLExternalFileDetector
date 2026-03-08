"""Main external file detector application."""

import os
import logging
import tempfile
from typing import Dict, List, Any, Optional
from pathlib import Path

from .file_detector import FileDetector
from .sql_generator import SQLGenerator
from .storage_handlers import StorageHandler, StorageFactory

logger = logging.getLogger(__name__)


class ExternalFileDetectorApp:
    """Main application for external file detection and SQL DDL generation."""
    
    def __init__(self, storage_config: Dict[str, Any] = None):
        """
        Initialize the external file detector application.
        
        Args:
            storage_config: Configuration for cloud storage access
        """
        self.file_detector = FileDetector()
        self.sql_generator = SQLGenerator()
        self.storage_config = storage_config or {}
        self.temp_dir = None
    
    def analyze_location(self, location: str, data_source: str = None) -> Dict[str, Any]:
        """
        Analyze files at the given location and generate SQL DDL.
        
        Args:
            location: Path to analyze (local, S3, or Azure)
            data_source: Name of the external data source for SQL
            
        Returns:
            Analysis results with file metadata and SQL DDL
        """
        # Create storage handler
        storage_handler = StorageFactory.create_handler(location, **self.storage_config)
        
        # List files
        files = storage_handler.list_files(location)
        
        if not files:
            return {
                'location': location,
                'files_found': 0,
                'files': [],
                'error': 'No files found at the specified location'
            }
        
        # Create temporary directory for downloads if needed
        is_remote = location.startswith(('s3://', 'azure://', 'https://'))
        if is_remote:
            self.temp_dir = tempfile.mkdtemp()
        
        results = {
            'location': location,
            'files_found': len(files),
            'files': [],
            'summary': {
                'file_types': {},
                'total_size': 0,
                'total_files': len(files)
            }
        }
        
        try:
            for file_path in files:
                file_result = self._analyze_single_file(
                    file_path, storage_handler, data_source
                )
                results['files'].append(file_result)
                
                # Update summary
                file_type = file_result['metadata']['file_type']
                if file_type not in results['summary']['file_types']:
                    results['summary']['file_types'][file_type] = 0
                results['summary']['file_types'][file_type] += 1
                
                if 'file_size' in file_result['metadata']:
                    results['summary']['total_size'] += file_result['metadata']['file_size']
                    
        finally:
            # Clean up temporary directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)
        
        return results
    
    def _analyze_single_file(self, file_path: str, storage_handler: StorageHandler,
                           data_source: str = None) -> Dict[str, Any]:
        """Analyze a single file and generate SQL DDL."""
        local_path = file_path
        
        # Download file if it's remote
        is_remote = file_path.startswith(('s3://', 'azure://', 'https://'))
        if is_remote:
            filename = os.path.basename(file_path)
            local_path = os.path.join(self.temp_dir, filename)
            try:
                local_path = storage_handler.download_file(file_path, local_path)
            except Exception as e:
                logger.error("Failed to download %s: %s", file_path, e)
                return {
                    'file_path': file_path,
                    'error': f"Failed to download file: {str(e)}",
                    'metadata': {'file_type': 'unknown'},
                    'sql_ddl': None,
                    'table_name': self._generate_table_name(file_path)
                }
        
        # Analyze file metadata
        try:
            metadata = self.file_detector.analyze_file_metadata(local_path)
            metadata['original_path'] = file_path
        except Exception as e:
            logger.error("Failed to analyze %s: %s", file_path, e)
            return {
                'file_path': file_path,
                'error': f"Failed to analyze file: {str(e)}",
                'metadata': {'file_type': 'unknown'},
                'sql_ddl': None,
                'table_name': self._generate_table_name(file_path)
            }
        
        # Generate SQL DDL
        try:
            table_name = self._generate_table_name(file_path)
            ddl = self.sql_generator.generate_complete_ddl(
                metadata, table_name, data_source, file_path
            )
        except Exception as e:
            ddl = f"-- Error generating DDL: {str(e)}"
        
        return {
            'file_path': file_path,
            'metadata': metadata,
            'sql_ddl': ddl,
            'table_name': table_name
        }
    
    def _generate_table_name(self, file_path: str) -> str:
        """Generate a valid SQL table name from file path."""
        # Extract filename without extension
        filename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(filename)[0]
        
        # Clean name for SQL compatibility
        clean_name = ''.join(c if c.isalnum() else '_' for c in name_without_ext)
        
        # Ensure it doesn't start with a number
        if clean_name and clean_name[0].isdigit():
            clean_name = 'tbl_' + clean_name
        
        # Ensure it's not empty
        if not clean_name:
            clean_name = 'external_table'
        
        return f"ext_{clean_name}"
    
    def analyze_files(self, file_paths: List[str], data_source: str = None) -> List[Dict[str, Any]]:
        """
        Analyze multiple specific files.
        
        Args:
            file_paths: List of file paths to analyze
            data_source: Name of the external data source for SQL
            
        Returns:
            List of analysis results
        """
        results = []
        
        for file_path in file_paths:
            storage_handler = StorageFactory.create_handler(file_path, **self.storage_config)
            result = self._analyze_single_file(file_path, storage_handler, data_source)
            results.append(result)
        
        return results
    
    def generate_data_source_ddl(self, data_source_name: str, storage_type: str,
                                location: str, credential: str = None) -> str:
        """
        Generate CREATE EXTERNAL DATA SOURCE statement.
        
        Args:
            data_source_name: Name for the data source
            storage_type: Type of storage (S3, Azure, etc.)
            location: Base location/URL
            credential: Optional credential name
            
        Returns:
            SQL CREATE EXTERNAL DATA SOURCE statement
        """
        sql_parts = [f"CREATE EXTERNAL DATA SOURCE [{data_source_name}]"]
        sql_parts.append("WITH (")
        
        options = []
        
        if storage_type.lower() == 's3':
            options.append(f"    TYPE = HADOOP")
            options.append(f"    LOCATION = '{location}'")
        elif storage_type.lower() == 'azure':
            options.append(f"    TYPE = BLOB_STORAGE")
            options.append(f"    LOCATION = '{location}'")
        else:
            # Generic/local
            options.append(f"    TYPE = HADOOP")
            options.append(f"    LOCATION = '{location}'")
        
        if credential:
            options.append(f"    CREDENTIAL = [{credential}]")
        
        sql_parts.append(",\n".join(options))
        sql_parts.append(");")
        
        return "\n".join(sql_parts)
    
    def export_results(self, results: Dict[str, Any], output_file: str,
                      format: str = 'sql') -> None:
        """
        Export analysis results to file.
        
        Args:
            results: Analysis results
            output_file: Path to output file
            format: Output format ('sql', 'json')
        """
        output_dir = os.path.dirname(output_file)
        if output_dir:  # Only create directory if there's a directory part
            os.makedirs(output_dir, exist_ok=True)
        
        if format.lower() == 'json':
            import json
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)
        else:  # SQL format
            with open(output_file, 'w') as f:
                f.write("-- External File Detection Results\n")
                f.write(f"-- Location: {results['location']}\n")
                f.write(f"-- Files found: {results['files_found']}\n\n")
                
                for file_result in results['files']:
                    f.write(f"-- File: {file_result['file_path']}\n")
                    f.write(f"-- Type: {file_result['metadata']['file_type']}\n")
                    if 'error' in file_result:
                        f.write(f"-- Error: {file_result['error']}\n\n")
                    else:
                        f.write(file_result['sql_ddl'])
                        f.write("\n\n")
    
    def get_supported_file_types(self) -> List[str]:
        """Get list of supported file types."""
        return list(self.file_detector.SUPPORTED_EXTENSIONS.values())