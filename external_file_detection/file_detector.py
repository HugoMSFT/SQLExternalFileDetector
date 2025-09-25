"""File type detection and metadata analysis module."""

import os
import json
import csv
import mimetypes
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


class FileDetector:
    """Detects file types and analyzes metadata for SQL DDL generation."""
    
    SUPPORTED_EXTENSIONS = {
        '.txt': 'text',
        '.csv': 'csv',
        '.parquet': 'parquet',
        '.json': 'json',
        '.orc': 'orc',
        '.rc': 'rc',
        '.delta': 'delta'
    }
    
    def __init__(self):
        """Initialize the file detector."""
        pass
    
    def detect_file_type(self, file_path: str) -> str:
        """
        Detect the type of a file based on extension and content analysis.
        
        Args:
            file_path: Path to the file
            
        Returns:
            File type string
        """
        path = Path(file_path)
        extension = path.suffix.lower()
        
        if extension in self.SUPPORTED_EXTENSIONS:
            return self.SUPPORTED_EXTENSIONS[extension]
        
        # Try to detect by content for files without clear extensions
        try:
            return self._detect_by_content(file_path)
        except Exception:
            return 'unknown'
    
    def _detect_by_content(self, file_path: str) -> str:
        """Detect file type by analyzing content."""
        try:
            # Try JSON first
            with open(file_path, 'r', encoding='utf-8') as f:
                json.load(f)
            return 'json'
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        
        try:
            # Try CSV
            with open(file_path, 'r', encoding='utf-8') as f:
                sample = f.read(1024)
                sniffer = csv.Sniffer()
                if sniffer.has_header(sample):
                    return 'csv'
        except Exception:
            pass
        
        # Default to text
        return 'text'
    
    def analyze_file_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze file metadata including schema, size, and format details.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary containing metadata
        """
        file_type = self.detect_file_type(file_path)
        metadata = {
            'file_path': file_path,
            'file_type': file_type,
            'file_size': os.path.getsize(file_path),
            'schema': None,
            'row_count': None,
            'column_count': None,
            'delimiter': None,
            'encoding': 'utf-8',
            'has_header': False,
            'compression': None
        }
        
        try:
            if file_type == 'csv':
                metadata.update(self._analyze_csv(file_path))
            elif file_type == 'parquet':
                metadata.update(self._analyze_parquet(file_path))
            elif file_type == 'json':
                metadata.update(self._analyze_json(file_path))
            elif file_type == 'text':
                metadata.update(self._analyze_text(file_path))
        except Exception as e:
            metadata['error'] = str(e)
        
        return metadata
    
    def _analyze_csv(self, file_path: str) -> Dict[str, Any]:
        """Analyze CSV file metadata."""
        try:
            # Read a sample to detect delimiter and structure
            df = pd.read_csv(file_path, nrows=100)
            
            # Detect delimiter
            with open(file_path, 'r', encoding='utf-8') as f:
                sample = f.read(1024)
                sniffer = csv.Sniffer()
                delimiter = sniffer.sniff(sample).delimiter
            
            return {
                'schema': [(col, str(dtype)) for col, dtype in df.dtypes.items()],
                'row_count': len(pd.read_csv(file_path)),
                'column_count': len(df.columns),
                'delimiter': delimiter,
                'has_header': True,
                'encoding': 'utf-8'
            }
        except Exception:
            return {'delimiter': ',', 'has_header': False}
    
    def _analyze_parquet(self, file_path: str) -> Dict[str, Any]:
        """Analyze Parquet file metadata."""
        try:
            parquet_file = pq.ParquetFile(file_path)
            schema = parquet_file.schema_arrow
            
            return {
                'schema': [(field.name, str(field.type)) for field in schema],
                'row_count': parquet_file.metadata.num_rows,
                'column_count': len(schema),
                'compression': parquet_file.metadata.row_group(0).column(0).compression if parquet_file.metadata.num_row_groups > 0 else None
            }
        except Exception as e:
            # Fallback: try reading with pandas
            try:
                df = pd.read_parquet(file_path)
                return {
                    'schema': [(col, str(dtype)) for col, dtype in df.dtypes.items()],
                    'row_count': len(df),
                    'column_count': len(df.columns),
                }
            except Exception:
                return {}
    
    def _analyze_json(self, file_path: str) -> Dict[str, Any]:
        """Analyze JSON file metadata."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, list) and data:
                # Array of objects - infer schema from first object
                if isinstance(data[0], dict):
                    schema = [(key, type(value).__name__) for key, value in data[0].items()]
                    return {
                        'schema': schema,
                        'row_count': len(data),
                        'column_count': len(schema)
                    }
            elif isinstance(data, dict):
                # Single object
                schema = [(key, type(value).__name__) for key, value in data.items()]
                return {
                    'schema': schema,
                    'row_count': 1,
                    'column_count': len(schema)
                }
            
            return {}
        except Exception:
            return {}
    
    def _analyze_text(self, file_path: str) -> Dict[str, Any]:
        """Analyze text file metadata."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            return {
                'row_count': len(lines),
                'encoding': 'utf-8'
            }
        except UnicodeDecodeError:
            # Try different encodings
            for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        lines = f.readlines()
                    return {
                        'row_count': len(lines),
                        'encoding': encoding
                    }
                except UnicodeDecodeError:
                    continue
            return {'encoding': 'binary'}
    
    def scan_directory(self, directory_path: str) -> List[Dict[str, Any]]:
        """
        Scan a directory for supported files and analyze their metadata.
        
        Args:
            directory_path: Path to the directory to scan
            
        Returns:
            List of file metadata dictionaries
        """
        results = []
        
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                file_type = self.detect_file_type(file_path)
                
                if file_type != 'unknown':
                    metadata = self.analyze_file_metadata(file_path)
                    results.append(metadata)
        
        return results