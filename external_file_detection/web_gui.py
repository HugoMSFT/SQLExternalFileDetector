"""Web-based GUI for External File Detection.

Inspired by ParquetViewer, this provides a user-friendly web interface for:
- Selecting files or folders
- Previewing file metadata 
- Generating T-SQL DDL statements
"""

import os
import json
import tempfile
from typing import Dict, List, Any, Optional
from pathlib import Path
from urllib.parse import quote, unquote
import mimetypes

try:
    from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

from .external_file_detector import ExternalFileDetectorApp
from .file_detector import FileDetector


class ExternalFileDetectionWebGUI:
    """Web-based GUI application for External File Detection."""
    
    def __init__(self):
        """Initialize the web GUI application."""
        if not FLASK_AVAILABLE:
            raise ImportError("Flask is required for the web GUI. Install with: pip install flask")
            
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.detector_app = ExternalFileDetectorApp()
        self.file_detector = FileDetector()
        
        # Current session data
        self.current_files: List[Dict[str, Any]] = []
        
        self.setup_routes()
        
    def setup_routes(self):
        """Set up Flask routes."""
        
        @self.app.route('/')
        def index():
            """Main page."""
            return render_template('index.html')
            
        @self.app.route('/api/browse')
        def browse_files():
            """Browse files in a directory."""
            path = request.args.get('path', os.path.expanduser('~'))
            try:
                items = []
                
                # Add parent directory option if not at root
                if path != '/' and path != os.path.expanduser('~'):
                    parent = os.path.dirname(path)
                    items.append({
                        'name': '..',
                        'path': parent,
                        'type': 'directory',
                        'size': 0
                    })
                
                # List directory contents
                for item in sorted(os.listdir(path)):
                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path):
                        items.append({
                            'name': item,
                            'path': item_path,
                            'type': 'directory',
                            'size': 0
                        })
                    else:
                        # Check if file is supported
                        file_type = self.file_detector.detect_file_type(item_path)
                        if file_type != 'unknown':
                            size = os.path.getsize(item_path) if os.path.exists(item_path) else 0
                            items.append({
                                'name': item,
                                'path': item_path,
                                'type': 'file',
                                'file_type': file_type,
                                'size': size
                            })
                
                return jsonify({
                    'success': True,
                    'current_path': path,
                    'items': items
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                })
                
        @self.app.route('/api/analyze_files', methods=['POST'])
        def analyze_files():
            """Analyze selected files."""
            try:
                data = request.get_json()
                file_paths = data.get('files', [])
                
                if not file_paths:
                    return jsonify({'success': False, 'error': 'No files provided'})
                
                # Clear current files
                self.current_files = []
                
                # Analyze each file
                for file_path in file_paths:
                    try:
                        metadata = self.file_detector.analyze_file_metadata(file_path)
                        self.current_files.append(metadata)
                    except Exception as e:
                        # Add error entry
                        error_metadata = {
                            'file_path': file_path,
                            'file_type': 'error',
                            'file_size': 0,
                            'error': str(e)
                        }
                        self.current_files.append(error_metadata)
                
                return jsonify({
                    'success': True,
                    'files': self.current_files,
                    'count': len(self.current_files)
                })
                
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
                
        @self.app.route('/api/analyze_folder', methods=['POST'])
        def analyze_folder():
            """Analyze all supported files in a folder."""
            try:
                data = request.get_json()
                folder_path = data.get('folder')
                
                if not folder_path:
                    return jsonify({'success': False, 'error': 'No folder provided'})
                
                # Clear current files
                self.current_files = []
                
                # Scan directory
                self.current_files = self.file_detector.scan_directory(folder_path)
                
                return jsonify({
                    'success': True,
                    'files': self.current_files,
                    'count': len(self.current_files)
                })
                
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
                
        @self.app.route('/api/preview/<path:file_path>')
        def preview_file(file_path):
            """Get file preview."""
            try:
                file_path = unquote(file_path)
                
                # Find file in current files
                file_data = None
                for f in self.current_files:
                    if f['file_path'] == file_path:
                        file_data = f
                        break
                        
                if not file_data:
                    return jsonify({'success': False, 'error': 'File not found in current analysis'})
                    
                if 'error' in file_data:
                    return jsonify({
                        'success': False,
                        'error': file_data['error']
                    })
                
                preview_content = self._generate_preview_content(file_data)
                
                return jsonify({
                    'success': True,
                    'preview': preview_content,
                    'file_type': file_data.get('file_type', 'unknown')
                })
                
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
                
        @self.app.route('/api/sql_ddl/<path:file_path>')
        def get_sql_ddl(file_path):
            """Get SQL DDL for a file."""
            try:
                file_path = unquote(file_path)
                data_source = request.args.get('data_source', 'MyDataSource')
                
                # Find file in current files
                file_data = None
                for f in self.current_files:
                    if f['file_path'] == file_path:
                        file_data = f
                        break
                        
                if not file_data:
                    return jsonify({'success': False, 'error': 'File not found in current analysis'})
                    
                if 'error' in file_data:
                    return jsonify({
                        'success': False,
                        'error': file_data['error']
                    })
                
                # Generate SQL DDL
                sql_ddl = self.detector_app.sql_generator.generate_complete_ddl(
                    file_data,
                    data_source=data_source,
                    location=os.path.basename(file_data['file_path'])
                )
                
                return jsonify({
                    'success': True,
                    'sql_ddl': sql_ddl
                })
                
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
                
        @self.app.route('/api/file_details/<path:file_path>')
        def get_file_details(file_path):
            """Get detailed file information."""
            try:
                file_path = unquote(file_path)
                
                # Find file in current files
                file_data = None
                for f in self.current_files:
                    if f['file_path'] == file_path:
                        file_data = f
                        break
                        
                if not file_data:
                    return jsonify({'success': False, 'error': 'File not found in current analysis'})
                
                return jsonify({
                    'success': True,
                    'details': file_data
                })
                
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
                
    def _generate_preview_content(self, file_data: Dict[str, Any]) -> str:
        """Generate preview content for a file."""
        file_path = file_data['file_path']
        file_type = file_data.get('file_type', 'unknown')
        
        try:
            if file_type in ['csv', 'txt', 'json']:
                # Show text preview
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    # Read first 50 lines or 5KB, whichever is smaller
                    content = []
                    for i, line in enumerate(f):
                        if i >= 50:
                            content.append("... (truncated)")
                            break
                        content.append(line.rstrip())
                        if len(''.join(content)) > 5000:
                            content.append("... (truncated)")
                            break
                    
                    return '\n'.join(content)
                    
            elif file_type == 'parquet':
                # Show parquet metadata
                try:
                    import pyarrow.parquet as pq
                    parquet_file = pq.ParquetFile(file_path)
                    
                    preview_content = []
                    file_name = os.path.basename(file_path)
                    preview_content.append(f"Parquet File: {file_name}")
                    preview_content.append(f"Rows: {parquet_file.metadata.num_rows:,}")
                    preview_content.append(f"Columns: {len(parquet_file.schema)}")
                    preview_content.append("")
                    preview_content.append("Schema:")
                    for field in parquet_file.schema:
                        preview_content.append(f"  {field.name}: {field.type}")
                    
                    # Show sample data if possible
                    try:
                        table = parquet_file.read()
                        df = table.to_pandas().head(10)
                        preview_content.append("")
                        preview_content.append("Sample Data (first 10 rows):")
                        preview_content.append(df.to_string())
                    except Exception:
                        preview_content.append("")
                        preview_content.append("Could not load sample data")
                    
                    return '\n'.join(preview_content)
                    
                except Exception as e:
                    return f"Error reading Parquet file: {str(e)}"
                    
            else:
                return f"Preview not available for {file_type} files"
                
        except Exception as e:
            return f"Error loading preview: {str(e)}"
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """Format file size in human readable format."""
        if size_bytes == 0:
            return "0 B"
        
        units = ['B', 'KB', 'MB', 'GB']
        i = 0
        while size_bytes >= 1024 and i < len(units) - 1:
            size_bytes /= 1024
            i += 1
            
        return f"{size_bytes:.1f} {units[i]}"
        
    def run(self, host='127.0.0.1', port=5000, debug=False):
        """Run the web application."""
        # Create templates directory and files if they don't exist
        self._create_templates()
        
        print(f"Starting External File Detection Web GUI...")
        print(f"Open your browser and go to: http://{host}:{port}")
        
        self.app.run(host=host, port=port, debug=debug)
        
    def _create_templates(self):
        """Create HTML templates."""
        templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
        os.makedirs(templates_dir, exist_ok=True)
        
        # Create index.html template
        index_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>External File Detection Tool</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .header {
            background: #2563eb;
            color: white;
            padding: 20px;
        }
        
        .header h1 {
            margin: 0;
            font-size: 24px;
        }
        
        .toolbar {
            padding: 20px;
            background: #f8fafc;
            border-bottom: 1px solid #e5e7eb;
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }
        
        .btn {
            padding: 8px 16px;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            background: white;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            font-size: 14px;
        }
        
        .btn:hover {
            background: #f3f4f6;
        }
        
        .btn-primary {
            background: #2563eb;
            color: white;
            border-color: #2563eb;
        }
        
        .btn-primary:hover {
            background: #1d4ed8;
        }
        
        .input-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .input-group label {
            font-weight: 500;
        }
        
        .input-group input {
            padding: 6px 12px;
            border: 1px solid #d1d5db;
            border-radius: 4px;
            font-size: 14px;
        }
        
        .main-content {
            display: flex;
            height: 600px;
        }
        
        .sidebar {
            width: 350px;
            border-right: 1px solid #e5e7eb;
            overflow-y: auto;
        }
        
        .content-area {
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        
        .tabs {
            display: flex;
            border-bottom: 1px solid #e5e7eb;
        }
        
        .tab {
            padding: 12px 20px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
        }
        
        .tab.active {
            border-bottom-color: #2563eb;
            background: #eff6ff;
        }
        
        .tab-content {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
        }
        
        .file-list {
            padding: 0;
        }
        
        .file-item {
            padding: 12px 20px;
            border-bottom: 1px solid #e5e7eb;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .file-item:hover {
            background: #f8fafc;
        }
        
        .file-item.selected {
            background: #eff6ff;
            border-left: 3px solid #2563eb;
        }
        
        .file-info {
            flex: 1;
        }
        
        .file-name {
            font-weight: 500;
            margin-bottom: 4px;
        }
        
        .file-meta {
            font-size: 12px;
            color: #6b7280;
        }
        
        .file-type-badge {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            text-transform: uppercase;
        }
        
        .file-type-csv { background: #dbeafe; color: #1e40af; }
        .file-type-json { background: #f3e8ff; color: #7c3aed; }
        .file-type-parquet { background: #dcfce7; color: #166534; }
        .file-type-text { background: #f3f4f6; color: #4b5563; }
        .file-type-error { background: #fecaca; color: #dc2626; }
        
        .preview-content, .sql-content, .details-content {
            background: #f8fafc;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 16px;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 13px;
            line-height: 1.5;
            white-space: pre-wrap;
            max-height: 500px;
            overflow-y: auto;
        }
        
        .status-bar {
            padding: 10px 20px;
            background: #f8fafc;
            border-top: 1px solid #e5e7eb;
            font-size: 14px;
            color: #6b7280;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: #6b7280;
        }
        
        .error {
            color: #dc2626;
            background: #fef2f2;
            padding: 12px;
            border-radius: 6px;
            border: 1px solid #fecaca;
        }
        
        .hidden {
            display: none !important;
        }
        
        .browser-content {
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
        }
        
        .browser-item {
            padding: 8px 12px;
            border-bottom: 1px solid #f3f4f6;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .browser-item:hover {
            background: #f8fafc;
        }
        
        .browser-item.directory {
            font-weight: 500;
        }
        
        .copy-btn {
            float: right;
            margin-bottom: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>External File Detection Tool</h1>
        </div>
        
        <div class="toolbar">
            <button class="btn btn-primary" onclick="showFileBrowser()">Browse Files</button>
            <button class="btn" onclick="analyzeFolder()">Analyze Current Folder</button>
            <div class="input-group">
                <label for="dataSource">Data Source:</label>
                <input type="text" id="dataSource" value="MyDataSource" placeholder="Enter data source name">
            </div>
            <button class="btn" onclick="clearFiles()">Clear</button>
        </div>
        
        <div class="main-content">
            <div class="sidebar">
                <div id="fileList" class="file-list">
                    <div class="loading">Select files to analyze</div>
                </div>
            </div>
            
            <div class="content-area">
                <div class="tabs">
                    <div class="tab active" onclick="showTab('preview')">Preview</div>
                    <div class="tab" onclick="showTab('sql')">T-SQL DDL</div>
                    <div class="tab" onclick="showTab('details')">Details</div>
                </div>
                
                <div class="tab-content">
                    <div id="previewTab" class="tab-pane">
                        <div class="preview-content" id="previewContent">Select a file to see preview</div>
                    </div>
                    
                    <div id="sqlTab" class="tab-pane hidden">
                        <button class="btn copy-btn" onclick="copySqlToClipboard()">Copy to Clipboard</button>
                        <div class="sql-content" id="sqlContent">Select a file to see T-SQL DDL</div>
                    </div>
                    
                    <div id="detailsTab" class="tab-pane hidden">
                        <div class="details-content" id="detailsContent">Select a file to see details</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="status-bar">
            <span id="statusText">Ready</span>
        </div>
    </div>
    
    <!-- File Browser Modal -->
    <div id="browserModal" class="hidden" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1000; display: flex; align-items: center; justify-content: center;">
        <div style="background: white; border-radius: 8px; width: 600px; max-height: 80vh; overflow: hidden;">
            <div style="padding: 20px; border-bottom: 1px solid #e5e7eb;">
                <h2 style="margin: 0;">Browse Files</h2>
                <div style="margin-top: 10px; font-size: 14px; color: #6b7280;" id="currentPath"></div>
            </div>
            
            <div class="browser-content" id="browserContent">
                <div class="loading">Loading...</div>
            </div>
            
            <div style="padding: 20px; border-top: 1px solid #e5e7eb; display: flex; justify-content: space-between;">
                <button class="btn" onclick="selectCurrentFolder()">Select This Folder</button>
                <div>
                    <button class="btn" onclick="hideBrowser()">Cancel</button>
                    <button class="btn btn-primary" onclick="analyzeSelectedFiles()">Analyze Selected</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentFiles = [];
        let selectedFiles = [];
        let currentPath = '';
        let selectedFileIndex = -1;
        
        function setStatus(message) {
            document.getElementById('statusText').textContent = message;
        }
        
        function showTab(tabName) {
            // Hide all tabs
            document.querySelectorAll('.tab-pane').forEach(pane => {
                pane.classList.add('hidden');
            });
            
            // Remove active class from all tabs
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected tab
            document.getElementById(tabName + 'Tab').classList.remove('hidden');
            event.target.classList.add('active');
        }
        
        function showFileBrowser() {
            document.getElementById('browserModal').classList.remove('hidden');
            browseDirectory(currentPath || '/home/runner');
        }
        
        function hideBrowser() {
            document.getElementById('browserModal').classList.add('hidden');
        }
        
        function browseDirectory(path) {
            const content = document.getElementById('browserContent');
            content.innerHTML = '<div class="loading">Loading...</div>';
            
            fetch(`/api/browse?path=${encodeURIComponent(path)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        currentPath = data.current_path;
                        document.getElementById('currentPath').textContent = currentPath;
                        
                        content.innerHTML = '';
                        data.items.forEach(item => {
                            const div = document.createElement('div');
                            div.className = `browser-item ${item.type}`;
                            
                            if (item.type === 'directory') {
                                div.innerHTML = `
                                    <span>📁</span>
                                    <span>${item.name}</span>
                                `;
                                div.onclick = () => browseDirectory(item.path);
                            } else {
                                div.innerHTML = `
                                    <input type="checkbox" onchange="toggleFileSelection('${item.path}')">
                                    <span>📄</span>
                                    <span>${item.name}</span>
                                    <span class="file-type-badge file-type-${item.file_type}">${item.file_type}</span>
                                `;
                            }
                            
                            content.appendChild(div);
                        });
                    } else {
                        content.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                    }
                })
                .catch(error => {
                    content.innerHTML = `<div class="error">Error: ${error.message}</div>`;
                });
        }
        
        function toggleFileSelection(filePath) {
            const index = selectedFiles.indexOf(filePath);
            if (index > -1) {
                selectedFiles.splice(index, 1);
            } else {
                selectedFiles.push(filePath);
            }
        }
        
        function selectCurrentFolder() {
            if (currentPath) {
                analyzeFolder(currentPath);
                hideBrowser();
            }
        }
        
        function analyzeSelectedFiles() {
            if (selectedFiles.length === 0) {
                alert('Please select files to analyze');
                return;
            }
            
            setStatus('Analyzing selected files...');
            
            fetch('/api/analyze_files', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    files: selectedFiles
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    currentFiles = data.files;
                    updateFileList();
                    setStatus(`Analyzed ${data.count} files`);
                    hideBrowser();
                    selectedFiles = [];
                } else {
                    setStatus(`Error: ${data.error}`);
                }
            })
            .catch(error => {
                setStatus(`Error: ${error.message}`);
            });
        }
        
        function analyzeFolder(folderPath = null) {
            const folder = folderPath || currentPath;
            if (!folder) {
                alert('No folder selected');
                return;
            }
            
            setStatus('Analyzing folder...');
            
            fetch('/api/analyze_folder', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    folder: folder
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    currentFiles = data.files;
                    updateFileList();
                    setStatus(`Found ${data.count} supported files`);
                } else {
                    setStatus(`Error: ${data.error}`);
                }
            })
            .catch(error => {
                setStatus(`Error: ${error.message}`);
            });
        }
        
        function updateFileList() {
            const fileList = document.getElementById('fileList');
            
            if (currentFiles.length === 0) {
                fileList.innerHTML = '<div class="loading">No files analyzed</div>';
                return;
            }
            
            fileList.innerHTML = '';
            
            currentFiles.forEach((file, index) => {
                const div = document.createElement('div');
                div.className = 'file-item';
                div.onclick = () => selectFile(index);
                
                const fileName = file.file_path.split('/').pop();
                const fileSize = formatFileSize(file.file_size || 0);
                const hasError = 'error' in file;
                
                div.innerHTML = `
                    <div class="file-info">
                        <div class="file-name">${fileName}</div>
                        <div class="file-meta">${fileSize} • ${file.file_path}</div>
                    </div>
                    <div class="file-type-badge file-type-${hasError ? 'error' : file.file_type}">
                        ${hasError ? 'error' : file.file_type}
                    </div>
                `;
                
                fileList.appendChild(div);
            });
        }
        
        function selectFile(index) {
            selectedFileIndex = index;
            
            // Update UI selection
            document.querySelectorAll('.file-item').forEach((item, i) => {
                if (i === index) {
                    item.classList.add('selected');
                } else {
                    item.classList.remove('selected');
                }
            });
            
            // Load file data
            const file = currentFiles[index];
            loadFilePreview(file);
            loadFileSql(file);
            loadFileDetails(file);
        }
        
        function loadFilePreview(file) {
            const content = document.getElementById('previewContent');
            content.textContent = 'Loading preview...';
            
            if ('error' in file) {
                content.textContent = `Error: ${file.error}`;
                return;
            }
            
            fetch(`/api/preview/${encodeURIComponent(file.file_path)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        content.textContent = data.preview;
                    } else {
                        content.textContent = `Error: ${data.error}`;
                    }
                })
                .catch(error => {
                    content.textContent = `Error: ${error.message}`;
                });
        }
        
        function loadFileSql(file) {
            const content = document.getElementById('sqlContent');
            content.textContent = 'Loading SQL DDL...';
            
            if ('error' in file) {
                content.textContent = `-- Cannot generate SQL DDL\\n-- Error: ${file.error}`;
                return;
            }
            
            const dataSource = document.getElementById('dataSource').value || 'MyDataSource';
            
            fetch(`/api/sql_ddl/${encodeURIComponent(file.file_path)}?data_source=${encodeURIComponent(dataSource)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        content.textContent = data.sql_ddl;
                    } else {
                        content.textContent = `-- Error generating SQL DDL: ${data.error}`;
                    }
                })
                .catch(error => {
                    content.textContent = `-- Error: ${error.message}`;
                });
        }
        
        function loadFileDetails(file) {
            const content = document.getElementById('detailsContent');
            
            let details = [];
            details.push(`File Path: ${file.file_path}`);
            details.push(`File Type: ${file.file_type || 'unknown'}`);
            details.push(`File Size: ${formatFileSize(file.file_size || 0)}`);
            
            if (file.row_count != null) {
                details.push(`Rows: ${file.row_count.toLocaleString()}`);
            }
            
            if (file.column_count != null) {
                details.push(`Columns: ${file.column_count}`);
            }
            
            if (file.delimiter) {
                details.push(`Delimiter: '${file.delimiter}'`);
            }
            
            if (file.encoding) {
                details.push(`Encoding: ${file.encoding}`);
            }
            
            if (file.has_header != null) {
                details.push(`Has Header: ${file.has_header}`);
            }
            
            if (file.compression) {
                details.push(`Compression: ${file.compression}`);
            }
            
            if (file.schema && file.schema.length > 0) {
                details.push('');
                details.push('Schema:');
                file.schema.forEach(([name, type]) => {
                    details.push(`  ${name}: ${type}`);
                });
            }
            
            if (file.error) {
                details.push('');
                details.push(`Error: ${file.error}`);
            }
            
            content.textContent = details.join('\\n');
        }
        
        function copySqlToClipboard() {
            const content = document.getElementById('sqlContent').textContent;
            navigator.clipboard.writeText(content).then(() => {
                setStatus('SQL DDL copied to clipboard');
            }).catch(() => {
                setStatus('Failed to copy to clipboard');
            });
        }
        
        function clearFiles() {
            currentFiles = [];
            selectedFileIndex = -1;
            updateFileList();
            
            document.getElementById('previewContent').textContent = 'Select a file to see preview';
            document.getElementById('sqlContent').textContent = 'Select a file to see T-SQL DDL';
            document.getElementById('detailsContent').textContent = 'Select a file to see details';
            
            setStatus('Cleared');
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            
            const units = ['B', 'KB', 'MB', 'GB'];
            let i = 0;
            while (bytes >= 1024 && i < units.length - 1) {
                bytes /= 1024;
                i++;
            }
            
            return `${bytes.toFixed(1)} ${units[i]}`;
        }
    </script>
</body>
</html>'''
        
        with open(os.path.join(templates_dir, 'index.html'), 'w') as f:
            f.write(index_html)


def main():
    """Run the web GUI application."""
    if not FLASK_AVAILABLE:
        print("Error: Flask is required for the web GUI.")
        print("Install with: pip install flask")
        return
        
    app = ExternalFileDetectionWebGUI()
    app.run(debug=True)