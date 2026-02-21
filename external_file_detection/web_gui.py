"""Web-based GUI for External File Detection.

Inspired by ParquetViewer, this provides a user-friendly web interface for:
- Selecting files or folders
- Previewing file metadata 
- Generating T-SQL DDL statements
"""

import os
import json
import uuid
import time
import threading
from typing import Dict, List, Any, Optional
from pathlib import Path
from urllib.parse import unquote

try:
    from flask import Flask, render_template, request, jsonify, session
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

from .external_file_detector import ExternalFileDetectorApp
from .file_detector import FileDetector


# Module-level root directory constraint (None = unrestricted)
_ROOT_DIR: Optional[str] = None


def _validate_path(path: str, allow_files: bool = True, allow_dirs: bool = True) -> str:
    """
    Validate and sanitize a path to prevent path injection attacks.
    
    When _ROOT_DIR is set, only paths underneath that root are allowed.
    
    Args:
        path: Path to validate
        allow_files: Whether to allow file paths
        allow_dirs: Whether to allow directory paths
        
    Returns:
        Sanitized absolute path
        
    Raises:
        ValueError: If path is invalid or unsafe
    """
    if not path:
        raise ValueError("Path cannot be empty")
    
    # Resolve symlinks and normalize the path
    normalized_path = os.path.realpath(os.path.abspath(path))
    
    # Root directory constraint (after symlink resolution)
    if _ROOT_DIR is not None:
        root = os.path.realpath(os.path.abspath(_ROOT_DIR))
        if not normalized_path.startswith(root + os.sep) and normalized_path != root:
            raise ValueError("Path is outside the allowed root directory")
    
    # Check if path exists
    if not os.path.exists(normalized_path):
        raise ValueError("Path does not exist")
    
    # Check if it's a file or directory as requested
    if os.path.isfile(normalized_path) and not allow_files:
        raise ValueError("File path not allowed")
    
    if os.path.isdir(normalized_path) and not allow_dirs:
        raise ValueError("Directory path not allowed")
    
    # Ensure path components don't contain traversal or illegal characters
    if '..' in Path(path).parts or any(c in normalized_path for c in '<>|?*'):
        raise ValueError("Path contains unsafe characters")
    
    return normalized_path


