"""Tests for file detector functionality."""

import os
import tempfile
import json
import csv
from pathlib import Path

from external_file_detection.file_detector import FileDetector


def test_file_type_detection():
    """Test file type detection."""
    detector = FileDetector()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test files
        csv_file = os.path.join(temp_dir, "test.csv")
        json_file = os.path.join(temp_dir, "test.json")
        txt_file = os.path.join(temp_dir, "test.txt")
        
        # CSV file
        with open(csv_file, 'w') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name'])
            writer.writerow([1, 'John'])
        
        # JSON file
        with open(json_file, 'w') as f:
            json.dump({"id": 1, "name": "John"}, f)
        
        # Text file
        with open(txt_file, 'w') as f:
            f.write("This is a text file")
        
        # Test detection
        assert detector.detect_file_type(csv_file) == 'csv'
        assert detector.detect_file_type(json_file) == 'json'
        assert detector.detect_file_type(txt_file) == 'text'


def test_csv_metadata_analysis():
    """Test CSV metadata analysis."""
    detector = FileDetector()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        csv_file = os.path.join(temp_dir, "test.csv")
        
        with open(csv_file, 'w') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'age'])
            writer.writerow([1, 'John', 30])
            writer.writerow([2, 'Jane', 25])
        
        metadata = detector.analyze_file_metadata(csv_file)
        
        assert metadata['file_type'] == 'csv'
        assert metadata['has_header'] == True
        assert metadata['delimiter'] == ','
        assert metadata['column_count'] == 3
        assert metadata['row_count'] == 2  # excluding header
        assert len(metadata['schema']) == 3


def test_json_metadata_analysis():
    """Test JSON metadata analysis."""
    detector = FileDetector()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        json_file = os.path.join(temp_dir, "test.json")
        
        data = [
            {"id": 1, "name": "John", "active": True},
            {"id": 2, "name": "Jane", "active": False}
        ]
        
        with open(json_file, 'w') as f:
            json.dump(data, f)
        
        metadata = detector.analyze_file_metadata(json_file)
        
        assert metadata['file_type'] == 'json'
        assert metadata['row_count'] == 2
        assert metadata['column_count'] == 3
        assert len(metadata['schema']) == 3


def test_directory_scan():
    """Test directory scanning functionality."""
    detector = FileDetector()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test files
        csv_file = os.path.join(temp_dir, "test.csv")
        json_file = os.path.join(temp_dir, "test.json")
        
        with open(csv_file, 'w') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name'])
            writer.writerow([1, 'John'])
        
        with open(json_file, 'w') as f:
            json.dump({"id": 1, "name": "John"}, f)
        
        results = detector.scan_directory(temp_dir)
        
        assert len(results) == 2
        file_types = [r['file_type'] for r in results]
        assert 'csv' in file_types
        assert 'json' in file_types


if __name__ == '__main__':
    test_file_type_detection()
    test_csv_metadata_analysis()
    test_json_metadata_analysis()
    test_directory_scan()
    print("All tests passed!")