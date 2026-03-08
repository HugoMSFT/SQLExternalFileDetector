"""Tests for web GUI functionality."""

import unittest
import json
import os
import tempfile
from unittest.mock import patch, MagicMock

from external_file_detection.web_gui import ExternalFileDetectionWebGUI


class TestWebGUI(unittest.TestCase):
    """Test web GUI functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Use temp dir as root so test temp files pass path validation
        self.test_root = tempfile.mkdtemp()
        self.web_gui = ExternalFileDetectionWebGUI(root_dir=self.test_root)
        self.app = self.web_gui.app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        # Create test data
        self.test_files = [
            {
                'file_path': '/test/sample.csv',
                'file_type': 'csv',
                'file_size': 100,
                'schema': [('id', 'int64'), ('name', 'object')],
                'has_header': True
            },
            {
                'file_path': '/test/sample.json',
                'file_type': 'json',
                'file_size': 200,
                'schema': [('id', 'int64'), ('data', 'object')]
            }
        ]
        
    def test_home_page(self):
        """Test home page loads correctly."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'External File Detection Tool', response.data)

    def test_initial_path_api(self):
        """Test /api/initial_path returns a valid directory."""
        response = self.client.get('/api/initial_path')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('path', data)
        self.assertTrue(len(data['path']) > 0)
        
    def test_browse_files_api(self):
        """Test browse files API endpoint."""
        with patch('os.listdir') as mock_listdir, \
             patch('os.path.isdir') as mock_isdir, \
             patch('os.path.getsize') as mock_getsize, \
             patch('os.path.exists') as mock_exists, \
             patch('os.path.abspath') as mock_abspath:
            
            mock_listdir.return_value = ['file1.csv', 'file2.json', 'folder1']
            mock_isdir.side_effect = lambda x: x.endswith('folder1')
            mock_getsize.return_value = 100
            mock_exists.return_value = True
            mock_abspath.return_value = '/test'
            
            response = self.client.get('/api/browse?path=/test')
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertTrue(data['success'])
            # On Windows os.path.abspath('/test') returns '\\test' or 'C:\\test'
            self.assertIn('test', data['current_path'])
            
            # Should have files and folders
            items = data['items']
            self.assertTrue(any(item['type'] == 'file' for item in items))
            self.assertTrue(any(item['type'] == 'directory' for item in items))
            
    def test_analyze_files_api(self):
        """Test analyze files API endpoint."""
        # Mock the file detector and path validation
        with patch.object(self.web_gui.file_detector, 'analyze_file_metadata') as mock_analyze, \
             patch('os.path.exists') as mock_exists, \
             patch('os.path.isfile') as mock_isfile, \
             patch('os.path.abspath') as mock_abspath:
            
            mock_analyze.return_value = self.test_files[0]
            mock_exists.return_value = True
            mock_isfile.return_value = True
            mock_abspath.return_value = '/test/sample.csv'
            
            response = self.client.post('/api/analyze_files', 
                                      json={'files': ['/test/sample.csv']})
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertTrue(data['success'])
            self.assertEqual(data['count'], 1)
            self.assertEqual(len(data['files']), 1)
            
    def test_analyze_folder_api(self):
        """Test analyze folder API endpoint."""
        # Mock the file detector and path validation
        with patch.object(self.web_gui.file_detector, 'scan_directory') as mock_scan, \
             patch('os.path.exists') as mock_exists, \
             patch('os.path.isdir') as mock_isdir, \
             patch('os.path.abspath') as mock_abspath:
            
            mock_scan.return_value = self.test_files
            mock_exists.return_value = True
            mock_isdir.return_value = True
            mock_abspath.return_value = '/test'
            
            response = self.client.post('/api/analyze_folder', 
                                      json={'folder': '/test'})
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertTrue(data['success'])
            self.assertEqual(data['count'], 2)
            self.assertEqual(len(data['files']), 2)
            
    def _create_csv(self, content='id,name\n1,John\n2,Jane\n', name='test.csv'):
        """Create a CSV file inside test_root."""
        path = os.path.join(self.test_root, name)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_preview_api(self):
        """Test file preview API via analyze-first flow."""
        csv_path = self._create_csv()

        resp = self.client.post('/api/analyze_files', json={'files': [csv_path]})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        stored_path = data['files'][0]['file_path']

        from urllib.parse import quote
        resp2 = self.client.get('/api/preview/' + quote(stored_path, safe=''))
        self.assertEqual(resp2.status_code, 200)
        data2 = json.loads(resp2.data)
        self.assertTrue(data2['success'])
        self.assertIn('id,name', data2['preview'])

    def test_sql_ddl_api(self):
        """Test SQL DDL API via analyze-first flow."""
        csv_path = self._create_csv()

        resp = self.client.post('/api/analyze_files', json={'files': [csv_path]})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        stored_path = data['files'][0]['file_path']

        from urllib.parse import quote
        resp2 = self.client.get(
            '/api/sql_ddl/' + quote(stored_path, safe='') +
            '?data_source=TestDS&target_platform=sql_server_2022')
        self.assertEqual(resp2.status_code, 200)
        data2 = json.loads(resp2.data)
        self.assertTrue(data2['success'])
        self.assertIn('statements', data2)

    def test_file_details_api(self):
        """Test file details API via analyze-first flow."""
        csv_path = self._create_csv()

        resp = self.client.post('/api/analyze_files', json={'files': [csv_path]})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        stored_path = data['files'][0]['file_path']

        from urllib.parse import quote
        resp2 = self.client.get('/api/file_details/' + quote(stored_path, safe=''))
        self.assertEqual(resp2.status_code, 200)
        data2 = json.loads(resp2.data)
        self.assertTrue(data2['success'])
        self.assertEqual(data2['details']['file_type'], 'csv')
        
    def test_preview_content_generation(self):
        """Test preview content generation for different file types."""
        # Test CSV preview
        csv_path = self._create_csv('id,name\n1,John\n2,Jane\n', 'preview_test.csv')
        csv_file = {
            'file_path': csv_path,
            'file_type': 'csv'
        }
        preview = self.web_gui._generate_preview_content(csv_file)
        self.assertIn('id,name', preview)
        self.assertIn('1,John', preview)

        # Test JSON preview
        json_path = os.path.join(self.test_root, 'preview_test.json')
        with open(json_path, 'w') as f:
            json.dump([{'id': 1, 'name': 'John'}], f)
        json_file = {
            'file_path': json_path,
            'file_type': 'json'
        }
        preview = self.web_gui._generate_preview_content(json_file)
        self.assertIn('"id": 1', preview)
        self.assertIn('"name": "John"', preview)
            
    def test_format_file_size(self):
        """Test file size formatting."""
        self.assertEqual(ExternalFileDetectionWebGUI.format_file_size(0), "0 B")
        self.assertEqual(ExternalFileDetectionWebGUI.format_file_size(1023), "1023.0 B")
        self.assertEqual(ExternalFileDetectionWebGUI.format_file_size(1024), "1.0 KB")
        self.assertEqual(ExternalFileDetectionWebGUI.format_file_size(1024 * 1024), "1.0 MB")
        self.assertEqual(ExternalFileDetectionWebGUI.format_file_size(1024 * 1024 * 1024), "1.0 GB")
        
    def test_error_handling(self):
        """Test error handling in API endpoints."""
        # Test preview with unregistered file
        response = self.client.get('/api/preview/nonexistent_file.csv')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('not found', data['error'].lower())

        # Test analyze with non-existent file
        response = self.client.post('/api/analyze_files',
                                    json={'files': ['/nonexistent/path/file.csv']})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])  # request itself succeeds
        self.assertEqual(data['files'][0]['file_type'], 'error')

        # Test analyze with no files
        response = self.client.post('/api/analyze_files', json={'files': []})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertFalse(data['success'])

    def test_sql_ddl_api_via_analyze_flow(self):
        """Test SQL DDL generation after analysing real files."""
        csv_path = self._create_csv('id,name,age\n1,Alice,30\n2,Bob,25\n', 'flow_test.csv')

        # First analyse the file
        resp = self.client.post('/api/analyze_files',
                                json={'files': [csv_path]})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data['success'])

        # Use the stored file_path (which is os.path.abspath-normalised)
        stored_path = data['files'][0]['file_path']

        # Now request DDL using the exact stored path
        from urllib.parse import quote
        resp2 = self.client.get(
            '/api/sql_ddl/' + quote(stored_path, safe='') +
            '?target_platform=sql_server_2022&schema=dbo&data_source=DS')
        self.assertEqual(resp2.status_code, 200)
        data2 = json.loads(resp2.data)
        self.assertTrue(data2['success'])
        stmts = data2.get('statements', {})
        self.assertIn('create_table', stmts)
        self.assertIn('CREATE TABLE', stmts['create_table'])
        # SQL Server mode should NOT have DISTRIBUTION clause
        self.assertNotIn('DISTRIBUTION', stmts['create_table'])

    def test_preview_table_api(self):
        """Test /api/preview_table returns columnar data."""
        csv_path = self._create_csv('x,y\n1,hello\n2,world\n', 'preview_tbl.csv')

        # Analyse first
        self.client.post('/api/analyze_files', json={'files': [csv_path]})
        # Preview
        resp = self.client.get('/api/preview_table/' + csv_path.replace('\\', '/') + '?rows=10')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data['success'])
        self.assertEqual(len(data['columns']), 2)
        self.assertEqual(len(data['rows']), 2)


if __name__ == '__main__':
    unittest.main()