class ExternalFileDetectionWebGUI:
    """Web-based GUI application for External File Detection."""
    
    def __init__(self, root_dir: str = None):
        """Initialize the web GUI application.
        
        Args:
            root_dir: If set, restrict all file access to this directory tree.
        """
        global _ROOT_DIR
        if not FLASK_AVAILABLE:
            raise ImportError("Flask is required for the web GUI. Install with: pip install flask")
        
        _ROOT_DIR = root_dir
            
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())
        self.detector_app = ExternalFileDetectorApp()
        self.file_detector = FileDetector()
        
        # Thread-safe per-session file store
        self._sessions_lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, Any]] = {}  # sid -> {'files': [...], 'ts': float}
        self._session_ttl = 3600  # 1 hour TTL
        
        self.setup_routes()

    # --- thread-safe session helpers ---

    def _sid(self) -> str:
        """Return (or create) a per-browser session id."""
        if 'sid' not in session:
            session['sid'] = uuid.uuid4().hex
        return session['sid']

    def _get_files(self) -> List[Dict[str, Any]]:
        sid = self._sid()
        with self._sessions_lock:
            entry = self._sessions.setdefault(sid, {'files': [], 'ts': time.time()})
            entry['ts'] = time.time()
            return entry['files']

    def _set_files(self, files: List[Dict[str, Any]]) -> None:
        sid = self._sid()
        with self._sessions_lock:
            self._sessions[sid] = {'files': files, 'ts': time.time()}
            self._cleanup_expired_sessions()

    def _cleanup_expired_sessions(self) -> None:
        """Remove sessions older than TTL. Called inside _sessions_lock."""
        now = time.time()
        expired = [k for k, v in self._sessions.items()
                   if now - v.get('ts', 0) > self._session_ttl]
        for k in expired:
            del self._sessions[k]

    def setup_routes(self):
        """Set up Flask routes."""
        
        @self.app.route('/')
        def index():
            """Main page."""
            return render_template('index.html')

        @self.app.route('/api/initial_path')
        def initial_path():
            """Return the initial browse path (cwd or configured root)."""
            path = _ROOT_DIR or os.getcwd()
            return jsonify({'success': True, 'path': path})
            
        @self.app.route('/api/browse')
        def browse_files():
            """Browse files in a directory."""
            path = request.args.get('path', '') or _ROOT_DIR or os.getcwd()
            try:
                # Validate and sanitize the path to prevent path injection
                path = _validate_path(path, allow_files=False, allow_dirs=True)
                
                items = []
                
                # Add parent directory option if not at root
                parent = os.path.dirname(path)
                if parent != path:  # at root when dirname == path (works on Windows & Unix)
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
                
            except ValueError as e:
                return jsonify({
                    'success': False,
                    'error': f'Directory not accessible: {e}'
                })
            except PermissionError:
                return jsonify({
                    'success': False,
                    'error': f'Permission denied: cannot read {path}'
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Error accessing directory: {e}'
                })
                
        @self.app.route('/api/analyze_files', methods=['POST'])
        def analyze_files():
            """Analyze selected files."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'error': 'Invalid request data'})
                    
                file_paths = data.get('files', [])
                
                if not file_paths:
                    return jsonify({'success': False, 'error': 'No files provided'})
                
                # Build new file list
                analyzed: List[Dict[str, Any]] = []
                
                # Analyze each file
                for file_path in file_paths:
                    try:
                        # Validate and sanitize file path
                        file_path = _validate_path(file_path, allow_files=True, allow_dirs=False)
                        
                        metadata = self.file_detector.analyze_file_metadata(file_path)
                        analyzed.append(metadata)
                    except (ValueError, PermissionError):
                        analyzed.append({
                            'file_path': file_path,
                            'file_type': 'error',
                            'file_size': 0,
                            'error': 'File not accessible'
                        })
                    except Exception:
                        analyzed.append({
                            'file_path': file_path,
                            'file_type': 'error',
                            'file_size': 0,
                            'error': 'Error analyzing file'
                        })
                
                self._set_files(analyzed)
                return jsonify({
                    'success': True,
                    'files': analyzed,
                    'count': len(analyzed)
                })
                
            except Exception:
                return jsonify({'success': False, 'error': 'Server error processing request'})
                
        @self.app.route('/api/analyze_folder', methods=['POST'])
        def analyze_folder():
            """Analyze all supported files in a folder."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'error': 'Invalid request data'})
                    
                folder_path = data.get('folder')
                
                if not folder_path:
                    return jsonify({'success': False, 'error': 'No folder provided'})
                
                # Validate and sanitize folder path
                folder_path = _validate_path(folder_path, allow_files=False, allow_dirs=True)
                
                # Scan directory
                scanned = self.file_detector.scan_directory(folder_path)
                self._set_files(scanned)
                
                return jsonify({
                    'success': True,
                    'files': scanned,
                    'count': len(scanned)
                })
                
            except (ValueError, PermissionError):
                return jsonify({
                    'success': False, 
                    'error': 'Folder not accessible'
                })
            except Exception:
                return jsonify({'success': False, 'error': 'Server error processing request'})
                
        @self.app.route('/api/preview/<path:file_path>')
        def preview_file(file_path):
            """Get file preview."""
            try:
                # Flask automatically decodes the path parameter
                file_path = unquote(file_path)
                
                # Find file in current session files
                file_data = None
                for f in self._get_files():
                    if f['file_path'] == file_path:
                        file_data = f
                        break
                        
                if not file_data:
                    return jsonify({'success': False, 'error': 'File not found in current analysis'})
                    
                if 'error' in file_data:
                    return jsonify({
                        'success': False,
                        'error': 'Cannot preview file with errors'
                    })
                
                preview_content = self._generate_preview_content(file_data)
                
                return jsonify({
                    'success': True,
                    'preview': preview_content,
                    'file_type': file_data.get('file_type', 'unknown')
                })
                
            except Exception:
                return jsonify({'success': False, 'error': 'Server error generating preview'})
                
        @self.app.route('/api/sql_ddl/<path:file_path>')
        def get_sql_ddl(file_path):
            """Get SQL DDL for a file."""
            try:
                file_path = unquote(file_path)
                data_source = request.args.get('data_source', 'MyDataSource')
                schema_name = request.args.get('schema', 'dbo')
                target_platform = request.args.get('target_platform', 'synapse_dedicated')
                table_name = request.args.get('table_name', '') or None
                storage_url = request.args.get('storage_url', '') or None
                schema_overrides_raw = request.args.get('schema_overrides', '')
                schema_overrides = None
                if schema_overrides_raw:
                    try:
                        schema_overrides = json.loads(schema_overrides_raw)
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                # Find file in current session files
                file_data = None
                for f in self._get_files():
                    if f['file_path'] == file_path:
                        file_data = f
                        break
                        
                if not file_data:
                    return jsonify({'success': False, 'error': 'File not found in current analysis'})
                    
                if 'error' in file_data:
                    return jsonify({
                        'success': False,
                        'error': 'Cannot generate SQL DDL for file with errors'
                    })

                # Apply schema overrides if provided
                gen_metadata = dict(file_data)
                if schema_overrides and gen_metadata.get('schema'):
                    new_schema = []
                    new_nullable = list(gen_metadata.get('nullable_columns') or [])
                    for col_name, col_type in gen_metadata['schema']:
                        ov = schema_overrides.get(col_name, {})
                        new_name = ov.get('colName', col_name)
                        new_type = col_type  # keep original detected type
                        new_schema.append((new_name, new_type))
                        # Handle nullable override
                        if 'nullable' in ov:
                            if ov['nullable'] and new_name not in new_nullable:
                                new_nullable.append(new_name)
                            elif not ov['nullable'] and new_name in new_nullable:
                                new_nullable.remove(new_name)
                        # Store SQL type override
                        if 'sqlType' in ov:
                            gen_metadata.setdefault('sql_type_overrides', {})[new_name] = ov['sqlType']
                    gen_metadata['schema'] = new_schema
                    gen_metadata['nullable_columns'] = new_nullable
                
                # Generate all SQL statement types
                all_stmts = self.detector_app.sql_generator.generate_all_statements(
                    gen_metadata,
                    table_name=table_name,
                    data_source=data_source,
                    location=os.path.basename(file_data['file_path']),
                    schema_name=schema_name,
                    target_platform=target_platform,
                    storage_url=storage_url,
                )

                return jsonify({
                    'success': True,
                    'sql_ddl': all_stmts.get('create_external_table', ''),  # legacy
                    'statements': all_stmts
                })

            except Exception as e:
                return jsonify({'success': False, 'error': f'Server error generating SQL DDL: {e}'})
                
        @self.app.route('/api/file_details/<path:file_path>')
        def get_file_details(file_path):
            """Get detailed file information."""
            try:
                file_path = unquote(file_path)
                
                # Find file in current session files
                file_data = None
                for f in self._get_files():
                    if f['file_path'] == file_path:
                        file_data = f
                        break
                        
                if not file_data:
                    return jsonify({'success': False, 'error': 'File not found in current analysis'})
                
                return jsonify({
                    'success': True,
                    'details': file_data
                })
                
            except Exception:
                return jsonify({'success': False, 'error': 'Server error retrieving file details'})

        @self.app.route('/api/preview_table/<path:file_path>')
        def preview_table(file_path):
            """Return tabular preview data (columns + rows) for the file."""
            try:
                file_path = unquote(file_path)
                # Validate first
                safe_path = _validate_path(file_path, allow_files=True, allow_dirs=True)
                rows = int(request.args.get('rows', 100))
                data = self.file_detector.get_preview_data(safe_path, max_rows=rows)
                return jsonify({'success': True, **data})
            except (ValueError, PermissionError) as e:
                return jsonify({'success': False, 'error': str(e)})
            except Exception as e:
                return jsonify({'success': False, 'error': f'Preview error: {e}'})

        @self.app.route('/api/analyze_file', methods=['POST'])
        def analyze_single_file():
            """Analyse a single file by path and return full metadata + all SQL."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'error': 'Invalid request'})
                file_path = data.get('file_path', '')
                data_source = data.get('data_source', 'MyDataSource')
                safe_path = _validate_path(file_path, allow_files=True, allow_dirs=True)
                metadata = self.file_detector.analyze_file_metadata(safe_path)
                statements = self.detector_app.sql_generator.generate_all_statements(
                    metadata, data_source=data_source
                )
                # Store in session
                current = self._get_files()
                existing = next((i for i, f in enumerate(current)
                                 if f['file_path'] == safe_path), None)
                if existing is not None:
                    current[existing] = metadata
                else:
                    current.append(metadata)
                self._set_files(current)
                return jsonify({'success': True, 'metadata': metadata, 'statements': statements})
            except (ValueError, PermissionError) as e:
                return jsonify({'success': False, 'error': str(e)})
            except Exception as e:
                return jsonify({'success': False, 'error': f'Analysis error: {e}'})

    def _generate_preview_content(self, file_data: Dict[str, Any]) -> str:
        """Generate preview content for a file (legacy text fallback â€” UI uses /api/preview_table)."""
        file_path = file_data['file_path']
        file_type = file_data.get('file_type', 'unknown')
        encoding = file_data.get('encoding') or 'utf-8'
        if encoding == 'binary':
            encoding = 'utf-8'

        try:
            # Validate file path to prevent path injection
            allow_dirs = file_type in ('delta',)
            file_path = _validate_path(file_path, allow_files=True, allow_dirs=allow_dirs)

            if file_type in ('csv', 'text', 'json'):
                # Show text preview using detected encoding
                with open(file_path, 'r', encoding=encoding, errors='replace') as f:
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

            elif file_type in ('parquet', 'delta'):
                # Show metadata + sample data
                try:
                    import pyarrow.parquet as pq
                    import pandas as pd

                    if file_type == 'delta':
                        try:
                            from deltalake import DeltaTable  # type: ignore
                            dt = DeltaTable(file_path)
                            dm = dt.metadata()
                            schema = dt.schema()
                            pv = [
                                f'Delta Table: {os.path.basename(file_path)}',
                                f'Version    : {dt.version()}',
                                f'Partitions : {dm.partition_columns or "none"}',
                                '',
                                'Schema:',
                            ]
                            for f2 in schema.fields:
                                pv.append(f'  {f2.name}: {f2.type}{"  (nullable)" if f2.nullable else ""}')
                            try:
                                df = dt.to_pandas().head(10)
                                pv += ['', 'Sample Data (first 10 rows):', df.to_string()]
                            except Exception:
                                pv.append('(Could not load sample data)')
                            return '\n'.join(pv)
                        except ImportError:
                            pass  # fall through to parquet path

                    parquet_file = pq.ParquetFile(file_path)
                    pv = [
                        f'Parquet File: {os.path.basename(file_path)}',
                        f'Rows        : {parquet_file.metadata.num_rows:,}',
                        f'Row groups  : {parquet_file.metadata.num_row_groups}',
                        f'Columns     : {len(parquet_file.schema)}',
                        '',
                        'Schema:',
                    ]
                    for field in parquet_file.schema:
                        pv.append(f'  {field.name}: {field.type}')
                    try:
                        df = parquet_file.read().to_pandas().head(10)
                        pv += ['', 'Sample Data (first 10 rows):', df.to_string()]
                    except Exception:
                        pv.append('(Could not load sample data)')
                    return '\n'.join(pv)
                    
                except Exception:
                    return "Error reading Parquet file"
                    
            else:
                return f"Preview not available for {file_type} files"
                
        except (ValueError, PermissionError):
            return "File not accessible"
        except Exception:
            return "Error loading preview"
    
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
        # Ensure templates directory exists
        templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
        os.makedirs(templates_dir, exist_ok=True)
        
        index_path = os.path.join(templates_dir, 'index.html')
        if not os.path.exists(index_path):
            raise FileNotFoundError(
                f"Template not found at {index_path}. "
                "Please ensure templates/index.html is present in the package."
            )
        
        print(f"Starting External File Detection Web GUI...")
        print(f"Open your browser and go to: http://{host}:{port}")
        
        self.app.run(host=host, port=port, debug=debug)


def main():
    """Run the web GUI application."""
    if not FLASK_AVAILABLE:
        print("Error: Flask is required for the web GUI.")
        print("Install with: pip install flask")
        return
        
    import argparse
    parser = argparse.ArgumentParser(description='External File Detection Web GUI')
    parser.add_argument('--root-dir', default=None,
                        help='Restrict file browsing to this directory tree')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    
    app = ExternalFileDetectionWebGUI(root_dir=args.root_dir)
    app.run(host=args.host, port=args.port, debug=args.debug)
