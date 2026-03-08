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
        with open(csv_file, 'w', newline='') as f:
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
        
        with open(csv_file, 'w', newline='') as f:
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
        
        with open(csv_file, 'w', newline='') as f:
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


def test_unknown_extension():
    """Test that unknown extensions fall back to content-based detection."""
    detector = FileDetector()
    with tempfile.TemporaryDirectory() as temp_dir:
        unk = os.path.join(temp_dir, "data.xyz")
        with open(unk, 'w') as f:
            f.write("just some text\n")
        result = detector.detect_file_type(unk)
        # Content-based detection may classify this as text or csv
        assert result in ('text', 'csv', 'unknown')


def test_empty_file():
    """Test analysis of an empty file does not crash."""
    detector = FileDetector()
    with tempfile.TemporaryDirectory() as temp_dir:
        empty = os.path.join(temp_dir, "empty.csv")
        with open(empty, 'w') as f:
            pass  # 0 bytes
        metadata = detector.analyze_file_metadata(empty)
        assert metadata['file_type'] == 'csv'
        assert metadata['file_size'] == 0


def test_corrupted_json():
    """Test analysis of a corrupted JSON file."""
    detector = FileDetector()
    with tempfile.TemporaryDirectory() as temp_dir:
        bad = os.path.join(temp_dir, "bad.json")
        with open(bad, 'w') as f:
            f.write("{invalid json content!!!}")
        metadata = detector.analyze_file_metadata(bad)
        assert metadata['file_type'] == 'json'
        # Should still return metadata (possibly with an error key)


def test_csv_with_mixed_delimiters():
    """Test CSV detection with tab delimiter."""
    detector = FileDetector()
    with tempfile.TemporaryDirectory() as temp_dir:
        tsv = os.path.join(temp_dir, "data.tsv")
        with open(tsv, 'w') as f:
            f.write("id\tname\tage\n1\tAlice\t30\n2\tBob\t25\n")
        metadata = detector.analyze_file_metadata(tsv)
        assert metadata['file_type'] == 'csv'
        assert metadata['delimiter'] == '\t'


def test_delta_directory_detection():
    """Test Delta table directory detection."""
    detector = FileDetector()
    with tempfile.TemporaryDirectory() as temp_dir:
        delta_dir = os.path.join(temp_dir, "my_table")
        os.makedirs(os.path.join(delta_dir, "_delta_log"))
        # Create a dummy parquet file
        with open(os.path.join(delta_dir, "part-0.parquet"), 'wb') as f:
            f.write(b'PAR1' + b'\x00' * 100)
        result = detector.detect_file_type(delta_dir)
        assert result == 'delta'


def test_non_delta_directory():
    """Test that a regular directory returns 'unknown'."""
    detector = FileDetector()
    with tempfile.TemporaryDirectory() as temp_dir:
        sub = os.path.join(temp_dir, "subdir")
        os.makedirs(sub)
        assert detector.detect_file_type(sub) == 'unknown'


def test_encoding_detection():
    """Test encoding detection returns a tuple."""
    detector = FileDetector()
    with tempfile.TemporaryDirectory() as temp_dir:
        f_path = os.path.join(temp_dir, "utf8.txt")
        with open(f_path, 'w', encoding='utf-8') as f:
            f.write("Hello ñ world\n")
        enc, conf = detector.detect_encoding(f_path)
        assert isinstance(enc, str)
        assert isinstance(conf, float)
        assert 0.0 <= conf <= 1.0


def test_nullable_column_detection():
    """Test that nullable columns are detected in CSV."""
    detector = FileDetector()
    with tempfile.TemporaryDirectory() as temp_dir:
        csv_file = os.path.join(temp_dir, "nullable.csv")
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'optional'])
            writer.writerow([1, 'Alice', 'yes'])
            writer.writerow([2, 'Bob', ''])
        metadata = detector.analyze_file_metadata(csv_file)
        assert 'optional' in metadata.get('nullable_columns', [])


if __name__ == '__main__':
    test_file_type_detection()
    test_csv_metadata_analysis()
    test_json_metadata_analysis()
    test_directory_scan()
    test_unknown_extension()
    test_empty_file()
    test_corrupted_json()
    test_csv_with_mixed_delimiters()
    test_delta_directory_detection()
    test_non_delta_directory()
    test_encoding_detection()
    test_nullable_column_detection()
    print("All tests passed!")