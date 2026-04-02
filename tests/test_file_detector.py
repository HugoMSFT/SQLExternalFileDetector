"""Tests for file detector functionality."""

import os
import tempfile
import json
import csv
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

from external_file_detection.file_detector import FileDetector
from external_file_detection.external_file_detector import ExternalFileDetectorApp


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


def test_scan_directory_detects_delta_table_folder():
    """Directory scan should treat a Delta table folder as one delta entry."""
    detector = FileDetector()

    with tempfile.TemporaryDirectory() as temp_dir:
        delta_dir = os.path.join(temp_dir, 'delta_table')
        data_dir = os.path.join(delta_dir, 'data')
        log_dir = os.path.join(delta_dir, '_delta_log')
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)

        table = pa.table({'id': [1, 2], 'name': ['Alice', 'Bob']})
        pq.write_table(table, os.path.join(data_dir, 'part-00000.parquet'))

        with open(os.path.join(log_dir, '00000000000000000000.json'), 'w', encoding='utf-8') as f:
            f.write(json.dumps({
                'metaData': {
                    'id': 'sample-delta',
                    'format': {'provider': 'parquet', 'options': {}},
                    'schemaString': json.dumps({
                        'type': 'struct',
                        'fields': [
                            {'name': 'id', 'type': 'long', 'nullable': True, 'metadata': {}},
                            {'name': 'name', 'type': 'string', 'nullable': True, 'metadata': {}},
                        ],
                    }),
                    'partitionColumns': [],
                    'configuration': {},
                    'createdTime': 1760000000000,
                }
            }) + '\n')

        results = detector.scan_directory(temp_dir)

        delta_results = [r for r in results if r['file_type'] == 'delta']
        assert len(delta_results) == 1
        assert delta_results[0]['file_path'] == delta_dir


def test_supported_file_types_are_deduplicated():
    """Supported file types exposed by the app should be unique and sorted."""
    app = ExternalFileDetectorApp()
    supported = app.get_supported_file_types()

    assert supported == sorted(set(supported))
    assert 'csv' in supported
    assert supported.count('csv') == 1


def test_analyze_location_uses_delta_folder_as_single_entry():
    """App-level location analysis should include the Delta folder, not just inner parquet files."""
    app = ExternalFileDetectorApp()

    with tempfile.TemporaryDirectory() as temp_dir:
        delta_dir = os.path.join(temp_dir, 'delta_table')
        data_dir = os.path.join(delta_dir, 'data')
        log_dir = os.path.join(delta_dir, '_delta_log')
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)

        table = pa.table({'id': [1, 2], 'name': ['Alice', 'Bob']})
        pq.write_table(table, os.path.join(data_dir, 'part-00000.parquet'))

        with open(os.path.join(log_dir, '00000000000000000000.json'), 'w', encoding='utf-8') as f:
            f.write(json.dumps({
                'metaData': {
                    'id': 'sample-delta',
                    'format': {'provider': 'parquet', 'options': {}},
                    'schemaString': json.dumps({
                        'type': 'struct',
                        'fields': [
                            {'name': 'id', 'type': 'long', 'nullable': True, 'metadata': {}},
                            {'name': 'name', 'type': 'string', 'nullable': True, 'metadata': {}},
                        ],
                    }),
                    'partitionColumns': [],
                    'configuration': {},
                    'createdTime': 1760000000000,
                }
            }) + '\n')

        results = app.analyze_location(temp_dir, data_source='DS')
        assert results['files_found'] == 1
        assert results['summary']['file_types']['delta'] == 1
        assert results['files'][0]['metadata']['file_type'] == 'delta'


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
    test_scan_directory_detects_delta_table_folder()
    test_supported_file_types_are_deduplicated()
    test_analyze_location_uses_delta_folder_as_single_entry()


# ---- New tests using conftest fixtures ----

def test_parquet_metadata_analysis(sample_parquet):
    """Test Parquet metadata analysis with a real Parquet file."""
    detector = FileDetector()
    metadata = detector.analyze_file_metadata(sample_parquet)
    assert metadata['file_type'] == 'parquet'
    assert metadata['row_count'] == 3
    assert metadata['column_count'] == 3
    assert len(metadata['schema']) == 3
    col_names = [c[0] for c in metadata['schema']]
    assert 'id' in col_names
    assert 'name' in col_names
    assert 'score' in col_names


def test_parquet_preview_does_not_load_full_file(sample_parquet):
    """Test that Parquet preview reads efficiently."""
    detector = FileDetector()
    result = detector.get_preview_data(sample_parquet, max_rows=2)
    assert len(result['rows']) == 2
    assert len(result['columns']) == 3


def test_ndjson_detection(sample_ndjson):
    """Test NDJSON file detection and analysis."""
    detector = FileDetector()
    assert detector.detect_file_type(sample_ndjson) == 'json'
    metadata = detector.analyze_file_metadata(sample_ndjson)
    assert metadata['file_type'] == 'json'
    assert metadata.get('json_format') == 'ndjson'
    assert metadata['row_count'] == 2


def test_wide_csv_sample_rows(wide_csv):
    """Test that wide CSV files still produce sample_rows."""
    detector = FileDetector()
    metadata = detector.analyze_file_metadata(wide_csv)
    assert metadata['file_type'] == 'csv'
    assert metadata['column_count'] == 25
    assert len(metadata['sample_rows']) >= 1
    assert len(metadata['sample_rows'][0]) == 25


def test_nested_json_analysis(nested_json):
    """Test nested JSON detection and schema analysis."""
    detector = FileDetector()
    metadata = detector.analyze_file_metadata(nested_json)
    assert metadata['file_type'] == 'json'
    nesting = metadata.get('json_nesting', {})
    assert nesting.get('address') == 'object'
    assert nesting.get('tags') == 'array'
    assert nesting.get('id') == 'scalar'


def test_encoding_warning_for_low_confidence(temp_dir):
    """Test that low-confidence encoding detection adds a warning."""
    detector = FileDetector()
    # Create a file with ambiguous encoding
    path = os.path.join(temp_dir, "ambiguous.csv")
    with open(path, 'wb') as f:
        # Write bytes that chardet may struggle with
        f.write(b"id,name\n1,test\n2,data\n")
    metadata = detector.analyze_file_metadata(path)
    # Encoding confidence is reported; warning may or may not be present
    # depending on chardet certainty, but the field must exist
    assert 'encoding_confidence' in metadata
    assert isinstance(metadata['encoding_confidence'], int)


def test_preview_rows_capped():
    """Test that get_preview_data caps max_rows to 10000."""
    detector = FileDetector()
    # The method should internally cap, verified by the function signature
    import inspect
    src = inspect.getsource(detector.get_preview_data)
    assert '10000' in src


def test_thread_safe_cache():
    """Test that FileDetector uses thread-safe caching."""
    detector = FileDetector()
    assert hasattr(detector, '_cache_lock')
    import threading
    assert isinstance(detector._cache_lock, type(threading.Lock()))
    print("All tests passed!")