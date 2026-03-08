"""File type detection and metadata analysis module."""

import os
import json
import csv
import logging
import mimetypes
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


def _json_safe(val: Any) -> Any:
    """Return a JSON-serialisable representation of *val* for sample storage."""
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
        pass

    # ------------------------------------------------------------------
    # Type detection
    # ------------------------------------------------------------------

    def detect_file_type(self, file_path: str) -> str:
        """Detect the type of a file based on extension and content analysis."""
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

        # JSON
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                json.load(f)
            return 'json'
        except (json.JSONDecodeError, UnicodeDecodeError):
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
        try:
            import chardet
            sample_size = 65536
            with open(file_path, 'rb') as f:
                raw = f.read(sample_size)
            result = chardet.detect(raw)
            encoding = (result.get('encoding') or 'utf-8').lower()
            confidence = float(result.get('confidence') or 0.0)
            return encoding, confidence
        except ImportError:
            pass

        for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    f.read(4096)
                return enc, 0.5
            except (UnicodeDecodeError, LookupError):
                continue
        return 'utf-8', 0.0

    def encoding_to_codepage(self, encoding: str) -> str:
        """Return the SQL Server codepage string for a given Python encoding name."""
        key = encoding.lower().strip()
        return self.CODEPAGE_MAP.get(key, 'ACP')

    # ------------------------------------------------------------------
    # Full metadata analysis
    # ------------------------------------------------------------------

    def analyze_file_metadata(self, file_path: str) -> Dict[str, Any]:
        """Analyse file metadata including schema, size, encoding and format details."""
        file_type = self.detect_file_type(file_path)
        if file_type in ('csv', 'text', 'json'):
            encoding, enc_confidence = self.detect_encoding(file_path)
        else:
            encoding, enc_confidence = 'binary', 1.0
        codepage = self.encoding_to_codepage(encoding)

        metadata: Dict[str, Any] = {
            'file_path': file_path,
            'file_name': os.path.basename(file_path),
            'file_type': file_type,
            'file_size': os.path.getsize(file_path),
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

        try:
            if file_type == 'csv':
                metadata.update(self._analyze_csv(file_path, encoding))
            elif file_type == 'parquet':
                metadata.update(self._analyze_parquet(file_path))
            elif file_type == 'delta':
                metadata.update(self._analyze_delta(file_path))
            elif file_type == 'json':
                metadata.update(self._analyze_json(file_path, encoding))
            elif file_type == 'excel':
                metadata.update(self._analyze_excel(file_path))
            elif file_type == 'text':
                metadata.update(self._analyze_text(file_path, encoding))
        except Exception as e:
            metadata['error'] = str(e)

        return metadata

    # ------------------------------------------------------------------
    # Per-format analyser helpers
    # ------------------------------------------------------------------

    def _analyze_csv(self, file_path: str, encoding: str = 'utf-8') -> Dict[str, Any]:
        """Analyse CSV / TSV file metadata."""
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

            df = pd.read_csv(file_path, nrows=200, encoding=encoding,
                             sep=delimiter, low_memory=False, on_bad_lines='skip')
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
                if file_size > 100 * 1024 * 1024:  # > 100 MB — estimate row count
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
        except Exception as e:
            logger.warning("Failed to analyze CSV %s: %s", file_path, e)
            result['error'] = str(e)
            result.setdefault('delimiter', ',')
            result.setdefault('has_header', False)
        return result

    def _analyze_parquet(self, file_path: str) -> Dict[str, Any]:
        """Analyse Parquet file metadata."""
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
                # Use pyarrow table slice to avoid loading entire dataset
                arrow_table = dt.to_pyarrow_table()
                row_count = arrow_table.num_rows
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
            return self._analyze_parquet(file_path)
        except Exception as e:
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
        """
        first = rows[0]
        schema: List[tuple] = []
        nesting: Dict[str, str] = {}
        sample_values: Dict[str, Any] = {}

        for key, val in first.items():
            # Determine nesting kind by scanning first non-null value across rows
            effective_val = val
            if effective_val is None:
                for r in rows[1:]:
                    if r.get(key) is not None:
                        effective_val = r[key]
                        break

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
        try:
            try:
                import openpyxl  # noqa: F401
                df = pd.read_excel(file_path, nrows=200, engine='openpyxl')
            except ImportError:
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
            }
        except Exception as e:
            return {'error': str(e)}

    # ------------------------------------------------------------------
    # Preview data (tabular)
    # ------------------------------------------------------------------

    def get_preview_data(self, file_path: str, max_rows: int = 100) -> Dict[str, Any]:
        """Return a tabular preview of the file as columns + rows."""
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
                df = pf.read().to_pandas().head(max_rows)

            elif file_type == 'delta':
                try:
                    from deltalake import DeltaTable  # type: ignore
                    dt = DeltaTable(file_path)
                    arrow_table = dt.to_pyarrow_table()
                    df = arrow_table.slice(0, max_rows).to_pandas()
                except ImportError:
                    pf = pq.ParquetFile(file_path)
                    df = pf.read().to_pandas().head(max_rows)

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
            safe_rows = [
                [str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v for v in row]
                for row in rows
            ]

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
            for file in files:
                file_path = os.path.join(root, file)
                file_type = self.detect_file_type(file_path)
                if file_type != 'unknown':
                    metadata = self.analyze_file_metadata(file_path)
                    results.append(metadata)
        return results
