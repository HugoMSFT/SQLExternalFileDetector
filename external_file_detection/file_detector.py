"""File type detection and metadata analysis module."""

import os
import json
import csv
import math
import logging
import threading
from copy import deepcopy
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy imports for heavy dependencies (deferred to first use)
pd = None  # pandas
pq = None  # pyarrow.parquet


def _ensure_pandas():
    """Lazily import pandas on first use."""
    global pd
    if pd is None:
        import pandas as _pd
        pd = _pd
    return pd


def _ensure_pyarrow():
    """Lazily import pyarrow.parquet on first use."""
    global pq
    if pq is None:
        import pyarrow.parquet as _pq
        pq = _pq
    return pq

# --- Constants ---
CSV_SAMPLE_SIZE = 4096
ENCODING_DETECTION_BYTES = 65536
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB


def _json_safe(val: Any) -> Any:
    """Return a JSON-serialisable representation of *val* for sample storage."""
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if isinstance(val, (str, int, float, bool, type(None))):
        return val
    return str(val)


class FileDetector:
    """Detects file types and analyzes metadata for SQL DDL generation."""

    SUPPORTED_EXTENSIONS = {
        '.txt': 'text',
        '.csv': 'csv',
        '.tsv': 'csv',
        '.parquet': 'parquet',
        '.snappy': 'parquet',
        '.json': 'json',
        '.jsonl': 'json',
        '.ndjson': 'json',
        '.orc': 'orc',
        '.rc': 'rc',
        '.delta': 'delta',
        '.xlsx': 'excel',
        '.xls': 'excel',
    }

    # Codepage numbers for SQL Server BULK INSERT
    CODEPAGE_MAP = {
        'utf-8': '65001',
        'utf-8-sig': '65001',
        'ascii': '1252',
        'latin-1': '1252',
        'iso-8859-1': '1252',
        'cp1252': '1252',
        'windows-1252': '1252',
        'utf-16': '1200',
        'utf-16-le': '1200',
        'utf-16-be': '1201',
        'shift_jis': '932',
        'euc-jp': '20932',
        'gbk': '936',
        'big5': '950',
    }

    def __init__(self):
        """Initialize the file detector."""
        self._cache_lock = threading.Lock()
        self._encoding_cache: Dict[Tuple[str, float, int], Tuple[str, float]] = {}
        self._metadata_cache: Dict[Tuple[str, float, int], Dict[str, Any]] = {}

    def _get_file_signature(self, file_path: str) -> Optional[Tuple[str, float, int]]:
        """Return a cache signature for a file or directory based on path + stat info."""
        try:
            stat = os.stat(file_path)
            return (os.path.abspath(file_path), stat.st_mtime, stat.st_size)
        except OSError:
            return None

    def is_delta_table_directory(self, directory_path: str) -> bool:
        """Return True if *directory_path* looks like a Delta Lake table folder."""
        if not os.path.isdir(directory_path):
            return False
        return os.path.isdir(os.path.join(directory_path, '_delta_log'))

    def is_iceberg_table_directory(self, directory_path: str) -> bool:
        """Return True if *directory_path* looks like an Apache Iceberg table folder."""
        if not os.path.isdir(directory_path):
            return False
        metadata_dir = os.path.join(directory_path, 'metadata')
        if not os.path.isdir(metadata_dir):
            return False
        # Look for any v*.metadata.json file
        import glob
        return bool(glob.glob(os.path.join(metadata_dir, 'v*.metadata.json')))

    # ------------------------------------------------------------------
    # Type detection
    # ------------------------------------------------------------------

    def detect_file_type(self, file_path: str) -> str:
        """Detect the type of a file based on extension and content analysis."""
        if self.is_delta_table_directory(file_path):
            return 'delta'
        if self.is_iceberg_table_directory(file_path):
            return 'iceberg'
        if os.path.isdir(file_path):
            return 'unknown'

        path = Path(file_path)
        extension = path.suffix.lower()

        if extension in self.SUPPORTED_EXTENSIONS:
            return self.SUPPORTED_EXTENSIONS[extension]

        try:
            return self._detect_by_content(file_path)
        except Exception:
            return 'unknown'

    def _detect_by_content(self, file_path: str) -> str:
        """Detect file type by analysing the first bytes / characters."""
        # Parquet magic bytes: PAR1
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)
            if header == b'PAR1':
                return 'parquet'
        except Exception:
            pass

        # JSON — only read the first few KB instead of the whole file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                sample = f.read(8192)
            sample_stripped = sample.lstrip()
            if sample_stripped and sample_stripped[0] in ('{', '['):
                json.loads(sample_stripped)
                return 'json'
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            # Partial read may fail to parse; check if it starts like JSON
            try:
                if sample_stripped and sample_stripped[0] in ('{', '['):
                    return 'json'
            except Exception:
                pass

        # CSV / delimited text
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                sample = f.read(2048)
            sniffer = csv.Sniffer()
            if sniffer.has_header(sample):
                return 'csv'
        except Exception:
            pass

        return 'text'

    # ------------------------------------------------------------------
    # Encoding detection
    # ------------------------------------------------------------------

    def detect_encoding(self, file_path: str) -> Tuple[str, float]:
        """Detect file encoding using chardet when available."""
        signature = self._get_file_signature(file_path)
        if signature:
            with self._cache_lock:
                if signature in self._encoding_cache:
                    return self._encoding_cache[signature]

        try:
            import chardet
            with open(file_path, 'rb') as f:
                raw = f.read(ENCODING_DETECTION_BYTES)
            result = chardet.detect(raw)
            encoding = (result.get('encoding') or 'utf-8').lower()
            confidence = float(result.get('confidence') or 0.0)
            detected = (encoding, confidence)
            if signature:
                with self._cache_lock:
                    self._encoding_cache[signature] = detected
            return detected
        except ImportError:
            pass

        for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    f.read(4096)
                detected = (enc, 0.5)
                if signature:
                    with self._cache_lock:
                        self._encoding_cache[signature] = detected
                return detected
            except (UnicodeDecodeError, LookupError):
                continue
        detected = ('utf-8', 0.0)
        if signature:
            with self._cache_lock:
                self._encoding_cache[signature] = detected
        return detected

    def encoding_to_codepage(self, encoding: str) -> str:
        """Return the SQL Server codepage string for a given Python encoding name."""
        key = encoding.lower().strip()
        return self.CODEPAGE_MAP.get(key, 'ACP')

    # ------------------------------------------------------------------
    # Full metadata analysis
    # ------------------------------------------------------------------

    def analyze_file_metadata(self, file_path: str) -> Dict[str, Any]:
        """Analyse file metadata including schema, size, encoding and format details."""
        signature = self._get_file_signature(file_path)
        if signature:
            with self._cache_lock:
                if signature in self._metadata_cache:
                    return deepcopy(self._metadata_cache[signature])

        file_type = self.detect_file_type(file_path)
        if file_type in ('csv', 'text', 'json'):
            encoding, enc_confidence = self.detect_encoding(file_path)
        else:
            encoding, enc_confidence = 'binary', 1.0
        codepage = self.encoding_to_codepage(encoding)

        if os.path.isdir(file_path):
            file_size = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, fns in os.walk(file_path)
                for f in fns
            )
        else:
            file_size = os.path.getsize(file_path)

        metadata: Dict[str, Any] = {
            'file_path': file_path,
            'file_name': os.path.basename(file_path),
            'file_type': file_type,
            'file_size': file_size,
            'schema': None,
            'row_count': None,
            'column_count': None,
            'delimiter': None,
            'encoding': encoding,
            'encoding_confidence': round(enc_confidence * 100),
            'codepage': codepage,
            'has_header': False,
            'compression': None,
            'nullable_columns': [],
            'parquet_metadata': None,
            'delta_metadata': None,
        }

        # Warn if encoding detection confidence is low
        if file_type in ('csv', 'text', 'json') and enc_confidence < 0.5:
            metadata['encoding_warning'] = (
                f'Low confidence ({round(enc_confidence * 100)}%) for encoding "{encoding}". '
                f'Verify encoding manually or specify it explicitly.'
            )

        try:
            if file_type == 'csv':
                metadata.update(self._analyze_csv(file_path, encoding))
            elif file_type == 'parquet':
                metadata.update(self._analyze_parquet(file_path))
            elif file_type == 'delta':
                metadata.update(self._analyze_delta(file_path))
            elif file_type == 'iceberg':
                metadata.update(self._analyze_iceberg(file_path))
            elif file_type == 'json':
                metadata.update(self._analyze_json(file_path, encoding))
            elif file_type == 'excel':
                metadata.update(self._analyze_excel(file_path))
            elif file_type == 'text':
                metadata.update(self._analyze_text(file_path, encoding))
        except Exception as e:
            metadata['error'] = str(e)

        if signature:
            with self._cache_lock:
                self._metadata_cache[signature] = deepcopy(metadata)
        return metadata

    # ------------------------------------------------------------------
    # Per-format analyser helpers
    # ------------------------------------------------------------------

    def _analyze_csv(self, file_path: str, encoding: str = 'utf-8') -> Dict[str, Any]:
        """Analyse CSV / TSV file metadata."""
        _ensure_pandas()
        result: Dict[str, Any] = {}
        try:
            delimiter = ','
            has_header = True
            try:
                with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                    sample = f.read(4096)
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample)
                delimiter = dialect.delimiter
                has_header = sniffer.has_header(sample)
            except csv.Error:
                if '.tsv' in file_path.lower():
                    delimiter = '\t'

            result['delimiter'] = delimiter
            result['has_header'] = has_header

            df = pd.read_csv(file_path, nrows=1000, encoding=encoding,
                             sep=delimiter, low_memory=False, on_bad_lines='warn')
            result['schema'] = [(col, str(dtype)) for col, dtype in df.dtypes.items()]
            result['column_count'] = len(df.columns)

            # Sample max string lengths for smarter SQL type sizing
            max_lengths: Dict[str, int] = {}
            for col in df.columns:
                if df[col].dtype == object:
                    max_len = df[col].dropna().astype(str).str.len().max()
                    max_lengths[col] = int(max_len) if pd.notna(max_len) else 0
            result['max_string_lengths'] = max_lengths

            try:
                file_size = os.path.getsize(file_path)
                if file_size > LARGE_FILE_THRESHOLD:  # estimate row count for large files
                    with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                        sample_lines = [f.readline() for _ in range(500)]
                    avg_line = sum(len(l) for l in sample_lines) / max(len(sample_lines), 1)
                    result['row_count'] = int(file_size / max(avg_line, 1)) - (1 if has_header else 0)
                    result['row_count_estimated'] = True
                else:
                    with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                        result['row_count'] = sum(1 for _ in f) - (1 if has_header else 0)
            except Exception:
                result['row_count'] = len(df)

            result['nullable_columns'] = [col for col in df.columns if df[col].isnull().any()]

            # Store sample rows (first 3) for SQL comment generation
            sample_rows = df.head(3).where(pd.notnull(df.head(3)), None).values.tolist()
            result['sample_rows'] = [[_json_safe(v) for v in row] for row in sample_rows]
        except Exception as e:
            logger.warning("Failed to analyze CSV %s: %s", file_path, e)
            result['error'] = str(e)
            result.setdefault('delimiter', ',')
            result.setdefault('has_header', False)
        return result

    def _analyze_parquet(self, file_path: str) -> Dict[str, Any]:
        """Analyse Parquet file metadata."""
        _ensure_pyarrow()
        try:
            pf = pq.ParquetFile(file_path)
            arrow_schema = pf.schema_arrow
            pq_meta = pf.metadata

            schema = [(field.name, str(field.type)) for field in arrow_schema]
            nullable_cols = [field.name for field in arrow_schema if field.nullable]

            compression = None
            if pq_meta.num_row_groups > 0:
                try:
                    compression = pq_meta.row_group(0).column(0).compression
                except Exception:
                    pass

            kv_meta: Dict[str, str] = {}
            if pq_meta.metadata:
                for k, v in pq_meta.metadata.items():
                    try:
                        kv_meta[k.decode()] = v.decode()
                    except Exception:
                        pass

            return {
                'schema': schema,
                'row_count': pq_meta.num_rows,
                'column_count': len(arrow_schema),
                'compression': compression,
                'nullable_columns': nullable_cols,
                'encoding': 'binary',
                'parquet_metadata': {
                    'created_by': pq_meta.created_by,
                    'num_row_groups': pq_meta.num_row_groups,
                    'serialized_size': pq_meta.serialized_size,
                    'format_version': str(pq_meta.format_version),
                    'key_value_metadata': kv_meta,
                },
            }
        except Exception as e:
            _ensure_pandas()
            try:
                df = pd.read_parquet(file_path)
                return {
                    'schema': [(col, str(dtype)) for col, dtype in df.dtypes.items()],
                    'row_count': len(df),
                    'column_count': len(df.columns),
                    'encoding': 'binary',
                }
            except Exception:
                return {'error': str(e), 'encoding': 'binary'}

    def _analyze_delta(self, file_path: str) -> Dict[str, Any]:
        """Analyse a Delta Lake table folder."""
        try:
            from deltalake import DeltaTable  # type: ignore
            dt = DeltaTable(file_path)
            schema = dt.schema()
            meta = dt.metadata()

            fields = [(f.name, str(f.type)) for f in schema.fields]
            nullable_cols = [f.name for f in schema.fields if f.nullable]

            delta_meta = {
                'version': dt.version(),
                'name': meta.name,
                'description': meta.description,
                'partition_columns': meta.partition_columns,
                'created_time': str(meta.created_time) if meta.created_time else None,
                'configuration': meta.configuration,
            }

            row_count = None
            try:
                # Use pyarrow dataset to count rows without loading data
                ds = dt.to_pyarrow_dataset()
                row_count = ds.count_rows()
            except Exception:
                try:
                    # Fallback: read just one column to get num_rows
                    tbl = dt.to_pyarrow_table(columns=[schema.fields[0].name] if schema.fields else [])
                    row_count = tbl.num_rows
                except Exception:
                    pass

            return {
                'schema': fields,
                'column_count': len(fields),
                'row_count': row_count,
                'nullable_columns': nullable_cols,
                'delta_metadata': delta_meta,
                'encoding': 'binary',
            }
        except ImportError:
            logger.warning("DeltaTable analysis requires 'deltalake' package. "
                           "Falling back to Parquet analysis for %s. "
                           "Install with: pip install deltalake", file_path)
            result = self._analyze_parquet(file_path)
            result['warning'] = 'Delta table support requires: pip install deltalake'
            return result
        except Exception as e:
            # Fall back to reading underlying parquet files directly
            try:
                import glob
                parquet_files = glob.glob(
                    os.path.join(file_path, '**/*.parquet'), recursive=True
                )
                if parquet_files:
                    result = self._analyze_parquet(parquet_files[0])
                    result['warning'] = (
                        f'Delta log parsing failed ({type(e).__name__}). '
                        f'Metadata derived from underlying parquet files.'
                    )
                    return result
            except Exception:
                pass
            return {'error': str(e), 'encoding': 'binary'}

    def _analyze_iceberg(self, file_path: str) -> Dict[str, Any]:
        """Analyse an Apache Iceberg table folder by reading its metadata JSON."""
        import glob as _glob

        # Iceberg type mapping to our internal type names
        iceberg_type_map = {
            'boolean': 'bool', 'int': 'int32', 'long': 'int64',
            'float': 'float32', 'double': 'float64', 'string': 'str',
            'date': 'date', 'time': 'time', 'timestamp': 'timestamp',
            'timestamptz': 'timestamp', 'timestamp_ntz': 'timestamp',
            'binary': 'binary', 'uuid': 'str', 'fixed': 'binary',
            'decimal': 'decimal128',
        }

        try:
            # Find the latest metadata file
            meta_dir = os.path.join(file_path, 'metadata')
            meta_files = sorted(_glob.glob(os.path.join(meta_dir, 'v*.metadata.json')))
            if not meta_files:
                return {'error': 'No Iceberg metadata file found', 'encoding': 'binary'}

            with open(meta_files[-1], 'r', encoding='utf-8') as f:
                meta = json.load(f)

            # Parse schema from Iceberg metadata
            ice_schema = meta.get('schema') or (meta.get('schemas') or [{}])[-1]
            fields_raw = ice_schema.get('fields', [])

            schema = []
            nullable_cols = []
            for field in fields_raw:
                name = field.get('name', '')
                raw_type = field.get('type', 'string')
                if isinstance(raw_type, dict):
                    raw_type = raw_type.get('type', 'string')
                internal_type = iceberg_type_map.get(raw_type.lower(), 'str')
                schema.append((name, internal_type))
                if not field.get('required', False):
                    nullable_cols.append(name)

            iceberg_meta = {
                'format_version': meta.get('format-version'),
                'table_uuid': meta.get('table-uuid'),
                'location': meta.get('location'),
                'last_updated': meta.get('last-updated-ms'),
                'partition_spec': meta.get('partition-spec', {}).get('fields', []),
            }

            # Try counting rows from the underlying parquet files
            row_count = None
            parquet_files = _glob.glob(
                os.path.join(file_path, 'data', '*.parquet')
            )
            if parquet_files:
                try:
                    _ensure_pyarrow()
                    total = 0
                    for pf_path in parquet_files:
                        pf = pq.ParquetFile(pf_path)
                        total += pf.metadata.num_rows
                    row_count = total
                except Exception:
                    pass

            return {
                'schema': schema,
                'column_count': len(schema),
                'row_count': row_count,
                'nullable_columns': nullable_cols,
                'iceberg_metadata': iceberg_meta,
                'encoding': 'binary',
            }
        except Exception as e:
            # Fallback: try reading parquet files directly
            try:
                parquet_files = _glob.glob(
                    os.path.join(file_path, 'data', '*.parquet')
                )
                if parquet_files:
                    result = self._analyze_parquet(parquet_files[0])
                    result['warning'] = (
                        f'Iceberg metadata parsing failed ({type(e).__name__}). '
                        f'Metadata derived from underlying parquet files.'
                    )
                    return result
            except Exception:
                pass
            return {'error': str(e), 'encoding': 'binary'}

    def _analyze_json(self, file_path: str, encoding: str = 'utf-8') -> Dict[str, Any]:
        """Analyse JSON / NDJSON file metadata.

        Detects:
        - json_format: 'ndjson', 'array', or 'object'
        - json_nesting: dict mapping column name -> 'scalar', 'object', or 'array'
        - json_sample_values: dict mapping column name -> first non-null sample value
        """
        try:
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                first_char = f.read(1)
                f.seek(0)

                # ---- Try NDJSON (line-delimited JSON) ----
                if first_char == '{':
                    rows: list = []
                    for i, line in enumerate(f):
                        if i >= 200:
                            break
                        line = line.strip()
                        if line:
                            try:
                                rows.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                    if rows and isinstance(rows[0], dict):
                        return self._build_json_result(rows, json_format='ndjson')

                # ---- Full parse ----
                f.seek(0)
                data = json.load(f)

            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict):
                    return self._build_json_result(data, json_format='array')
            elif isinstance(data, dict):
                return self._build_json_result([data], json_format='object')
            return {}
        except Exception as e:
            return {'error': str(e)}

    # --- JSON helper ------------------------------------------------

    @staticmethod
    def _build_json_result(rows: list, json_format: str) -> Dict[str, Any]:
        """Build rich JSON metadata from a list of row-dicts.

        Walks one level deep to classify each field as scalar / object / array
        and records sample values for SQL generation.

        Scans ALL rows to discover the full set of keys (NDJSON files may
        have different fields per line).
        """
        # Collect all unique keys in order of first appearance across all rows
        all_keys: Dict[str, None] = {}
        for row in rows:
            for key in row:
                if key not in all_keys:
                    all_keys[key] = None

        schema: List[tuple] = []
        nesting: Dict[str, str] = {}
        sample_values: Dict[str, Any] = {}
        nullable_columns: List[str] = []

        for key in all_keys:
            # Find first non-null value for this key across all rows
            effective_val = None
            missing_count = 0
            for r in rows:
                if key not in r or r[key] is None:
                    missing_count += 1
                elif effective_val is None:
                    effective_val = r[key]

            if missing_count > 0:
                nullable_columns.append(key)

            if isinstance(effective_val, dict):
                nesting[key] = 'object'
                schema.append((key, 'dict'))
            elif isinstance(effective_val, list):
                nesting[key] = 'array'
                schema.append((key, 'list'))
            else:
                nesting[key] = 'scalar'
                schema.append((key, type(effective_val).__name__ if effective_val is not None else 'str'))

            sample_values[key] = effective_val

        return {
            'schema': schema,
            'row_count': len(rows),
            'column_count': len(schema),
            'has_header': True,
            'json_format': json_format,
            'json_nesting': nesting,
            'json_sample_values': {k: _json_safe(v) for k, v in sample_values.items()},
            'nullable_columns': nullable_columns,
        }


    def _analyze_text(self, file_path: str, encoding: str = 'utf-8') -> Dict[str, Any]:
        """Analyse plain text file metadata."""
        try:
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                lines = f.readlines()
            return {'row_count': len(lines)}
        except Exception as e:
            return {'error': str(e)}

    def _analyze_excel(self, file_path: str) -> Dict[str, Any]:
        """Analyse Excel (.xlsx / .xls) file metadata."""
        _ensure_pandas()
        try:
            try:
                import openpyxl  # noqa: F401
                df = pd.read_excel(file_path, nrows=200, engine='openpyxl')
            except ImportError:
                logger.warning("openpyxl not installed; Excel analysis may be limited. "
                               "Install with: pip install openpyxl")
                df = pd.read_excel(file_path, nrows=200)

            schema = []
            nullable_cols = []
            max_lengths: Dict[str, int] = {}
            for col in df.columns:
                dtype = str(df[col].dtype)
                if df[col].isnull().any():
                    nullable_cols.append(str(col))
                if dtype == 'object':
                    lengths = df[col].dropna().astype(str).str.len()
                    if len(lengths) > 0:
                        max_lengths[str(col)] = int(lengths.max())
                schema.append((str(col), dtype))

            return {
                'schema': schema,
                'nullable_columns': nullable_cols,
                'max_string_lengths': max_lengths,
                'row_count': len(df),
                'column_count': len(schema),
                'has_header': True,
                'sample_rows': [[_json_safe(v) for v in row] for row in df.head(3).where(pd.notnull(df.head(3)), None).values.tolist()],
            }
        except Exception as e:
            return {'error': str(e)}

    # ------------------------------------------------------------------
    # Preview data (tabular)
    # ------------------------------------------------------------------

    def get_preview_data(self, file_path: str, max_rows: int = 100) -> Dict[str, Any]:
        """Return a tabular preview of the file as columns + rows."""
        # Cap max_rows to prevent memory exhaustion
        max_rows = min(max_rows, 10000)
        _ensure_pandas()
        _ensure_pyarrow()
        file_type = self.detect_file_type(file_path)
        meta = self.analyze_file_metadata(file_path)
        encoding = meta.get('encoding', 'utf-8') or 'utf-8'
        if encoding == 'binary':
            encoding = 'utf-8'

        try:
            if file_type == 'csv':
                delimiter = meta.get('delimiter', ',') or ','
                df = pd.read_csv(file_path, nrows=max_rows, encoding=encoding,
                                 sep=delimiter, low_memory=False, on_bad_lines='skip')

            elif file_type == 'parquet':
                pf = pq.ParquetFile(file_path)
                # Read only the first row group instead of entire file
                if pf.metadata.num_row_groups > 0:
                    table = pf.read_row_group(0)
                    df = table.slice(0, max_rows).to_pandas()
                else:
                    df = pf.read().slice(0, max_rows).to_pandas()

            elif file_type == 'delta':
                try:
                    from deltalake import DeltaTable  # type: ignore
                    dt = DeltaTable(file_path)
                    # Use dataset scanner to avoid loading full table
                    ds = dt.to_pyarrow_dataset()
                    df = ds.scanner().head(max_rows).to_pandas()
                except ImportError:
                    pf = pq.ParquetFile(file_path)
                    if pf.metadata.num_row_groups > 0:
                        df = pf.read_row_group(0).slice(0, max_rows).to_pandas()
                    else:
                        df = pf.read().slice(0, max_rows).to_pandas()

            elif file_type == 'iceberg':
                import glob as _glob
                pq_files = sorted(_glob.glob(os.path.join(file_path, 'data', '*.parquet')))
                if pq_files:
                    pf = pq.ParquetFile(pq_files[0])
                    if pf.metadata.num_row_groups > 0:
                        df = pf.read_row_group(0).slice(0, max_rows).to_pandas()
                    else:
                        df = pf.read().slice(0, max_rows).to_pandas()
                else:
                    df = pd.DataFrame()

            elif file_type == 'json':
                # Try NDJSON first (line-delimited JSON: each line is a JSON object)
                is_ndjson = False
                with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                    first_char = f.read(1)
                    if first_char == '{':
                        f.seek(0)
                        rows = []
                        for i, line in enumerate(f):
                            if i >= max_rows:
                                break
                            line = line.strip()
                            if line:
                                try:
                                    rows.append(json.loads(line))
                                except json.JSONDecodeError:
                                    pass
                        if rows:
                            df = pd.DataFrame(rows)
                            is_ndjson = True

                if not is_ndjson:
                    with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        df = pd.DataFrame(data[:max_rows])
                    else:
                        df = pd.DataFrame([data])

            elif file_type == 'excel':
                try:
                    import openpyxl  # noqa: F401
                    df = pd.read_excel(file_path, nrows=max_rows, engine='openpyxl')
                except ImportError:
                    df = pd.read_excel(file_path, nrows=max_rows)

            else:
                lines = []
                with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                    for i, line in enumerate(f):
                        if i >= max_rows:
                            break
                        lines.append({'line': line.rstrip()})
                df = pd.DataFrame(lines)

            columns = [{'name': col, 'type': str(dtype)} for col, dtype in df.dtypes.items()]
            rows = df.where(pd.notnull(df), None).values.tolist()

            def _safe_val(v):
                """Ensure value is JSON-serialisable (NaN/Inf → None)."""
                if v is None:
                    return None
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    return None
                if not isinstance(v, (str, int, float, bool)):
                    return str(v)
                return v

            safe_rows = [[_safe_val(v) for v in row] for row in rows]

            return {
                'columns': columns,
                'rows': safe_rows,
                'total_rows': meta.get('row_count'),
                'truncated': (meta.get('row_count') or 0) > max_rows,
            }

        except Exception as e:
            return {
                'columns': [],
                'rows': [],
                'total_rows': None,
                'truncated': False,
                'error': str(e),
            }

    # ------------------------------------------------------------------
    # Directory scan
    # ------------------------------------------------------------------

    def scan_directory(self, directory_path: str) -> List[Dict[str, Any]]:
        """Scan a directory recursively for supported files."""
        results = []
        for root, dirs, files in os.walk(directory_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']

            # Recognize Delta table folders once at the directory level and avoid
            # descending into their internals as separate file entries.
            delta_dirs = []
            iceberg_dirs = []
            remaining_dirs = []
            for dirname in dirs:
                candidate = os.path.join(root, dirname)
                if self.is_delta_table_directory(candidate):
                    delta_dirs.append(candidate)
                elif self.is_iceberg_table_directory(candidate):
                    iceberg_dirs.append(candidate)
                else:
                    remaining_dirs.append(dirname)

            for delta_dir in delta_dirs:
                metadata = self.analyze_file_metadata(delta_dir)
                results.append(metadata)

            for iceberg_dir in iceberg_dirs:
                metadata = self.analyze_file_metadata(iceberg_dir)
                results.append(metadata)

            dirs[:] = remaining_dirs

            for file in files:
                file_path = os.path.join(root, file)
                file_type = self.detect_file_type(file_path)
                if file_type != 'unknown':
                    metadata = self.analyze_file_metadata(file_path)
                    results.append(metadata)
        return results
