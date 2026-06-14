"""Web-based GUI for External File Detection.

Inspired by ParquetViewer, this provides a user-friendly web interface for:
- Selecting files or folders
- Previewing file metadata 
- Generating T-SQL DDL statements
"""

import os
import json
import logging
import uuid
import time
import tempfile
import threading
from typing import Dict, List, Any, Optional
from pathlib import Path
from urllib.parse import unquote

logger = logging.getLogger(__name__)

try:
    from flask import Flask, render_template, request, jsonify, session, send_file
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

from .external_file_detector import ExternalFileDetectorApp
from .file_detector import FileDetector


# Maximum upload size: 200 MB
MAX_UPLOAD_SIZE = 200 * 1024 * 1024


def _validate_path(path: str, root_dir: str = None,
                   allow_files: bool = True, allow_dirs: bool = True) -> str:
    """
    Validate and sanitize a path to prevent path injection attacks.
    
    Args:
        path: Path to validate
        root_dir: If set, only paths underneath this root are allowed.
        allow_files: Whether to allow file paths
        allow_dirs: Whether to allow directory paths
        
    Returns:
        Sanitized absolute path
        
    Raises:
        ValueError: If path is invalid or unsafe
    """
    if not path:
        raise ValueError("Path cannot be empty")
    
    # Reject obviously illegal characters before touching the filesystem
    if any(c in path for c in '<>|?*'):
        raise ValueError("Path contains unsafe characters")

    # Resolve symlinks and normalize the path
    normalized_path = os.path.realpath(os.path.abspath(path))
    
    # Root directory constraint (after symlink resolution). commonpath is robust
    # against trailing-separator quirks across platforms.
    root = os.path.realpath(os.path.abspath(root_dir or os.getcwd()))
    try:
        if os.path.commonpath([root, normalized_path]) != root:
            raise ValueError("Path is outside the allowed root directory")
    except ValueError:
        # commonpath raises when paths are on different drives (Windows)
        raise ValueError("Path is outside the allowed root directory")

    # Check if path exists
    if not os.path.exists(normalized_path):
        raise ValueError("Path does not exist")
    
    # Check if it's a file or directory as requested
    if os.path.isfile(normalized_path) and not allow_files:
        raise ValueError("File path not allowed")
    
    if os.path.isdir(normalized_path) and not allow_dirs:
        raise ValueError("Directory path not allowed")

    return normalized_path


def _clean_results(results):
    """Recursively clean results for JSON serialization (NaN/Inf → None)."""
    if isinstance(results, float):
        import math
        if math.isnan(results) or math.isinf(results):
            return None
        return results
    if isinstance(results, dict):
        return {k: _clean_results(v) for k, v in results.items()}
    elif isinstance(results, list):
        return [_clean_results(item) for item in results]
    elif isinstance(results, tuple):
        return [_clean_results(item) for item in results]
    elif isinstance(results, (str, int, bool, type(None))):
        return results
    else:
        return str(results)


