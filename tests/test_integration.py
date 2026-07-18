"""Integration tests: analyze files end-to-end and verify SQL output."""

import os
import csv
import json
import tempfile
from unittest.mock import patch

from external_file_detection.file_detector import FileDetector
from external_file_detection.sql_generator import SQLGenerator
from external_file_detection.external_file_detector import ExternalFileDetectorApp


def test_csv_end_to_end():
    """Upload CSV -> analyze -> generate SQL -> validate SQL contains expected clauses."""
    with tempfile.TemporaryDirectory() as td:
        csv_path = os.path.join(td, "orders.csv")
        with open(csv_path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['order_id', 'customer', 'amount', 'date'])
            for i in range(10):
                w.writerow([i + 1, f'Customer_{i}', round(9.99 + i, 2), f'2025-01-{i+1:02d}'])

        app = ExternalFileDetectorApp()
        results = app.analyze_location(td)

        assert results['files_found'] == 1
        file_result = results['files'][0]
        assert 'error' not in file_result
        assert file_result['metadata']['file_type'] == 'csv'
        assert file_result['metadata']['column_count'] == 4
        assert 'CREATE EXTERNAL TABLE' in file_result['sql_ddl'] or 'CREATE TABLE' in file_result['sql_ddl']


def test_json_end_to_end():
    """Analyze JSON -> generate SQL -> verify DDL output."""
    with tempfile.TemporaryDirectory() as td:
        json_path = os.path.join(td, "users.json")
        data = [
            {"id": 1, "name": "Alice", "active": True},
            {"id": 2, "name": "Bob", "active": False},
        ]
        with open(json_path, 'w') as f:
            json.dump(data, f)

        detector = FileDetector()
        gen = SQLGenerator()

        metadata = detector.analyze_file_metadata(json_path)
        assert metadata['file_type'] == 'json'
        assert metadata['row_count'] == 2

        # Generate all statement types
        stmts = gen.generate_all_statements(metadata, table_name='users')
        assert 'create_table' in stmts
        assert 'CREATE TABLE' in stmts['create_table']
        assert '[id]' in stmts['create_table']
        assert '[name]' in stmts['create_table']


def test_multiple_files_analysis():
    """Analyze multiple files of different types."""
    with tempfile.TemporaryDirectory() as td:
        # CSV
        csv_path = os.path.join(td, "data.csv")
        with open(csv_path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['col_a', 'col_b'])
            w.writerow(['x', '1'])

        # JSON
        json_path = os.path.join(td, "data.json")
        with open(json_path, 'w') as f:
            json.dump([{"key": "val"}], f)

        # Text
        txt_path = os.path.join(td, "notes.txt")
        with open(txt_path, 'w') as f:
            f.write("line 1\nline 2\n")

        app = ExternalFileDetectorApp()
        results = app.analyze_files([csv_path, json_path])

        assert len(results) == 2
        types = {r['metadata']['file_type'] for r in results}
        assert types == {'csv', 'json'}
        for r in results:
            assert 'sql_ddl' in r
            assert r['sql_ddl'] is not None


def test_web_gui_upload_analyze_sql_flow():
    """Integration: upload via web GUI, analyze, then get SQL."""
    from external_file_detection.web_gui import ExternalFileDetectionWebGUI
    import io

    gui = ExternalFileDetectionWebGUI()
    gui.app.config['TESTING'] = True
    client = gui.app.test_client()

    csv_content = b'id,name,value\n1,alpha,10.5\n2,beta,20.3\n'

    # Upload
    resp = client.post('/api/upload', data={
        'files': (io.BytesIO(csv_content), 'test_upload.csv'),
    }, content_type='multipart/form-data')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success']
    assert data['count'] == 1
    stored_path = data['files'][0]['file_path']
    assert data['files'][0]['file_type'] == 'csv'
    assert os.path.exists(stored_path)

    # Get SQL DDL
    from urllib.parse import quote
    resp2 = client.get(
        '/api/sql_ddl/' + quote(stored_path.lstrip('/'), safe='/') +
        '?target_platform=sql_server_2022&data_source=TestDS')
    assert resp2.status_code == 200
    data2 = json.loads(resp2.data)
    assert data2['success']
    stmts = data2.get('statements', {})
    assert 'create_table' in stmts
    assert 'CREATE TABLE' in stmts['create_table']


def test_remote_analyze_files_uses_managed_temporary_directory():
    """Remote single-file analysis downloads safely and restores source paths."""
    downloaded_paths = []

    class FakeRemoteHandler:
        def list_files(self, path):
            return [path]

        def get_file_info(self, path):
            return {}

        def download_file(self, source_path, local_path):
            assert os.path.isdir(os.path.dirname(local_path))
            downloaded_paths.append(local_path)
            with open(local_path, 'w', encoding='utf-8') as handle:
                handle.write('id,name\n1,Alice\n')
            return local_path

    app = ExternalFileDetectorApp()
    with patch(
        'external_file_detection.external_file_detector.StorageFactory.create_handler',
        return_value=FakeRemoteHandler(),
    ):
        results = app.analyze_files(['s3://bucket/data.csv'])

    assert len(results) == 1
    assert 'error' not in results[0]
    assert results[0]['metadata']['file_path'] == 's3://bucket/data.csv'
    assert results[0]['metadata']['file_name'] == 'data.csv'
    assert not os.path.exists(downloaded_paths[0])


def test_remote_download_uses_filesystem_safe_temporary_name():
    """URL-decoded reserved characters must not enter Windows temp paths."""
    downloaded_paths = []

    class FakeRemoteHandler:
        def download_file(self, source_path, local_path):
            downloaded_paths.append(local_path)
            with open(local_path, 'w', encoding='utf-8') as handle:
                handle.write('id,name\n1,Alice\n')
            return local_path

    app = ExternalFileDetectorApp()
    with patch(
        'external_file_detection.external_file_detector.StorageFactory.create_handler',
        return_value=FakeRemoteHandler(),
    ):
        results = app.analyze_files(['s3://bucket/folder/a%3Fb.csv'])

    assert 'error' not in results[0]
    assert results[0]['metadata']['file_name'] == 'a?b.csv'
    assert results[0]['metadata']['file_type'] == 'csv'
    assert os.path.basename(downloaded_paths[0]).endswith('.csv')
    assert '?' not in os.path.basename(downloaded_paths[0])


def test_detector_metadata_errors_fail_the_file_analysis():
    """Parse failures must not produce success-shaped SQL results."""
    with tempfile.TemporaryDirectory() as td:
        broken_path = os.path.join(td, 'broken.json')
        with open(broken_path, 'w', encoding='utf-8') as handle:
            handle.write('{not valid json}')

        result = ExternalFileDetectorApp().analyze_files([broken_path])[0]

    assert 'error' in result
    assert 'Failed to analyze file' in result['error']
    assert result['sql_ddl'] is None
    assert result['metadata']['file_type'] == 'json'