class ExternalFileDetectionWebGUI:
    """Web-based GUI application for External File Detection."""
    
    def __init__(self, root_dir: str = None):
        """Initialize the web GUI application.
        
        Args:
            root_dir: If set, restrict all file access to this directory tree.
        """
        if not FLASK_AVAILABLE:
            raise ImportError("Flask is required for the web GUI. Install with: pip install flask")
        
        self._root_dir = root_dir
            
        self.app = Flask(__name__, template_folder='templates', static_folder=None)
        self.app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE
        secret_key = os.environ.get('FLASK_SECRET_KEY')
        if not secret_key:
            secret_key = os.urandom(24).hex()
            logger.warning(
                'FLASK_SECRET_KEY is not set; generated an ephemeral key. '
                'Sessions will not survive a process restart. Set FLASK_SECRET_KEY '
                'to a stable secret in production.'
            )
        self.app.secret_key = secret_key
        self.detector_app = ExternalFileDetectorApp()
        self.file_detector = FileDetector()
        self.sql_generator = self.detector_app.sql_generator
        
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
            path = self._root_dir or os.getcwd()
            return jsonify({'success': True, 'path': path})
            
        @self.app.route('/api/browse')
        def browse_files():
            """Browse files in a directory."""
            path = request.args.get('path', '') or self._root_dir or os.getcwd()
            try:
                # Validate and sanitize the path to prevent path injection
                path = _validate_path(path, root_dir=self._root_dir, allow_files=False, allow_dirs=True)
                
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
                        # Detect Delta tables: folder contains _delta_log
                        if os.path.isdir(os.path.join(item_path, '_delta_log')):
                            # Calculate total size of parquet files in the delta folder
                            delta_size = sum(
                                os.path.getsize(os.path.join(dp, f))
                                for dp, _, fns in os.walk(item_path)
                                for f in fns if not f.startswith('.')
                            )
                            items.append({
                                'name': item,
                                'path': item_path,
                                'type': 'delta_table',
                                'file_type': 'delta',
                                'size': delta_size
                            })
                        # Detect Iceberg tables: folder contains metadata/v*.metadata.json
                        elif self.file_detector.is_iceberg_table_directory(item_path):
                            iceberg_size = sum(
                                os.path.getsize(os.path.join(dp, f))
                                for dp, _, fns in os.walk(item_path)
                                for f in fns if not f.startswith('.')
                            )
                            items.append({
                                'name': item,
                                'path': item_path,
                                'type': 'delta_table',
                                'file_type': 'iceberg',
                                'size': iceberg_size
                            })
                        else:
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
                        # Allow dirs for Delta/Iceberg tables
                        is_delta = (os.path.isdir(file_path) and
                                    os.path.isdir(os.path.join(file_path, '_delta_log')))
                        is_iceberg = (os.path.isdir(file_path) and
                                      self.file_detector.is_iceberg_table_directory(file_path))
                        file_path = _validate_path(file_path, root_dir=self._root_dir,
                                                    allow_files=True,
                                                   allow_dirs=is_delta or is_iceberg)
                        
                        metadata = self.file_detector.analyze_file_metadata(file_path)
                        analyzed.append(metadata)
                    except ValueError as e:
                        analyzed.append({
                            'file_path': file_path,
                            'file_type': 'error',
                            'file_size': 0,
                            'error': f'Invalid path: {e}'
                        })
                    except PermissionError as e:
                        analyzed.append({
                            'file_path': file_path,
                            'file_type': 'error',
                            'file_size': 0,
                            'error': f'Permission denied: {e}'
                        })
                    except Exception as e:
                        analyzed.append({
                            'file_path': file_path,
                            'file_type': 'error',
                            'file_size': 0,
                            'error': f'Analysis failed: {type(e).__name__}: {e}'
                        })
                
                self._set_files(analyzed)
                return jsonify(_clean_results({
                    'success': True,
                    'files': analyzed,
                    'count': len(analyzed)
                }))
                
            except Exception:
                logger.exception('Error in /api/analyze_files')
                return jsonify({'success': False, 'error': 'Server error processing request'})

        @self.app.route('/api/upload', methods=['POST'])
        def upload_files():
            """Accept uploaded files, save to temp dir, and analyze them."""
            try:
                uploaded = request.files.getlist('files')
                if not uploaded:
                    return jsonify({'success': False, 'error': 'No files uploaded'})

                analyzed: List[Dict[str, Any]] = []

                with tempfile.TemporaryDirectory(prefix='efd_upload_') as upload_dir:
                    for f in uploaded:
                        if not f.filename:
                            continue
                        # Sanitize the filename to prevent path traversal
                        safe_name = os.path.basename(f.filename)
                        dest = os.path.join(upload_dir, safe_name)
                        f.save(dest)
                        try:
                            metadata = self.file_detector.analyze_file_metadata(dest)
                            analyzed.append(metadata)
                        except Exception as e:
                            analyzed.append({
                                'file_path': dest,
                                'file_type': 'error',
                                'file_size': 0,
                                'error': f'Analysis failed: {type(e).__name__}: {e}'
                            })

                self._set_files(analyzed)
                return jsonify(_clean_results({
                    'success': True,
                    'files': analyzed,
                    'count': len(analyzed)
                }))
            except Exception:
                logger.exception('Error in /api/upload')
                return jsonify({'success': False, 'error': 'Server error processing upload'})

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
                folder_path = _validate_path(folder_path, root_dir=self._root_dir, allow_files=False, allow_dirs=True)
                
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
                logger.exception('Error in /api/analyze_folder')
                return jsonify({'success': False, 'error': 'Server error processing request'})
                
        @self.app.route('/api/preview/<path:file_path>')
        def preview_file(file_path):
            """Get file preview."""
            try:
                # Flask automatically decodes the path parameter
                file_path = unquote(file_path)
                # Flask <path:> converter may strip leading '/' from absolute paths
                if not os.path.isabs(file_path):
                    file_path = '/' + file_path
                
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
                logger.exception('Error in /api/preview')
                return jsonify({'success': False, 'error': 'Server error generating preview'})
                
        @self.app.route('/api/sql_ddl/<path:file_path>')
        def get_sql_ddl(file_path):
            """Get SQL DDL for a file."""
            try:
                file_path = unquote(file_path)
                # Flask <path:> converter may strip leading '/' from absolute paths
                if not os.path.isabs(file_path):
                    file_path = '/' + file_path
                data_source = request.args.get('data_source', 'MyDataSource')
                schema_name = request.args.get('schema', 'dbo')
                target_platform = request.args.get('target_platform', 'sql_server_2022')
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
                        # Skip excluded columns
                        if ov.get('excluded'):
                            continue
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
                # Flask <path:> converter may strip leading '/' from absolute paths
                if not os.path.isabs(file_path):
                    file_path = '/' + file_path
                
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
                logger.exception('Error in /api/file_details')
                return jsonify({'success': False, 'error': 'Server error retrieving file details'})

        @self.app.route('/api/preview_table/<path:file_path>')
        def preview_table(file_path):
            """Return tabular preview data (columns + rows) for the file."""
            try:
                file_path = unquote(file_path)
                # Flask <path:> converter may strip leading '/' from absolute paths
                if not os.path.isabs(file_path):
                    file_path = '/' + file_path
                # Validate first
                safe_path = _validate_path(file_path, root_dir=self._root_dir, allow_files=True, allow_dirs=True)
                rows = min(int(request.args.get('rows', 100)), 10000)
                data = self.file_detector.get_preview_data(safe_path, max_rows=rows)
                return jsonify(_clean_results({'success': True, **data}))
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
                safe_path = _validate_path(file_path, root_dir=self._root_dir, allow_files=True, allow_dirs=True)
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

        # ---- Routes consolidated from web_ui.py ----

        @self.app.route('/api/supported-types', methods=['GET'])
        def supported_types():
            """Return supported file types."""
            return jsonify({'types': self.detector_app.get_supported_file_types()})

        @self.app.route('/api/analyze-upload', methods=['POST'])
        def analyze_upload():
            """Analyze uploaded files (web_ui-compatible endpoint)."""
            if 'files' not in request.files:
                return jsonify({'error': 'No files uploaded'}), 400

            files = request.files.getlist('files')
            data_source = request.form.get('data_source', '')
            results = []

            with tempfile.TemporaryDirectory() as temp_dir:
                for uploaded_file in files:
                    if uploaded_file.filename:
                        safe_name = Path(uploaded_file.filename).name
                        temp_path = os.path.join(temp_dir, safe_name)
                        uploaded_file.save(temp_path)

                        try:
                            metadata = self.file_detector.analyze_file_metadata(temp_path)
                            table_name = self.detector_app._generate_table_name(safe_name)
                            ddl = self.sql_generator.generate_complete_ddl(
                                metadata, table_name,
                                data_source if data_source else None,
                                uploaded_file.filename,
                            )
                            clean_metadata = _clean_results(metadata)
                            results.append({
                                'file_name': uploaded_file.filename,
                                'metadata': clean_metadata,
                                'sql_ddl': ddl,
                                'table_name': table_name,
                                'success': True,
                            })
                        except Exception as e:
                            results.append({
                                'file_name': uploaded_file.filename,
                                'error': str(e),
                                'success': False,
                            })

            return jsonify({'results': results, 'total': len(results)})

        @self.app.route('/api/analyze-path', methods=['POST'])
        def analyze_path():
            """Analyze files at a local or remote path."""
            data = request.get_json()
            if not data or 'path' not in data:
                return jsonify({'error': 'No path specified'}), 400

            location = data['path']
            if not isinstance(location, str) or not location.strip():
                return jsonify({'error': 'Path cannot be empty'}), 400
            location = location.strip()
            if len(location) > 2048:
                return jsonify({'error': 'Path too long'}), 400

            # For local paths, use full symlink-resolving validation
            is_remote = location.startswith(('s3://', 'azure://', 'https://'))
            if not is_remote:
                try:
                    location = _validate_path(location, root_dir=self._root_dir,
                                              allow_files=True, allow_dirs=True)
                except ValueError as e:
                    return jsonify({'error': str(e)}), 400

            data_source = data.get('data_source', '')
            storage_config = {}
            for src_key, dst_key in [
                ('aws_access_key_id', 'aws_access_key_id'),
                ('aws_secret_access_key', 'aws_secret_access_key'),
                ('aws_region', 'region_name'),
                ('azure_account_name', 'azure_account_name'),
                ('azure_account_key', 'azure_account_key'),
                ('azure_connection_string', 'azure_connection_string'),
            ]:
                if data.get(src_key):
                    storage_config[dst_key] = data[src_key]

            try:
                app_instance = ExternalFileDetectorApp(storage_config)
                results = app_instance.analyze_location(
                    location, data_source if data_source else None
                )
                clean_results = _clean_results(results)
                return jsonify(clean_results)
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/generate-data-source', methods=['POST'])
        def generate_data_source():
            """Generate CREATE EXTERNAL DATA SOURCE DDL."""
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            required = ['name', 'storage_type', 'location']
            missing = [f for f in required if f not in data]
            if missing:
                return jsonify({'error': f"Missing required fields: {', '.join(missing)}"}), 400

            try:
                ddl = self.detector_app.generate_data_source_ddl(
                    data['name'], data['storage_type'],
                    data['location'], data.get('credential'),
                    target_platform=data.get('target_platform', 'sql_server_2022'),
                )
                return jsonify({'sql_ddl': ddl})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/generate-ddl', methods=['POST'])
        def generate_ddl():
            """Generate DDL from manual metadata input."""
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            columns = data.get('columns', [])
            metadata = {
                'file_type': data.get('file_type', 'csv'),
                'file_path': data.get('location', ''),
                'schema': [(col['name'], col['type']) for col in columns] if columns else None,
                'delimiter': data.get('delimiter', ','),
                'has_header': data.get('has_header', True),
                'encoding': data.get('encoding', 'utf-8'),
                'compression': data.get('compression'),
            }

            try:
                ddl = self.sql_generator.generate_complete_ddl(
                    metadata,
                    data.get('table_name', 'ext_table'),
                    data.get('data_source'),
                    data.get('location', ''),
                )
                return jsonify({'sql_ddl': ddl})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/export', methods=['POST'])
        def export_results():
            """Export results as a downloadable file."""
            data = request.get_json()
            if not data or 'content' not in data:
                return jsonify({'error': 'No content provided'}), 400

            fmt = data.get('format', 'sql')
            content = data['content']

            with tempfile.NamedTemporaryFile(
                mode='w', suffix=f'.{fmt}', delete=False, prefix='efd_export_',
            ) as f:
                f.write(content)
                temp_path = f.name

            @self.app.after_request
            def _cleanup_export(response):
                """Remove temp export file after response is sent."""
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                # Unregister this one-shot handler
                self.app.after_request_funcs.get(None, []).remove(_cleanup_export)
                return response

            return send_file(
                temp_path, as_attachment=True,
                download_name=f'external_file_detection.{fmt}',
                mimetype='text/plain' if fmt == 'sql' else 'application/json',
            )

    def _generate_preview_content(self, file_data: Dict[str, Any]) -> str:
        """Generate preview content for a file (legacy text fallback)."""
        file_path = file_data['file_path']
        file_type = file_data.get('file_type', 'unknown')
        encoding = file_data.get('encoding') or 'utf-8'
        if encoding == 'binary':
            encoding = 'utf-8'

        try:
            # Validate file path to prevent path injection
            allow_dirs = file_type in ('delta',)
            file_path = _validate_path(file_path, root_dir=self._root_dir, allow_files=True, allow_dirs=allow_dirs)

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
