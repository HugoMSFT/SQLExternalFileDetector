"""SQL DDL generator for external file formats and tables."""

import os
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class ExternalFileFormatConfig:
    """Configuration for external file format."""
    format_type: str
    field_terminator: Optional[str] = None
    string_delimiter: Optional[str] = None
    date_format: Optional[str] = None
    use_type_default: bool = False
    encoding: str = 'UTF8'
    first_row: int = 1
    data_compression: Optional[str] = None
    row_terminator: Optional[str] = None
    serialization_encoding: Optional[str] = None
    serializer_method: Optional[str] = None
    deserializer_method: Optional[str] = None


class SQLGenerator:
    """Generates T-SQL statements for CREATE TABLE, BULK INSERT, OPENROWSET, and CREATE EXTERNAL TABLE."""

    # Mapping from detected types to SQL Server data types
    TYPE_MAPPING = {
        'int64':         'BIGINT',
        'int32':         'INT',
        'int16':         'SMALLINT',
        'int8':          'TINYINT',
        'int':           'INT',
        'uint64':        'DECIMAL(20,0)',
        'uint32':        'BIGINT',
        'uint16':        'INT',
        'uint8':         'SMALLINT',
        'float64':       'FLOAT',
        'float32':       'REAL',
        'float':         'FLOAT',
        'double':        'FLOAT',
        'bool':          'BIT',
        'boolean':       'BIT',
        'object':        'NVARCHAR(255)',
        'str':           'NVARCHAR(255)',
        'string':        'NVARCHAR(255)',
        'large_string':  'NVARCHAR(MAX)',
        'datetime64[ns]':'DATETIME2(7)',
        'datetime64[us]':'DATETIME2(6)',
        'timestamp[us]': 'DATETIME2(6)',
        'timestamp[ns]': 'DATETIME2(7)',
        'timestamp':     'DATETIME2(7)',
        'date32':        'DATE',
        'date':          'DATE',
        'time':          'TIME(7)',
        'time64[us]':    'TIME(6)',
        'decimal128':    'DECIMAL(38,10)',
        'binary':        'VARBINARY(MAX)',
        'large_binary':  'VARBINARY(MAX)',
        'list':          'NVARCHAR(MAX)',        # JSON serialised
        'struct':        'NVARCHAR(MAX)',        # JSON serialised
        'dict':          'NVARCHAR(MAX)',
        'map':           'NVARCHAR(MAX)',
    }

    # Delimiter display names for comments
    DELIMITER_NAMES = {
        ',':  'comma',
        '\t': 'tab',
        '|':  'pipe',
        ';':  'semicolon',
        ' ':  'space',
    }

    # Supported target platforms
    PLATFORMS = (
        'sql_server_2019', 'sql_server_2022', 'sql_server_2025',
        'azure_sql_db', 'azure_sql_mi',
        'fabric_sql_db',
    )

    # Feature availability per platform.
    # Each key maps to a frozenset of platforms that support it.
    PLATFORM_FEATURES = {
        'create_table': frozenset({
            'sql_server_2019', 'sql_server_2022', 'sql_server_2025',
            'azure_sql_db', 'azure_sql_mi',
            'fabric_sql_db',
        }),
        'distribution': frozenset({              # DISTRIBUTION clause in CREATE TABLE

        }),
        'bulk_insert': frozenset({
            'sql_server_2019', 'sql_server_2022', 'sql_server_2025',
            'azure_sql_db', 'azure_sql_mi',
        }),
        'openrowset': frozenset({
            'sql_server_2019', 'sql_server_2022', 'sql_server_2025',
            'azure_sql_db', 'azure_sql_mi',

            'fabric_sql_db',
        }),
        'openrowset_format_keyword': frozenset({ # OPENROWSET(BULK ..., FORMAT = ...)
 'fabric_sql_db',
        }),
        'openrowset_bulk_local': frozenset({     # OPENROWSET(BULK '\\path')  local files
            'sql_server_2019', 'sql_server_2022', 'sql_server_2025',
        }),
        'openrowset_blob_storage': frozenset({   # OPENROWSET(BULK ..., DATA_SOURCE = blob_ds)
            'azure_sql_db', 'azure_sql_mi',
        }),
        'external_table': frozenset({
            'sql_server_2019', 'sql_server_2022', 'sql_server_2025',

        }),
        'copy_into': frozenset(),
        'credential_setup': frozenset({
            'sql_server_2019', 'sql_server_2022', 'sql_server_2025',

        }),
        'json_openjson': frozenset({             # OPENJSON, JSON_VALUE, JSON_QUERY, ISJSON
            'sql_server_2019', 'sql_server_2022', 'sql_server_2025',
            'azure_sql_db', 'azure_sql_mi',
            'fabric_sql_db',
        }),
        'json_path_exists': frozenset({          # JSON_PATH_EXISTS  (SQL Server 2022+)
            'sql_server_2022', 'sql_server_2025',
            'azure_sql_db', 'azure_sql_mi',
            'fabric_sql_db',
        }),
        'json_object_array': frozenset({         # JSON_OBJECT / JSON_ARRAY  (SQL Server 2022+)
            'sql_server_2022', 'sql_server_2025',
            'azure_sql_db', 'azure_sql_mi',
            'fabric_sql_db',
        }),
        'for_json': frozenset({
            'sql_server_2019', 'sql_server_2022', 'sql_server_2025',
            'azure_sql_db', 'azure_sql_mi',
            'fabric_sql_db',
        }),
    }

    # Human-readable platform labels
    PLATFORM_LABELS = {
        'sql_server_2019': 'SQL Server 2019',
        'sql_server_2022': 'SQL Server 2022',
        'sql_server_2025': 'SQL Server 2025',
        'azure_sql_db': 'Azure SQL Database',
        'azure_sql_mi': 'Azure SQL Managed Instance',
        'fabric_sql_db': 'Microsoft Fabric SQL Database',
    }

    def _supports(self, feature: str, platform: str) -> bool:
        """Return True if *platform* supports *feature*."""
        return platform in self.PLATFORM_FEATURES.get(feature, frozenset())

    def _not_supported_message(self, feature_label: str,
                               platform: str,
                               alternatives: str = '') -> str:
        """Return a comment block saying feature is not available."""
        label = self.PLATFORM_LABELS.get(platform, platform)
        lines = [
            f'-- ====================================================================',
            f'-- {feature_label}',
            f'-- NOT AVAILABLE on {label}',
            f'-- ====================================================================',
        ]
        if alternatives:
            lines.append(f'-- {alternatives}')
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # CREATE TABLE
    # ------------------------------------------------------------------

    def generate_create_table(self, metadata: Dict[str, Any],
                              table_name: str = None,
                              schema_name: str = 'dbo',
                              target_platform: str = 'sql_server_2022') -> str:
        """
        Generate a standard CREATE TABLE statement.

        Args:
            target_platform: One of the PLATFORMS tuple values.
        Nullable columns (detected from sample data) use NULL; others use NOT NULL.
        """
        if target_platform not in self.PLATFORMS:
            target_platform = 'sql_server_2022'

        if not self._supports('create_table', target_platform):
            return self._not_supported_message(
                'CREATE TABLE', target_platform,
                'Use CREATE EXTERNAL TABLE instead (see EXT TABLE tab).')

        if not table_name:
            base = os.path.splitext(os.path.basename(metadata['file_path']))[0]
            table_name = _clean_identifier(base)
        table_name = _escape_identifier(table_name)
        schema_name = _escape_identifier(schema_name)

        columns = self._generate_column_definitions(metadata, include_nullability=True)
        if not columns:
            columns = ['    [data] NVARCHAR(MAX) NULL']

        file_type = metadata.get('file_type', 'unknown').upper()
        file_name = metadata.get('file_name', metadata['file_path'])

        platform_label = self.PLATFORM_LABELS.get(target_platform, target_platform)

        lines = [
            f'-- ====================================================================',
            f'-- CREATE TABLE',
            f'-- Source : {file_name}  ({file_type})',
            f'-- Target : {platform_label}',
            f'-- ====================================================================',
            f'',
            f'CREATE TABLE [{schema_name}].[{table_name}]',
            f'(',
        ]
        lines.append(',\n'.join(columns))
        lines.append(f')')

        if self._supports('distribution', target_platform):
            lines += [
                f'WITH',
                f'(',
                f'    DISTRIBUTION = ROUND_ROBIN,    -- Change to HASH([col]) for large tables',
                f'    HEAP                           -- Change to CLUSTERED COLUMNSTORE INDEX for analytics',
                f');',
            ]
        else:
            # SQL Server / Azure SQL Database / MI / Fabric SQL DB
            lines.append(f';')

        # Append sample data as comments
        lines += self._format_sample_rows(metadata)

        # Append a commented-out INSERT INTO...SELECT FROM OPENROWSET as a quick-start
        file_name = metadata.get('file_name', metadata['file_path'])
        file_type = metadata.get('file_type', 'csv')
        blob_path = _quote_literal(f'https://<storage_account>.dfs.core.windows.net/<container>/<path>/{file_name}')
        format_kw = _format_keyword(file_type)

        lines += [
            '',
            '-- ====================================================================',
            '-- QUICK LOAD: INSERT INTO from OPENROWSET  (uncomment & customise)',
            '-- ====================================================================',
            f'-- INSERT INTO [{schema_name}].[{table_name}]',
            f'-- SELECT *',
            f'-- FROM OPENROWSET(',
            f'--     BULK \'{blob_path}\',',
            f'--     FORMAT = \'{format_kw}\'',
            f'-- ) AS src;',
        ]

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # BULK INSERT
    # ------------------------------------------------------------------

    def generate_bulk_insert(self, metadata: Dict[str, Any],
                             table_name: str = None,
                             schema_name: str = 'dbo',
                             file_path_override: str = None,
                             target_platform: str = 'sql_server_2022') -> str:
        """Generate a BULK INSERT statement (CSV / delimited text files only)."""
        if target_platform not in self.PLATFORMS:
            target_platform = 'sql_server_2022'

        if not self._supports('bulk_insert', target_platform):
            if target_platform == 'fabric_sql_db':
                file_name = metadata.get('file_name', metadata.get('file_path', 'file.csv'))
                detected_type = metadata.get('file_type', 'csv').upper()
                blob_path = _quote_literal(f'https://<storage_account>.dfs.core.windows.net/<container>/<path>/{file_name}')
                if not table_name:
                    base = os.path.splitext(os.path.basename(metadata.get('file_path', 'file')))[0]
                    table_name = _clean_identifier(base)
                table_name = _escape_identifier(table_name)

                return '\n'.join([
                    '-- ====================================================================',
                    '-- BULK INSERT',
                    '-- NOT AVAILABLE on Microsoft Fabric SQL Database',
                    '-- ====================================================================',
                    '-- Use OPENROWSET instead (Data Virtualization in Fabric SQL Database):',
                    '-- https://learn.microsoft.com/en-us/fabric/database/sql/data-virtualization',
                    '',
                    '-- Option 1: SELECT INTO from OPENROWSET (creates a new table)',
                    'SELECT *',
                    f'INTO [dbo].[stg_{table_name}]',
                    'FROM OPENROWSET(',
                    f'    BULK \'{blob_path}\',',
                    f"    FORMAT = '{_format_keyword(metadata.get('file_type', 'csv'))}'",
                    ') AS src;',
                    '',
                    '-- Option 2: INSERT INTO from OPENROWSET (loads an existing table)',
                    f'INSERT INTO [dbo].[{table_name}]',
                    'SELECT *',
                    'FROM OPENROWSET(',
                    f'    BULK \'{blob_path}\',',
                    f"    FORMAT = '{_format_keyword(metadata.get('file_type', 'csv'))}'",
                    ') AS src;',
                    '',
                    f'-- Detected source type: {detected_type}',
                    '-- For JSON payloads, combine OPENROWSET with OPENJSON (see JSON Functions tab).',
                ])

            label = self.PLATFORM_LABELS.get(target_platform, target_platform)
            alts = []
            if self._supports('copy_into', target_platform):
                alts.append('COPY INTO (see COPY INTO tab)')
            if self._supports('openrowset', target_platform):
                alts.append('OPENROWSET (see OPENROWSET tab)')
            if self._supports('external_table', target_platform):
                alts.append('CREATE EXTERNAL TABLE (see EXT TABLE tab)')
            alt_text = ', '.join(alts) if alts else 'Use the appropriate data loading method for your platform.'
            return self._not_supported_message(
                'BULK INSERT', target_platform,
                f'Alternative: {alt_text}')

        if not table_name:
            base = os.path.splitext(os.path.basename(metadata['file_path']))[0]
            table_name = _clean_identifier(base)
        table_name = _escape_identifier(table_name)
        schema_name = _escape_identifier(schema_name)

        file_type = metadata.get('file_type', '')
        file_path = (file_path_override or metadata['file_path']).replace('\\', '/')
        file_path_sql = _quote_literal(file_path)
        encoding = metadata.get('encoding', 'utf-8') or 'utf-8'
        codepage = metadata.get('codepage', '65001')

        if file_type not in ('csv', 'text'):
            return (
                f'-- BULK INSERT is designed for delimited text / CSV files.\n'
                f'-- This file is {file_type.upper()} — use OPENROWSET or CREATE EXTERNAL TABLE instead.\n'
            )

        delimiter = metadata.get('delimiter', ',') or ','
        has_header = metadata.get('has_header', True)
        first_row = 2 if has_header else 1
        delim_escaped = _quote_literal(delimiter.replace('\t', '\\t'))
        delim_name = self.DELIMITER_NAMES.get(delimiter, repr(delimiter))

        platform_label = self.PLATFORM_LABELS.get(target_platform, target_platform)
        use_for_note = 'High-speed batch load into ' + platform_label
        prereq_note = 'File must be accessible to the SQL Server service account'
        if target_platform == 'azure_sql_db':
            prereq_note = 'File must be in Azure Blob Storage accessible via SAS or database credential'
        elif target_platform == 'azure_sql_mi':
            prereq_note = 'File must be in Azure Blob Storage or a network share accessible to the MI'

        lines = [
            f'-- ====================================================================',
            f'-- BULK INSERT',
            f'-- Source    : {metadata.get("file_name", file_path)}',
            f'-- Encoding  : {encoding.upper()}  (codepage {codepage})',
            f'-- Delimiter : {delim_name}  (\\"{delim_escaped}\\")',
            f'-- Target   : {platform_label}',
            f'-- Use for   : {use_for_note}',
            f'-- Prereq    : {prereq_note}',
            f'-- ====================================================================',
            f'',
            f'-- Step 1: Create the target table (see CREATE TABLE tab)',
            f'',
            f'-- Step 2: Load the data',
            f'BULK INSERT [{schema_name}].[{table_name}]',
            f'FROM N\'{file_path_sql}\'',
            f'WITH',
            f'(',
            f'    FORMAT          = \'CSV\',         -- SQL Server 2017 +',
            f'    FIRSTROW        = {first_row},',
            f'    FIELDTERMINATOR = \'{delim_escaped}\',',
            f'    ROWTERMINATOR   = \'0x0a\',        -- LF  (use \'\\r\\n\' for Windows line endings)',
            f'    CODEPAGE        = \'{codepage}\',  -- {encoding.upper()}',
            f'    TABLOCK,                            -- Minimally logged; remove if concurrent inserts needed',
            f'    MAXERRORS       = 0,               -- Fail on first error; increase for tolerant loads',
            f'    BATCHSIZE       = 50000            -- Tune per available memory',
            f');',
            f'',
            f'-- Verify row count',
            f'SELECT COUNT(*) AS loaded_rows FROM [{schema_name}].[{table_name}];',
        ]
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # OPENROWSET
    # ------------------------------------------------------------------

    def generate_openrowset(self, metadata: Dict[str, Any],
                            storage_url: str = None,
                            credential_name: str = 'MyStorageCredential',
                            target_platform: str = 'sql_server_2022') -> str:
        """
        Generate OPENROWSET queries.
        Supports CSV, Parquet, Delta, JSON.
        """
        if target_platform not in self.PLATFORMS:
            target_platform = 'sql_server_2022'

        if not self._supports('openrowset', target_platform):
            alts = []
            if self._supports('bulk_insert', target_platform):
                alts.append('BULK INSERT (see BULK INSERT tab)')
            if self._supports('json_openjson', target_platform):
                alts.append('JSON functions (see JSON Functions tab)')
            alt_text = ', '.join(alts) if alts else 'Use the appropriate data access method for your platform.'
            return self._not_supported_message(
                'OPENROWSET', target_platform,
                f'Alternative: {alt_text}')

        is_cloud = target_platform in self.PLATFORM_FEATURES['openrowset_format_keyword']
        is_local = target_platform in self.PLATFORM_FEATURES['openrowset_bulk_local']
        file_type = metadata.get('file_type', 'csv')
        file_name = metadata.get('file_name', metadata['file_path'])
        encoding = metadata.get('encoding', 'utf-8') or 'utf-8'
        codepage = metadata.get('codepage', '65001')
        delimiter = metadata.get('delimiter', ',') or ','
        has_header = metadata.get('has_header', True)
        delim_escaped = _quote_literal(delimiter.replace('\t', '\\t'))

        blob_path = _quote_literal(storage_url or f'https://<storage_account>.dfs.core.windows.net/<container>/<path>/{file_name}')
        local_path = _quote_literal(metadata['file_path'].replace('\\', '/'))

        platform_label = self.PLATFORM_LABELS.get(target_platform, target_platform)
        lines = [
            f'-- ====================================================================',
            f'-- OPENROWSET',
            f'-- Source  : {file_name}  ({file_type.upper()})',
            f'-- Target  : {platform_label}',
            f'-- Use for : Ad-hoc / exploratory queries without creating a table',
            f'-- ====================================================================',
            f'',
        ]

        # For on-prem SQL Server, generate OPENROWSET(BULK 'local_path') syntax
        if is_local and not is_cloud:
            return self._generate_openrowset_local(
                metadata, lines, local_path, target_platform)

        # Azure SQL DB / MI — OPENROWSET(BULK) with BLOB_STORAGE data source
        is_blob_storage = target_platform in self.PLATFORM_FEATURES.get('openrowset_blob_storage', frozenset())
        if is_blob_storage:
            return self._generate_openrowset_blob_storage(
                metadata, lines, blob_path, target_platform)

        # Cloud path (Synapse / Fabric DW) — existing logic
        if file_type == 'parquet':
            lines += [
                f'-- ---- Parquet (Synapse Serverless) ------------------------------------------',
                f'SELECT TOP 100 *',
                f'FROM OPENROWSET(',
                f'    BULK \'{blob_path}\',',
                f'    FORMAT = \'PARQUET\'',
                f') AS [result];',
                f'',
                f'-- ---- Parquet with explicit credential ----------------------------------------',
                f'SELECT TOP 100 *',
                f'FROM OPENROWSET(',
                f'    BULK \'{blob_path}\',',
                f'    DATA_SOURCE = \'MyADLS\',      -- Created via CREATE EXTERNAL DATA SOURCE',
                f'    FORMAT = \'PARQUET\'',
                f') WITH (',
            ]
            cols = self._generate_column_definitions(metadata, indent=4)
            lines.append(',\n'.join(cols) if cols else '    [data] NVARCHAR(MAX)')
            lines += [
                f') AS [result];',
                f'',
                f'-- ---- Wildcard folder scan ---------------------------------------------------',
                f'SELECT *',
                f'FROM OPENROWSET(',
                f'    BULK \'{blob_path.rsplit("/", 1)[0]}/**\',',
                f'    FORMAT = \'PARQUET\'',
                f') AS [result];',
            ]

        elif file_type == 'delta':
            lines += [
                f'-- ---- Delta Lake (Synapse Serverless) ----------------------------------------',
                f'-- Delta Lake is read via the DELTA format keyword (preview as of 2024)',
                f'SELECT TOP 100 *',
                f'FROM OPENROWSET(',
                f'    BULK \'{blob_path}\',',
                f'    FORMAT = \'DELTA\'',
                f') AS [result];',
                f'',
                f'-- Or use the dedicated OPENROWSET syntax for Delta:',
                f'SELECT TOP 100 *',
                f'FROM OPENROWSET(',
                f'    BULK \'{blob_path.rsplit("/", 1)[0]}/\',',
                f'    FORMAT = \'DELTA\'',
                f') AS [result];',
            ]

        elif file_type == 'json':
            json_format = metadata.get('json_format', 'array')
            nesting = metadata.get('json_nesting') or {}
            schema = metadata.get('schema') or []

            # Build JSON_VALUE / JSON_QUERY column list from real schema
            jv_cols = []
            for col_name, col_type in schema:
                clean = _clean_identifier(col_name)
                kind = nesting.get(col_name, 'scalar')
                if kind == 'object':
                    jv_cols.append(f'    JSON_QUERY(doc, \'{_quote_json_path(col_name)}\') AS [{clean}]')
                elif kind == 'array':
                    jv_cols.append(f'    JSON_QUERY(doc, \'{_quote_json_path(col_name)}\') AS [{clean}]')
                else:
                    sql_t = self._map_type_to_sql(col_type)
                    jv_cols.append(f'    JSON_VALUE(doc, \'{_quote_json_path(col_name)}\') AS [{clean}]')
            jv_select = ',\n'.join(jv_cols) if jv_cols else '    JSON_VALUE(doc, \'$.id\') AS [id]'

            if json_format == 'ndjson':
                # NDJSON: each line is a JSON document
                lines += [
                    f'-- ---- NDJSON / JSON Lines (Synapse Serverless) ----------------------------',
                    f'-- Each line is an independent JSON document',
                    f'SELECT TOP 100',
                    jv_select,
                    f'FROM OPENROWSET(',
                    f'    BULK \'{blob_path}\',',
                    f'    FORMAT          = \'CSV\',',
                    f'    FIELDTERMINATOR = \'0x0b\',',
                    f'    FIELDQUOTE      = \'0x0b\',',
                    f'    ROWTERMINATOR   = \'0x0a\'   -- LF: one JSON object per line',
                    f') WITH (doc NVARCHAR(MAX)) AS [src];',
                ]
            else:
                # JSON array / single object
                lines += [
                    f'-- ---- JSON (Synapse Serverless) — load whole file as single CLOB ----------',
                    f'SELECT TOP 100',
                    jv_select,
                    f'FROM OPENROWSET(',
                    f'    BULK \'{blob_path}\',',
                    f'    FORMAT          = \'CSV\',',
                    f'    FIELDTERMINATOR = \'0x0b\',',
                    f'    FIELDQUOTE      = \'0x0b\',',
                    f'    ROWTERMINATOR   = \'0x0b\'',
                    f') WITH (doc NVARCHAR(MAX)) AS [src];',
                ]

            # CROSS APPLY OPENJSON with typed WITH clause
            openjson_cols = self._generate_openjson_columns(metadata, indent=4)
            lines += [
                f'',
                f'-- ---- JSON → relational (CROSS APPLY OPENJSON with typed columns) -----------',
                f'SELECT j.*',
                f'FROM OPENROWSET(',
                f'    BULK \'{blob_path}\',',
                f'    FORMAT          = \'CSV\',',
                f'    FIELDTERMINATOR = \'0x0b\',',
                f'    FIELDQUOTE      = \'0x0b\'',
                f') WITH (json_doc NVARCHAR(MAX)) AS [src]',
                f'CROSS APPLY OPENJSON(src.json_doc)',
                f'WITH (',
            ]
            lines.append(',\n'.join(openjson_cols) if openjson_cols else '    [data] NVARCHAR(MAX)')
            lines += [f') AS j;']

        else:  # CSV / text
            lines += [
                f'-- ---- CSV (Synapse Serverless, PARSER_VERSION 2.0) --------------------------',
                f'SELECT TOP 100 *',
                f'FROM OPENROWSET(',
                f'    BULK \'{blob_path}\',',
                f'    FORMAT          = \'CSV\',',
                f'    PARSER_VERSION  = \'2.0\',       -- Faster parser for simple CSV',
                f'    HEADER_ROW      = {"TRUE" if has_header else "FALSE"},',
                f'    FIELDTERMINATOR = \'{delim_escaped}\',',
                f'    ROWTERMINATOR   = \'\\n\',',
                f'    CODEPAGE        = \'{codepage}\'  -- {encoding.upper()}',
                f') AS [result];',
                f'',
                f'-- ---- CSV with explicit schema (SQL Server PolyBase / Synapse) ---------------',
                f'SELECT TOP 100 *',
                f'FROM OPENROWSET(',
                f'    BULK \'{blob_path}\',',
                f'    FORMAT          = \'CSV\',',
                f'    FIRSTROW        = {2 if has_header else 1},',
                f'    FIELDTERMINATOR = \'{delim_escaped}\',',
                f'    ROWTERMINATOR   = \'\\n\',',
                f'    CODEPAGE        = \'{codepage}\'',
                f') WITH (',
            ]
            cols = self._generate_column_definitions(metadata, indent=4)
            lines.append(',\n'.join(cols) if cols else '    [data] NVARCHAR(MAX)')
            lines += [f') AS [result];']

        lines += [
            f'',
            f'-- ---- Create a reusable VIEW -------------------------------------------------------',
            f'CREATE OR ALTER VIEW [dbo].[vw_{_clean_identifier(os.path.splitext(file_name)[0])}] AS',
            f'SELECT *',
            f'FROM OPENROWSET(',
            f'    BULK \'{blob_path}\',',
            f'    FORMAT = \'{_format_keyword(file_type)}\'',
            f') AS [result];',
        ]
        return '\n'.join(lines)

    def _generate_openrowset_local(self, metadata: Dict[str, Any],
                                   lines: List[str],
                                   local_path: str,
                                   target_platform: str) -> str:
        """Generate OPENROWSET(BULK ...) for on-prem SQL Server using local file paths."""
        file_type = metadata.get('file_type', 'csv')
        encoding = metadata.get('encoding', 'utf-8') or 'utf-8'
        codepage = metadata.get('codepage', '65001')
        delimiter = metadata.get('delimiter', ',') or ','
        has_header = metadata.get('has_header', True)
        delim_escaped = _quote_literal(delimiter.replace('\t', '\\t'))
        file_name = metadata.get('file_name', metadata['file_path'])

        if file_type in ('csv', 'text'):
            lines += [
                f'-- ---- CSV via OPENROWSET(BULK) — SQL Server local file -------------------',
                f'SELECT TOP 100 *',
                f'FROM OPENROWSET(',
                f'    BULK N\'{local_path}\',',
                f'    FORMATFILE = N\'<path_to_format_file.xml>\',',
                f'    CODEPAGE   = \'{codepage}\',  -- {encoding.upper()}',
                f'    FIRSTROW   = {2 if has_header else 1}',
                f') AS [result];',
                f'',
                f'-- ---- Alternative: ad-hoc with SINGLE_CLOB (small files) ---',
                f'SELECT BulkColumn',
                f'FROM OPENROWSET(BULK N\'{local_path}\', SINGLE_CLOB) AS [src];',
            ]
        elif file_type == 'json':
            lines += [
                f'-- ---- JSON via SINGLE_CLOB + OPENJSON  (SQL Server 2016+) ---------------',
                f'DECLARE @json NVARCHAR(MAX);',
                f'SELECT @json = BulkColumn',
                f'FROM OPENROWSET(BULK N\'{local_path}\', SINGLE_CLOB) AS [src];',
                f'',
                f'SELECT * FROM OPENJSON(@json)',
            ]
            openjson_cols = self._generate_openjson_columns(metadata, indent=4)
            if openjson_cols:
                lines += [
                    f'WITH (',
                    ',\n'.join(openjson_cols),
                    f');',
                ]
            else:
                lines.append(f';')
        elif file_type == 'parquet':
            lines += [
                f'-- SQL Server does not natively read Parquet files via OPENROWSET.',
                f'-- Options:',
                f'--   1. Use PolyBase with CREATE EXTERNAL TABLE (see EXT TABLE tab)',
                f'--   2. Convert to CSV before loading',
                f'--   3. Use Python/R integration (sp_execute_external_script)',
            ]
        elif file_type == 'delta':
            lines += [
                f'-- SQL Server does not natively read Delta Lake files.',
                f'-- Options:',
                f'--   1. Use Azure Synapse Serverless with FORMAT = \'DELTA\'',
                f'--   2. Convert to Parquet/CSV before loading',
            ]

        return '\n'.join(lines)

    def _generate_openrowset_blob_storage(self, metadata: Dict[str, Any],
                                          lines: List[str],
                                          blob_path: str,
                                          target_platform: str) -> str:
        """Generate OPENROWSET(BULK) for Azure SQL DB / MI using BLOB_STORAGE data source."""
        file_type = metadata.get('file_type', 'csv')
        encoding = metadata.get('encoding', 'utf-8') or 'utf-8'
        codepage = metadata.get('codepage', '65001')
        delimiter = metadata.get('delimiter', ',') or ','
        has_header = metadata.get('has_header', True)
        delim_escaped = _quote_literal(delimiter.replace('\t', '\\t'))
        platform_label = self.PLATFORM_LABELS.get(target_platform, target_platform)

        lines += [
            f'-- Prerequisite: Create an EXTERNAL DATA SOURCE of type BLOB_STORAGE.',
            f'-- This allows {platform_label} to read files from Azure Blob Storage.',
            f'--',
            f'-- CREATE MASTER KEY ENCRYPTION BY PASSWORD = \'<strong_password>\';',
            f'--',
            f'-- CREATE DATABASE SCOPED CREDENTIAL [BlobCredential]',
            f'-- WITH IDENTITY = \'SHARED ACCESS SIGNATURE\',',
            f'--      SECRET = \'<sas_token_without_leading_?>\';',
            f'--',
            f'-- CREATE EXTERNAL DATA SOURCE [BlobDS]',
            f'-- WITH (',
            f'--     TYPE = BLOB_STORAGE,',
            f'--     LOCATION = \'https://<storage_account>.blob.core.windows.net/<container>\',',
            f'--     CREDENTIAL = [BlobCredential]',
            f'-- );',
            f'',
        ]

        if file_type in ('csv', 'text'):
            lines += [
                f'-- ---- CSV via OPENROWSET(BULK) with BLOB_STORAGE data source ---------------',
                f'SELECT TOP 100 *',
                f'FROM OPENROWSET(',
                f'    BULK \'{blob_path}\',',
                f'    DATA_SOURCE = \'BlobDS\',',
                f'    FORMATFILE  = \'<format_file.xml>\',',
                f'    FORMATFILE_DATA_SOURCE = \'BlobDS\'',
                f') AS [result];',
                f'',
                f'-- ---- Alternative: SINGLE_CLOB for small files -----------------------------',
                f'SELECT BulkColumn',
                f'FROM OPENROWSET(',
                f'    BULK \'{blob_path}\',',
                f'    DATA_SOURCE = \'BlobDS\',',
                f'    SINGLE_CLOB',
                f') AS [src];',
            ]
        elif file_type == 'json':
            lines += [
                f'-- ---- JSON via SINGLE_CLOB + OPENJSON --------------------------------------',
                f'DECLARE @json NVARCHAR(MAX);',
                f'SELECT @json = BulkColumn',
                f'FROM OPENROWSET(',
                f'    BULK \'{blob_path}\',',
                f'    DATA_SOURCE = \'BlobDS\',',
                f'    SINGLE_CLOB',
                f') AS [src];',
                f'',
                f'SELECT * FROM OPENJSON(@json)',
            ]
            openjson_cols = self._generate_openjson_columns(metadata, indent=4)
            if openjson_cols:
                lines += [
                    f'WITH (',
                    ',\n'.join(openjson_cols),
                    f');',
                ]
            else:
                lines.append(f';')
        elif file_type == 'parquet':
            lines += [
                f'-- {platform_label} does not natively support Parquet via OPENROWSET.',
                f'-- Options:',
                f'--   1. Convert Parquet to CSV (e.g., pandas, Azure Data Factory)',
                f'--   2. Use Azure Synapse Serverless for direct Parquet queries',
                f'--   3. Use PolyBase on SQL Server for external Parquet tables',
            ]
        elif file_type == 'delta':
            lines += [
                f'-- {platform_label} does not support Delta Lake format.',
                f'-- Use Azure Synapse Serverless with FORMAT = \'DELTA\' instead.',
            ]

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # CREATE EXTERNAL FILE FORMAT
    # ------------------------------------------------------------------

    def generate_external_file_format(self, metadata: Dict[str, Any],
                                      format_name: str = None,
                                      target_platform: str = 'sql_server_2022') -> str:
        """Generate CREATE EXTERNAL FILE FORMAT statement."""
        if target_platform not in self.PLATFORMS:
            target_platform = 'sql_server_2022'

        if not self._supports('external_table', target_platform):
            return self._not_supported_message(
                'CREATE EXTERNAL FILE FORMAT', target_platform,
                'External tables are not available on this platform.')

        if not format_name:
            format_name = f'ff_{metadata["file_type"]}_format'
        format_name = _escape_identifier(format_name)

        config = self._determine_format_config(metadata)
        format_options = [f'    FORMAT_TYPE = {config.format_type}']

        if config.field_terminator:
            format_options.append(f'    FIELD_TERMINATOR = \'{_quote_literal(config.field_terminator)}\'')
        if config.string_delimiter:
            format_options.append(f'    STRING_DELIMITER = \'{_quote_literal(config.string_delimiter)}\'')
        if config.date_format:
            format_options.append(f'    DATE_FORMAT = \'{_quote_literal(config.date_format)}\'')
        if config.use_type_default:
            format_options.append(f'    USE_TYPE_DEFAULT = TRUE')
        if config.encoding and config.encoding != 'UTF8':
            format_options.append(f'    ENCODING = \'{_quote_literal(config.encoding)}\'')
        if config.first_row != 1:
            format_options.append(f'    FIRST_ROW = {config.first_row}')
        if config.data_compression:
            format_options.append(f'    DATA_COMPRESSION = \'{_quote_literal(config.data_compression)}\'')
        if config.row_terminator:
            format_options.append(f'    ROW_TERMINATOR = \'{_quote_literal(config.row_terminator)}\'')
        if config.serialization_encoding:
            format_options.append(f'    SERIALIZATION_ENCODING = \'{_quote_literal(config.serialization_encoding)}\'')
        if config.serializer_method:
            format_options.append(f'    SERIALIZER_METHOD = \'{_quote_literal(config.serializer_method)}\'')
        if config.deserializer_method:
            format_options.append(f'    DESERIALIZER_METHOD = \'{_quote_literal(config.deserializer_method)}\'')

        sql_parts = [
            f'-- CREATE EXTERNAL FILE FORMAT  (PolyBase / Synapse Dedicated or Serverless)',
            f'CREATE EXTERNAL FILE FORMAT [{format_name}]',
            f'WITH (',
            ',\n'.join(format_options),
            f');',
        ]
        return '\n'.join(sql_parts)

    # ------------------------------------------------------------------
    # CREATE EXTERNAL TABLE
    # ------------------------------------------------------------------

    def generate_external_table(self, metadata: Dict[str, Any],
                                table_name: str = None,
                                data_source: str = None,
                                location: str = None,
                                file_format: str = None,
                                schema_name: str = 'dbo',
                                target_platform: str = 'sql_server_2022') -> str:
        """Generate CREATE EXTERNAL TABLE statement (PolyBase / Synapse)."""
        if target_platform not in self.PLATFORMS:
            target_platform = 'sql_server_2022'

        if not self._supports('external_table', target_platform):
            # Fabric SQL DB — cannot use external tables but has alternatives
            if target_platform == 'fabric_sql_db':
                return '\n'.join([
                    '-- ====================================================================',
                    '-- CREATE EXTERNAL TABLE  (Microsoft Fabric SQL Database)',
                    '-- ====================================================================',
                    '-- CREATE EXTERNAL TABLE is not natively supported on Fabric SQL Database.',
                    '-- However, you can access external data through these Fabric features:',
                    '--',
                    '-- 1. Fabric Shortcuts',
                    '--    Create a shortcut in your Lakehouse or Warehouse to ADLS Gen2,',
                    '--    S3, or Dataverse. Data appears as a managed table without copying.',
                    '--    https://learn.microsoft.com/fabric/onelake/onelake-shortcuts',
                    '--',
                    '-- 2. Mirroring',
                    '--    Mirror data from Azure SQL, Cosmos DB, Snowflake, etc. into Fabric',
                    '--    for near-real-time replication without building ETL.',
                    '--    https://learn.microsoft.com/fabric/database/mirrored-database/',
                    '--',
                    '-- 3. Cross-warehouse queries',
                    '--    Query data across Fabric SQL DB, Warehouse, and Lakehouse using',
                    '--    three-part names:  [workspace].[schema].[table]',
                    '--',
                    '-- 4. Dataflows Gen2 / Data Pipelines',
                    '--    Use no-code/low-code options to ingest data from 100+ sources.',
                    '--    https://learn.microsoft.com/fabric/data-factory/',
                    '--',
                    '-- In Fabric SQL Database, use OPENROWSET for external reads and',
                    '-- INSERT INTO ... SELECT FROM OPENROWSET for loading.',
                    '-- For JSON payloads, use OPENROWSET + OPENJSON (see JSON Functions tab).',
                ])
            alts = []
            if self._supports('bulk_insert', target_platform):
                alts.append('BULK INSERT (see BULK INSERT tab)')
            if self._supports('json_openjson', target_platform):
                alts.append('JSON functions (see JSON Functions tab)')
            alt_text = ', '.join(alts) if alts else 'Use the appropriate data access method.'
            return self._not_supported_message(
                'CREATE EXTERNAL TABLE', target_platform,
                f'Alternative: {alt_text}')

        if not table_name:
            base = os.path.splitext(os.path.basename(metadata['file_path']))[0]
            table_name = f'ext_{_clean_identifier(base)}'
        if not location:
            location = metadata['file_path']
        if not file_format:
            file_format = f'ff_{metadata["file_type"]}_format'
        table_name = _escape_identifier(table_name)
        schema_name = _escape_identifier(schema_name)
        file_format = _escape_identifier(file_format)
        if data_source:
            data_source = _escape_identifier(data_source)

        columns = self._generate_column_definitions(metadata, include_nullability=False)
        if not columns:
            columns = ['    [data] NVARCHAR(MAX)']

        with_options = []
        if data_source:
            with_options.append(f'    DATA_SOURCE = [{data_source}]')
        with_options.append(f'    LOCATION = \'{_quote_literal(location)}\'')
        with_options.append(f'    FILE_FORMAT = [{file_format}]')
        with_options.append(f'    REJECT_TYPE = VALUE')
        with_options.append(f'    REJECT_VALUE = 0')

        platform_label = self.PLATFORM_LABELS.get(target_platform, target_platform)
        sql_parts = [
            f'-- ====================================================================',
            f'-- CREATE EXTERNAL TABLE  ({platform_label})',
            f'-- Prereq: CREATE EXTERNAL DATA SOURCE and CREATE EXTERNAL FILE FORMAT',
            f'-- ====================================================================',
            f'',
            f'CREATE EXTERNAL TABLE [{schema_name}].[{table_name}]',
            f'(',
            ',\n'.join(columns),
            f')',
            f'WITH',
            f'(',
            ',\n'.join(with_options),
            f');',
        ]
        return '\n'.join(sql_parts)

    # ------------------------------------------------------------------
    # COPY INTO  (Synapse Dedicated Pool / Fabric Data Warehouse)
    # ------------------------------------------------------------------

    def generate_copy_into(self, metadata: Dict[str, Any],
                           table_name: str = None,
                           schema_name: str = 'dbo',
                           storage_url: str = None,
                           target_platform: str = 'sql_server_2022') -> str:
        """Generate a COPY INTO statement (Synapse Dedicated Pool / Fabric DW)."""
        if target_platform not in self.PLATFORMS:
            target_platform = 'sql_server_2022'

        if not self._supports('copy_into', target_platform):
            if target_platform in {
                'sql_server_2019', 'sql_server_2022', 'sql_server_2025',
                'azure_sql_db', 'azure_sql_mi', 'fabric_sql_db'
            }:
                platform_label = self.PLATFORM_LABELS.get(target_platform, target_platform)
                lines = [
                    '-- ====================================================================',
                    '-- COPY INTO',
                    f'-- NOT AVAILABLE on {platform_label}',
                    '-- ====================================================================',
                    '-- Recommended alternatives:',
                ]
                if self._supports('bulk_insert', target_platform):
                    lines.append('-- 1. BULK INSERT for high-speed CSV/text ingestion (see BULK INSERT tab).')
                if self._supports('openrowset', target_platform):
                    lines += [
                        '-- 2. OPENROWSET for ad-hoc reads and ELT patterns (see OPENROWSET tab).',
                        '--    Use SELECT INTO or INSERT INTO ... SELECT FROM OPENROWSET for loading.',
                    ]
                if self._supports('json_openjson', target_platform):
                    lines.append('-- 3. OPENJSON / JSON_VALUE for JSON ingestion (see JSON Functions tab).')
                if target_platform == 'fabric_sql_db':
                    lines.append('-- 4. Fabric Data Pipelines / Dataflows Gen2 for orchestrated ingestion.')
                return '\n'.join(lines)

            alts = []
            if self._supports('bulk_insert', target_platform):
                alts.append('BULK INSERT (see BULK INSERT tab)')
            if self._supports('openrowset', target_platform):
                alts.append('OPENROWSET (see OPENROWSET tab)')
            if self._supports('external_table', target_platform):
                alts.append('CREATE EXTERNAL TABLE (see EXT TABLE tab)')
            alt_text = ', '.join(alts) if alts else 'Use the appropriate data loading method.'
            return self._not_supported_message(
                'COPY INTO', target_platform,
                f'Alternative: {alt_text}')

        if not table_name:
            base = os.path.splitext(os.path.basename(metadata['file_path']))[0]
            table_name = _clean_identifier(base)
        table_name = _escape_identifier(table_name)
        schema_name = _escape_identifier(schema_name)

        file_type = metadata.get('file_type', 'csv')
        file_name = metadata.get('file_name', metadata['file_path'])
        encoding = metadata.get('encoding', 'utf-8') or 'utf-8'
        delimiter = metadata.get('delimiter', ',') or ','
        has_header = metadata.get('has_header', True)
        delim_escaped = _quote_literal(delimiter.replace('\t', '\\t'))
        blob_path = _quote_literal(storage_url or f'https://<storage_account>.blob.core.windows.net/<container>/<path>/{file_name}')

        platform_label = self.PLATFORM_LABELS.get(target_platform, target_platform)
        lines = [
            f'-- ====================================================================',
            f'-- COPY INTO  ({platform_label})',
            f'-- Source : {file_name}  ({file_type.upper()})',
            f'-- Prereq : Table must exist; see CREATE TABLE tab',
            f'-- ====================================================================',
            f'',
        ]

        if file_type in ('csv', 'text'):
            lines += [
                f'COPY INTO [{schema_name}].[{table_name}]',
                f'FROM \'{blob_path}\'',
                f'WITH (',
                f'    FILE_TYPE       = \'CSV\',',
                f'    FIRSTROW        = {2 if has_header else 1},',
                f'    FIELDTERMINATOR = \'{delim_escaped}\',',
                f'    ROWTERMINATOR   = \'0x0a\',',
                f'    ENCODING        = \'{encoding.upper()}\',',
                f'    CREDENTIAL      = (IDENTITY = \'Storage Account Key\',',
                f'                       SECRET   = \'<your_storage_account_key>\')',
                f');',
            ]
        elif file_type == 'parquet':
            lines += [
                f'COPY INTO [{schema_name}].[{table_name}]',
                f'FROM \'{blob_path}\'',
                f'WITH (',
                f'    FILE_TYPE  = \'PARQUET\',',
                f'    CREDENTIAL = (IDENTITY = \'Storage Account Key\',',
                f'                  SECRET   = \'<your_storage_account_key>\')',
                f');',
            ]
        elif file_type == 'json':
            lines += [
                f'-- COPY INTO does not natively support JSON file type in Synapse.',
                f'-- Option 1: Convert JSON to Parquet using pandas / Spark, then COPY INTO.',
                f'-- Option 2: Use OPENROWSET + OPENJSON (see JSON Functions tab).',
                f'-- Option 3: Use Azure Data Factory to flatten JSON and load as CSV.',
            ]
        elif file_type == 'delta':
            lines += [
                f'-- COPY INTO does not support Delta Lake directly.',
                f'-- Use CREATE EXTERNAL TABLE with FORMAT_TYPE = DELTA instead,',
                f'-- or read via OPENROWSET FORMAT = \'DELTA\' in Synapse Serverless.',
            ]
        else:
            lines += [
                f'COPY INTO [{schema_name}].[{table_name}]',
                f'FROM \'{blob_path}\'',
                f'WITH (',
                f'    FILE_TYPE  = \'CSV\',',
                f'    CREDENTIAL = (IDENTITY = \'Storage Account Key\',',
                f'                  SECRET   = \'<your_storage_account_key>\')',
                f');',
            ]

        lines += [
            f'',
            f'-- Verify row count after load',
            f'SELECT COUNT(*) AS loaded_rows FROM [{schema_name}].[{table_name}];',
        ]
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # CREDENTIAL + DATA SOURCE setup
    # ------------------------------------------------------------------

    def generate_credential_setup(self, data_source: str = 'MyDataSource',
                                  file_format: str = 'ff_csv_format',
                                  metadata: Dict[str, Any] = None,
                                  target_platform: str = 'sql_server_2022') -> str:
        """Generate prerequisite CREATE CREDENTIAL, CREATE EXTERNAL DATA SOURCE,
        and CREATE EXTERNAL FILE FORMAT statements."""
        if target_platform not in self.PLATFORMS:
            target_platform = 'sql_server_2022'

        if not self._supports('credential_setup', target_platform):
            return self._not_supported_message(
                'CREDENTIAL / DATA SOURCE SETUP', target_platform,
                'External data sources are not supported on this platform. '
                'Use BULK INSERT or application-level data loading instead.')

        platform_label = self.PLATFORM_LABELS.get(target_platform, target_platform)
        file_type = (metadata or {}).get('file_type', 'csv')
        data_source = _escape_identifier(data_source)
        lines = [
            f'-- ====================================================================',
            f'-- PREREQUISITE SETUP  ({platform_label})',
            f'-- Run these ONCE before using CREATE EXTERNAL TABLE or OPENROWSET',
            f'-- with a DATA_SOURCE reference.',
            f'-- ====================================================================',
            f'',
            f'-- 1. Master key (required once per database)',
            f'IF NOT EXISTS (SELECT * FROM sys.symmetric_keys WHERE name = \'##MS_DatabaseMasterKey##\')',
            f'    CREATE MASTER KEY ENCRYPTION BY PASSWORD = \'<StrongPassword!>\';',
            f'GO',
            f'',
            f'-- 2. Database Scoped Credential',
            f'--    Choose ONE authentication method and uncomment:',
            f'',
            f'-- Option A: Storage Account Key',
            f'CREATE DATABASE SCOPED CREDENTIAL [cred_{data_source}]',
            f'WITH',
            f'    IDENTITY = \'Storage Account Key\',',
            f'    SECRET   = \'<your_storage_account_key>\';',
            f'GO',
            f'',
            f'-- Option B: Managed Identity (no secret needed)',
            f'-- CREATE DATABASE SCOPED CREDENTIAL [cred_{data_source}]',
            f'-- WITH IDENTITY = \'Managed Identity\';',
            f'-- GO',
            f'',
            f'-- Option C: Shared Access Signature (SAS token)',
            f'-- CREATE DATABASE SCOPED CREDENTIAL [cred_{data_source}]',
            f'-- WITH',
            f'--     IDENTITY = \'SHARED ACCESS SIGNATURE\',',
            f'--     SECRET   = \'<SAS_token_without_leading_?>\';',
            f'-- GO',
            f'',
            f'-- 3. External Data Source',
            f'CREATE EXTERNAL DATA SOURCE [{data_source}]',
            f'WITH (',
            f'    TYPE     = HADOOP,                      -- Use BLOB_STORAGE for BULK INSERT with SAS',
            f'    LOCATION = \'https://<storage_account>.dfs.core.windows.net/<container>\',',
            f'    CREDENTIAL = [cred_{data_source}]',
            f');',
            f'GO',
        ]

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # JSON Functions  (OPENJSON, JSON_VALUE, JSON_QUERY, ISJSON, etc.)
    # ------------------------------------------------------------------

    def generate_json_functions(self, metadata: Dict[str, Any],
                                table_name: str = None,
                                schema_name: str = 'dbo',
                                target_platform: str = 'sql_server_2022') -> str:
        """Generate comprehensive T-SQL JSON function examples using the file's real schema."""
        if target_platform not in self.PLATFORMS:
            target_platform = 'sql_server_2022'

        if not self._supports('json_openjson', target_platform):
            alts = []
            if self._supports('openrowset', target_platform):
                alts.append('OPENROWSET (see OPENROWSET tab)')
            if self._supports('external_table', target_platform):
                alts.append('CREATE EXTERNAL TABLE (see EXT TABLE tab)')
            alt_text = ', '.join(alts) if alts else 'JSON functions may have limited support on this platform.'
            return self._not_supported_message(
                'JSON FUNCTIONS (OPENJSON / JSON_VALUE / JSON_QUERY)',
                target_platform,
                f'Alternative: {alt_text}')

        has_path_exists = self._supports('json_path_exists', target_platform)
        has_json_object = self._supports('json_object_array', target_platform)
        is_on_prem = target_platform.startswith('sql_server_')
        has_openrowset_cloud = self._supports('openrowset_format_keyword', target_platform)

        platform_label = self.PLATFORM_LABELS.get(target_platform, target_platform)
        file_type = metadata.get('file_type', 'csv')
        file_name = metadata.get('file_name', metadata.get('file_path', 'file'))
        json_format = metadata.get('json_format', 'array')
        nesting = metadata.get('json_nesting') or {}
        schema = metadata.get('schema') or []

        if not table_name:
            base = os.path.splitext(os.path.basename(metadata.get('file_path', 'data')))[0]
            table_name = _clean_identifier(base)
        table_name = _escape_identifier(table_name)
        schema_name = _escape_identifier(schema_name)

        file_path_sql = metadata.get('file_path', r'C:/data/file.json').replace('\\', '/').replace("'", "''")

        lines = [
            f'-- ====================================================================',
            f'-- T-SQL JSON FUNCTIONS  —  {file_name}',
            f'-- Target  : {platform_label}',
            f'-- JSON format : {json_format.upper()}',
            f'-- Columns     : {len(schema)}',
            f'-- ====================================================================',
            f'',
        ]

        # ---- Section 1: SINGLE_CLOB + OPENJSON  (SQL Server 2016+) ------
        openjson_cols = self._generate_openjson_columns(metadata, indent=8)
        openjson_with = ',\n'.join(openjson_cols) if openjson_cols else '        [data] NVARCHAR(MAX)'

        lines += [
            f'-- ----------------------------------------------------------------',
            f'-- 1. OPENROWSET(BULK) + OPENJSON  (SQL Server 2016+ / Azure SQL)',
            f'--    Loads the entire file as a single string, then parses as JSON.',
            f'-- ----------------------------------------------------------------',
            f'DECLARE @json NVARCHAR(MAX);',
            f'SELECT @json = BulkColumn',
            f'FROM OPENROWSET(BULK N\'{file_path_sql}\', SINGLE_CLOB) AS j;',
            f'',
        ]

        if json_format == 'object':
            # Single object: direct JSON_VALUE
            lines += [
                f'-- Single JSON object — extract individual values',
                f'SELECT',
            ]
            jv = []
            for col_name, col_type in schema:
                clean = _clean_identifier(col_name)
                kind = nesting.get(col_name, 'scalar')
                if kind in ('object', 'array'):
                    jv.append(f'    JSON_QUERY(@json, \'{_quote_json_path(col_name)}\') AS [{clean}]')
                else:
                    jv.append(f'    JSON_VALUE(@json, \'{_quote_json_path(col_name)}\') AS [{clean}]')
            lines.append(',\n'.join(jv) + ';' if jv else '    @json;')
        else:
            lines += [
                f'-- Parse the JSON array into rows with typed columns',
                f'SELECT *',
                f'FROM OPENJSON(@json)',
                f'WITH (',
                openjson_with,
                f');',
            ]

        # ---- Section 2: OPENJSON without schema (key/value/type) ---------
        lines += [
            f'',
            f'-- ----------------------------------------------------------------',
            f'-- 2. OPENJSON — schemaless (key / value / type discovery)',
            f'-- ----------------------------------------------------------------',
            f'SELECT [key], [value], [type]',
            f'FROM OPENJSON(@json);',
        ]

        # ---- Section 3: Nested objects — JSON_QUERY + CROSS APPLY --------
        nested_cols = [(n, k) for n, k in nesting.items() if k in ('object', 'array')]
        if nested_cols:
            lines += [
                f'',
                f'-- ----------------------------------------------------------------',
                f'-- 3. NESTED OBJECTS / ARRAYS  — CROSS APPLY OPENJSON',
                f'-- ----------------------------------------------------------------',
            ]
            for col_name, kind in nested_cols:
                clean = _clean_identifier(col_name)
                lines += [
                    f'',
                    f'-- Expand nested {"array" if kind == "array" else "object"}: $.{col_name}',
                    f'SELECT',
                    f'    parent.[key] AS parent_key,',
                    f'    child.[key]  AS child_key,',
                    f'    child.[value] AS child_value',
                    f'FROM OPENJSON(@json) AS parent',
                    f'CROSS APPLY OPENJSON(parent.[value], \'{_quote_json_path(col_name)}\') AS child;',
                ]

        # ---- Section 4: Validation with ISJSON --------------------------
        lines += [
            f'',
            f'-- ----------------------------------------------------------------',
            f'-- 4. VALIDATE JSON  — ISJSON  (SQL Server 2016+)',
            f'-- ----------------------------------------------------------------',
            f'SELECT',
            f'    ISJSON(@json) AS is_valid_json,',
            f'    CASE ISJSON(@json) WHEN 1 THEN \'Valid\' ELSE \'Invalid\' END AS status;',
        ]

        # ---- Section 5: JSON_PATH_EXISTS  (SQL Server 2022+ / Azure SQL) ---
        if schema and has_path_exists:
            first_col = schema[0][0]
            lines += [
                f'',
                f'-- ----------------------------------------------------------------',
                f'-- 5. JSON_PATH_EXISTS  ({platform_label})',
                f'-- ----------------------------------------------------------------',
                f'SELECT JSON_PATH_EXISTS(@json, \'{_quote_json_path(first_col)}\') AS path_exists;',
            ]
        elif schema and not has_path_exists:
            lines += [
                f'',
                f'-- ----------------------------------------------------------------',
                f'-- 5. JSON_PATH_EXISTS  — NOT available on {platform_label}',
                f'--    Requires SQL Server 2022+ or Azure SQL Database',
                f'-- ----------------------------------------------------------------',
            ]

        # ---- Section 6: JSON_MODIFY  (update values) --------------------
        if schema:
            first_col = schema[0][0]
            lines += [
                f'',
                f'-- ----------------------------------------------------------------',
                f'-- 6. JSON_MODIFY  — update a value in the JSON document',
                f'-- ----------------------------------------------------------------',
                f'SET @json = JSON_MODIFY(@json, \'{_quote_json_path(first_col)}\', \'new_value\');',
                f'-- Verify: SELECT JSON_VALUE(@json, \'{_quote_json_path(first_col)}\');',
            ]

        # ---- Section 7: Cloud OPENROWSET + OPENJSON  (Synapse / Fabric) ---
        if has_openrowset_cloud:
            blob_path = _quote_literal(f'https://<storage_account>.dfs.core.windows.net/<container>/<path>/{file_name}')
            lines += [
                f'',
                f'-- ----------------------------------------------------------------',
                f'-- 7. CLOUD OPENROWSET + OPENJSON  ({platform_label})',
                f'-- ----------------------------------------------------------------',
                f'SELECT j.*',
                f'FROM OPENROWSET(',
                f'    BULK \'{blob_path}\',',
                f'    FORMAT          = \'CSV\',',
                f'    FIELDTERMINATOR = \'0x0b\',',
                f'    FIELDQUOTE      = \'0x0b\'',
                f') WITH (json_doc NVARCHAR(MAX)) AS src',
                f'CROSS APPLY OPENJSON(src.json_doc)',
                f'WITH (',
            ]
            lines.append(',\n'.join(openjson_cols) if openjson_cols else '    [data] NVARCHAR(MAX)')
            lines += [f') AS j;']
        elif is_on_prem:
            lines += [
                f'',
                f'-- ----------------------------------------------------------------',
                f'-- 7. Cloud OPENROWSET syntax is not available on {platform_label}.',
                f'--    Use Section 1 (SINGLE_CLOB + OPENJSON) for local JSON files.',
                f'-- ----------------------------------------------------------------',
            ]

        # ---- Section 8: INSERT parsed JSON into table -------------------
        if schema:
            insert_cols = ', '.join(f'[{_clean_identifier(c)}]' for c, _ in schema if nesting.get(c, 'scalar') == 'scalar')
            if insert_cols:
                lines += [
                    f'',
                    f'-- ----------------------------------------------------------------',
                    f'-- 8. INSERT parsed JSON into [{schema_name}].[{table_name}]',
                    f'--    (create the table first — see CREATE TABLE tab)',
                    f'-- ----------------------------------------------------------------',
                    f'INSERT INTO [{schema_name}].[{table_name}] ({insert_cols})',
                    f'SELECT {insert_cols}',
                    f'FROM OPENJSON(@json)',
                    f'WITH (',
                    openjson_with,
                    f');',
                ]

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # FOR JSON PATH  (SQL → JSON export)
    # ------------------------------------------------------------------

    def generate_for_json_path(self, metadata: Dict[str, Any],
                               table_name: str = None,
                               schema_name: str = 'dbo',
                               target_platform: str = 'sql_server_2022') -> str:
        """Generate FOR JSON PATH examples for SQL-to-JSON export."""
        if target_platform not in self.PLATFORMS:
            target_platform = 'sql_server_2022'

        if not self._supports('for_json', target_platform):
            return self._not_supported_message(
                'FOR JSON PATH', target_platform,
                'FOR JSON is not available on Data Warehouse platforms. '
                'Use application-level JSON serialisation instead.')

        has_json_object = self._supports('json_object_array', target_platform)
        platform_label = self.PLATFORM_LABELS.get(target_platform, target_platform)

        if not table_name:
            base = os.path.splitext(os.path.basename(metadata.get('file_path', 'data')))[0]
            table_name = _clean_identifier(base)
        root_label = _quote_literal(table_name)  # literal context (FOR JSON ROOT)
        table_name = _escape_identifier(table_name)
        schema_name = _escape_identifier(schema_name)
        schema = metadata.get('schema') or []
        nesting = metadata.get('json_nesting') or {}

        select_cols = []
        for col_name, _ in schema:
            clean = _clean_identifier(col_name)
            kind = nesting.get(col_name, 'scalar')
            if kind in ('object', 'array'):
                select_cols.append(f'    JSON_QUERY([{clean}]) AS [{_escape_identifier(col_name)}]')
            else:
                select_cols.append(f'    [{clean}] AS [{_escape_identifier(col_name)}]')

        cols_str = ',\n'.join(select_cols) if select_cols else '    *'

        lines = [
            f'-- ====================================================================',
            f'-- FOR JSON PATH  — export SQL rows back to JSON',
            f'-- Target : {platform_label}',
            f'-- ====================================================================',
            f'',
            f'-- 1. Basic array output (each row = one JSON object)',
            f'SELECT',
            cols_str,
            f'FROM [{schema_name}].[{table_name}]',
            f'FOR JSON PATH;',
            f'',
            f'-- 2. Wrapped in a root element',
            f'SELECT',
            cols_str,
            f'FROM [{schema_name}].[{table_name}]',
            f'FOR JSON PATH, ROOT(\'{root_label}\');',
            f'',
            f'-- 3. Include NULL values in output (omitted by default)',
            f'SELECT',
            cols_str,
            f'FROM [{schema_name}].[{table_name}]',
            f'FOR JSON PATH, INCLUDE_NULL_VALUES;',
            f'',
            f'-- 4. Single object (without array wrapper)',
            f'SELECT TOP 1',
            cols_str,
            f'FROM [{schema_name}].[{table_name}]',
            f'FOR JSON PATH, WITHOUT_ARRAY_WRAPPER;',
        ]

        if has_json_object:
            lines += [
                f'',
                f'-- 5. JSON_OBJECT / JSON_ARRAY  ({platform_label})',
                f'SELECT',
                f'    JSON_OBJECT(',
            ]
            jo_pairs = [f'        \'{_quote_literal(col_name)}\': [{_clean_identifier(col_name)}]' for col_name, _ in schema[:6]]
            lines.append(',\n'.join(jo_pairs) if jo_pairs else '        \'data\': *')
            lines += [
                f'    ) AS json_row',
                f'FROM [{schema_name}].[{table_name}];',
            ]
        else:
            lines += [
                f'',
                f'-- 5. JSON_OBJECT / JSON_ARRAY  — NOT available on {platform_label}',
                f'--    Requires SQL Server 2022+ or Azure SQL Database',
            ]

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # BEST PRACTICES
    # ------------------------------------------------------------------

    def generate_best_practices(self, metadata: Dict[str, Any],
                                target_platform: str = 'sql_server_2022') -> str:
        """Generate a best-practices guide for ingesting / querying this file type."""
        if target_platform not in self.PLATFORMS:
            target_platform = 'sql_server_2022'

        platform_label = self.PLATFORM_LABELS.get(target_platform, target_platform)
        file_type = metadata.get('file_type', 'csv')
        file_name = metadata.get('file_name', 'file')
        row_count = metadata.get('row_count')
        encoding = (metadata.get('encoding') or 'utf-8').upper()
        compression = metadata.get('compression')
        delimiter = metadata.get('delimiter', ',')
        has_header = metadata.get('has_header', True)

        size_bytes = metadata.get('file_size', 0)
        size_mb = (size_bytes or 0) / 1024 / 1024
        size_label = f'{size_mb:.1f} MB'

        rows_label = f'{row_count:}' if row_count else 'unknown'
        default_table_name = _clean_identifier(os.path.splitext(file_name)[0] or 'data')

        lines = [
            '-- ====================================================================',
            f'-- BEST PRACTICES  —  {file_name}',
            f'-- Target   : {platform_label}',
            f'-- File type : {file_type.upper()}',
            f'-- File size : {size_label}',
            f'-- Row count : {rows_label}',
            f'-- Encoding  : {encoding}',
            '-- ====================================================================',
            '',
        ]

        lines += _best_practices_summary(metadata, target_platform, size_mb)
        warnings = _best_practices_warnings(metadata)
        if warnings:
            lines += warnings

        # Platform-specific loading recommendation
        load_methods = []
        if self._supports('copy_into', target_platform):
            load_methods.append('COPY INTO (fastest for bulk loads)')
        if self._supports('bulk_insert', target_platform):
            load_methods.append('BULK INSERT (high-speed batch loads)')
        if self._supports('openrowset', target_platform):
            load_methods.append('OPENROWSET (ad-hoc / exploratory queries)')
        if self._supports('external_table', target_platform):
            load_methods.append('CREATE EXTERNAL TABLE (persistent virtual table)')
        if self._supports('json_openjson', target_platform) and file_type == 'json':
            load_methods.append('OPENJSON / JSON_VALUE (native JSON parsing)')
        if self._supports('for_json', target_platform):
            load_methods.append('FOR JSON PATH (export to JSON)')

        if load_methods:
            lines += [
                f'-- RECOMMENDED LOADING METHODS for {platform_label}:',
            ]
            for i, m in enumerate(load_methods, 1):
                lines.append(f'--   {i}. {m}')
            lines.append('')

        if file_type == 'csv':
            lines += _best_practices_csv(size_mb, encoding, delimiter, has_header, compression)
        elif file_type == 'parquet':
            lines += _best_practices_parquet(size_mb, compression, metadata)
        elif file_type == 'delta':
            lines += _best_practices_delta(metadata)
        elif file_type == 'json':
            lines += _best_practices_json(size_mb)
        else:
            lines += _best_practices_generic()

        lines += _best_practices_validation_sql(metadata, default_table_name)

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Complete DDL (all statements)
    # ------------------------------------------------------------------

    def generate_complete_ddl(self, metadata: Dict[str, Any],
                              table_name: str = None,
                              data_source: str = None,
                              location: str = None,
                              schema_name: str = 'dbo') -> str:
        """Legacy: return all DDL as a single string (kept for backward compatibility)."""
        return self.generate_all_statements(metadata, table_name, data_source,
                                            location, schema_name).get('create_external_table', '')

    def generate_all_statements(self, metadata: Dict[str, Any],
                                table_name: str = None,
                                data_source: str = 'MyDataSource',
                                location: str = None,
                                schema_name: str = 'dbo',
                                target_platform: str = 'sql_server_2022',
                                storage_url: str = None) -> Dict[str, str]:
        """
        Return a dictionary with all generated SQL statement types:
            create_table, bulk_insert, openrowset, copy_into,
            external_file_format, create_external_table,
            json_functions, for_json, best_practices
        """
        if not table_name:
            base = os.path.splitext(os.path.basename(metadata['file_path']))[0]
            table_name = _clean_identifier(base)

        fmt_name = f'ff_{metadata.get("file_type", "csv")}_format'
        loc = location or os.path.basename(metadata['file_path'])

        return {
            'create_table': self.generate_create_table(metadata, table_name, schema_name,
                                                       target_platform=target_platform),
            'bulk_insert': self.generate_bulk_insert(metadata, table_name, schema_name,
                                                     target_platform=target_platform),
            'openrowset': self.generate_openrowset(metadata,
                                                   storage_url=storage_url,
                                                   target_platform=target_platform),
            'copy_into': self.generate_copy_into(metadata, table_name, schema_name,
                                                 storage_url=storage_url,
                                                 target_platform=target_platform),
            'external_file_format': self.generate_external_file_format(metadata, fmt_name,
                                                                       target_platform=target_platform),
            'create_external_table': self.generate_external_table(
                metadata, table_name, data_source, loc, fmt_name, schema_name,
                target_platform=target_platform,
            ),
            'json_functions': self.generate_json_functions(metadata, table_name, schema_name,
                                                          target_platform=target_platform),
            'for_json': self.generate_for_json_path(metadata, table_name, schema_name,
                                                    target_platform=target_platform),
            'credential_setup': self.generate_credential_setup(data_source, fmt_name,
                                                               metadata=metadata,
                                                               target_platform=target_platform),
            'best_practices': self.generate_best_practices(metadata,
                                                           target_platform=target_platform),
        }

    # ------------------------------------------------------------------
    # Sample data comments
    # ------------------------------------------------------------------

    @staticmethod
    def _format_sample_rows(metadata: Dict[str, Any]) -> List[str]:
        """Return sample data rows as SQL comments for context."""
        sample_rows = metadata.get('sample_rows')
        schema = metadata.get('schema')
        json_samples = metadata.get('json_sample_values')

        if not schema:
            return []

        lines: List[str] = []

        # For CSV/Excel with sample_rows
        if sample_rows and len(sample_rows) > 0:
            col_names = [c[0] for c in schema]
            # Truncate wide tables to first 8 columns for readability
            max_display = 8
            truncated = len(col_names) > max_display
            display_cols = col_names[:max_display]
            lines.append('')
            lines.append('-- Sample data (first rows from file):')
            header = ' | '.join(str(n)[:20] for n in display_cols)
            if truncated:
                header += f' | ... ({len(col_names) - max_display} more)'
            lines.append(f'-- {header}')
            lines.append(f'-- {"-" * len(header)}')
            for row in sample_rows[:3]:
                display_vals = row[:max_display]
                vals = ' | '.join(str(v if v is not None else 'NULL')[:20] for v in display_vals)
                if truncated:
                    vals += ' | ...'
                lines.append(f'-- {vals}')

        # For JSON with json_sample_values
        elif json_samples:
            lines.append('')
            lines.append('-- Sample data (first record):')
            for col_name, _ in schema[:10]:
                val = json_samples.get(col_name, '')
                val_str = str(val)[:60]
                lines.append(f'--   {col_name}: {val_str}')

        return lines

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _determine_format_config(self, metadata: Dict[str, Any]) -> ExternalFileFormatConfig:
        file_type = metadata.get('file_type', 'text')
        encoding = (metadata.get('encoding') or 'utf-8').upper()
        # Normalise encoding to SQL Server keyword
        if encoding in ('UTF-8', 'UTF_8', 'UTF8-SIG', 'UTF-8-SIG'):
            encoding = 'UTF8'
        elif encoding in ('UTF-16', 'UTF_16'):
            encoding = 'UTF16'

        if file_type == 'csv':
            delimiter = metadata.get('delimiter', ',') or ','
            has_header = metadata.get('has_header', False)
            return ExternalFileFormatConfig(
                format_type='DELIMITEDTEXT',
                field_terminator=delimiter.replace('\t', '\\t'),
                string_delimiter='"',
                first_row=2 if has_header else 1,
                encoding=encoding,
                use_type_default=True,
            )
        elif file_type == 'json':
            return ExternalFileFormatConfig(format_type='JSON')
        elif file_type == 'parquet':
            comp = (metadata.get('compression') or '').upper()
            return ExternalFileFormatConfig(
                format_type='PARQUET',
                data_compression=comp if comp and comp != 'UNCOMPRESSED' else None,
            )
        elif file_type == 'delta':
            return ExternalFileFormatConfig(format_type='DELTA')
        elif file_type == 'orc':
            return ExternalFileFormatConfig(format_type='ORC', data_compression='DEFAULT')
        elif file_type == 'rc':
            return ExternalFileFormatConfig(
                format_type='RCFILE',
                serialization_encoding='UTF8',
                serializer_method='org.apache.hadoop.hive.serde2.columnar.ColumnarSerDe',
                deserializer_method='org.apache.hadoop.hive.serde2.columnar.ColumnarSerDe',
            )
        else:
            return ExternalFileFormatConfig(format_type='DELIMITEDTEXT',
                                            field_terminator='\\n',
                                            encoding=encoding)

    def _generate_column_definitions(self, metadata: Dict[str, Any],
                                     include_nullability: bool = False,
                                     indent: int = 4) -> List[str]:
        schema = metadata.get('schema')
        if not schema:
            return []
        nullable_set = set(metadata.get('nullable_columns') or [])
        max_lengths = metadata.get('max_string_lengths') or {}
        sql_type_overrides = metadata.get('sql_type_overrides') or {}
        pad = ' ' * indent
        columns = []
        for col_name, col_type in schema:
            clean_name = _clean_identifier(col_name)
            # Use explicit SQL type override if provided by schema editor
            if col_name in sql_type_overrides:
                sql_type = _safe_sql_type(sql_type_overrides[col_name])
            else:
                sql_type = self._map_type_to_sql(col_type, max_length=max_lengths.get(col_name))
            if include_nullability:
                null_kw = 'NULL' if col_name in nullable_set else 'NOT NULL'
                columns.append(f'{pad}[{clean_name}] {sql_type:<22} {null_kw}')
            else:
                columns.append(f'{pad}[{clean_name}] {sql_type}')
        return columns

    def _generate_openjson_columns(self, metadata: Dict[str, Any],
                                    indent: int = 4) -> List[str]:
        """Build WITH-clause column list for OPENJSON.

        Uses json_nesting to emit ``AS JSON`` for nested objects/arrays.
        """
        schema = metadata.get('schema') or []
        nesting = metadata.get('json_nesting') or {}
        max_lengths = metadata.get('max_string_lengths') or {}
        sql_type_overrides = metadata.get('sql_type_overrides') or {}
        pad = ' ' * indent
        cols: List[str] = []
        for col_name, col_type in schema:
            clean = _clean_identifier(col_name)
            kind = nesting.get(col_name, 'scalar')
            if kind in ('object', 'array'):
                cols.append(f'{pad}[{clean}] NVARCHAR(MAX) \'{_quote_json_path(col_name)}\' AS JSON')
            else:
                if col_name in sql_type_overrides:
                    sql_type = _safe_sql_type(sql_type_overrides[col_name])
                else:
                    sql_type = self._map_type_to_sql(col_type,
                                                     max_length=max_lengths.get(col_name))
                cols.append(f'{pad}[{clean}] {sql_type} \'{_quote_json_path(col_name)}\'')
        return cols

    def _map_type_to_sql(self, data_type: str, max_length: int = None) -> str:
        data_type_lower = str(data_type).lower()
        # Exact match first
        if data_type_lower in self.TYPE_MAPPING:
            sql_type = self.TYPE_MAPPING[data_type_lower]
            # Override NVARCHAR(255) with a smarter size when string length data exists
            if sql_type == 'NVARCHAR(255)' and max_length is not None:
                if max_length > 4000:
                    return 'NVARCHAR(MAX)'
                elif max_length > 200:
                    # Round up to a nice boundary
                    size = ((max_length // 50) + 1) * 50
                    return f'NVARCHAR({min(size, 4000)})'
            return sql_type
        # Substring match
        for key, sql_type in self.TYPE_MAPPING.items():
            if key.lower() in data_type_lower:
                return sql_type
        # decimal(p, s) passthrough
        if 'decimal' in data_type_lower or 'numeric' in data_type_lower:
            return 'DECIMAL(18,4)'
        return 'NVARCHAR(255)'


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _clean_identifier(name: str) -> str:
    """Clean a name so it is a valid SQL identifier."""
    clean = re.sub(r'[^A-Za-z0-9_]', '_', str(name))
    if clean and clean[0].isdigit():
        clean = 'col_' + clean
    return clean or 'column_1'


def _escape_identifier(name: str) -> str:
    """Escape a value for safe use inside a T-SQL bracket-quoted ``[identifier]``.

    Bracket-quoting requires that any closing bracket be doubled so a value can
    never terminate the identifier early. Unlike :func:`_clean_identifier`, the
    original characters are preserved so caller-supplied names (table, schema,
    data source, ...) keep their intended form while remaining injection-safe.
    """
    return str(name).replace(']', ']]')


def _quote_literal(value: Any) -> str:
    """Escape a value for safe use inside a T-SQL single-quoted ``'string'`` literal."""
    return str(value).replace("'", "''")


_SIMPLE_JSON_KEY = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _quote_json_path(name: str) -> str:
    """Build a safe T-SQL JSON path (``$.<key>``) for *name*.

    Simple identifiers are emitted as ``$.key``. Names containing spaces, dots
    or other special characters are wrapped in double quotes (``$."weird key"``)
    as required by SQL Server. The result is additionally escaped so it is safe
    to embed inside a single-quoted SQL string literal.
    """
    n = str(name)
    if _SIMPLE_JSON_KEY.match(n):
        path = f'$.{n}'
    else:
        esc = n.replace('\\', '\\\\').replace('"', '\\"')
        path = f'$."{esc}"'
    return path.replace("'", "''")


# Allowed shape for a SQL data type: a type name optionally followed by a
# parenthesised length/precision such as NVARCHAR(255), DECIMAL(18,4) or
# VARBINARY(MAX). Anything else (e.g. a value smuggled in from the web schema
# editor) is rejected and replaced with a safe default.
_VALID_SQL_TYPE = re.compile(
    r'^[A-Za-z][A-Za-z0-9_]*\s*(\(\s*(\d+|MAX)\s*(,\s*\d+\s*)?\))?$',
    re.IGNORECASE,
)


def _safe_sql_type(sql_type: str, fallback: str = 'NVARCHAR(MAX)') -> str:
    """Return *sql_type* only if it matches the allowed type pattern, else *fallback*."""
    candidate = str(sql_type).strip()
    return candidate if _VALID_SQL_TYPE.match(candidate) else fallback


def _format_keyword(file_type: str) -> str:
    return {'parquet': 'PARQUET', 'delta': 'DELTA', 'json': 'CSV',
            'orc': 'ORC'}.get(file_type, 'CSV')


def _best_practices_summary(metadata: Dict[str, Any],
                            target_platform: str,
                            size_mb: float) -> List[str]:
    file_type = metadata.get('file_type', 'csv')

    recommended = 'CREATE TABLE + INSERT validation flow'
    fastest = 'OPENROWSET for preview / exploratory access'
    lowest_cost = 'OPENROWSET with projection/filtering'
    staging = 'Load to a staging table first, then transform into the final schema'

    if target_platform == 'fabric_sql_db':
        recommended = 'OPENROWSET with SELECT INTO / INSERT INTO ... SELECT'
        fastest = 'OPENROWSET for direct external access'
        lowest_cost = 'OPENROWSET over parquet with projected columns'
    elif target_platform.startswith('sql_server_') or target_platform in {'azure_sql_db', 'azure_sql_mi'}:
        if file_type in {'csv', 'text'}:
            recommended = 'BULK INSERT for load, then validate in SQL'
            fastest = 'BULK INSERT for local or staged CSV/text files'
        elif file_type == 'json':
            recommended = 'OPENJSON / OPENROWSET(SINGLE_CLOB) for controlled parsing'
            fastest = 'OPENJSON after loading the file as NVARCHAR(MAX)'
        elif file_type in {'parquet', 'delta'}:
            recommended = 'Use OPENROWSET or convert to CSV/Parquet depending on platform limits'
            fastest = 'OPENROWSET when supported; otherwise convert before load'

    if size_mb > 512:
        staging = 'For large files, land data in staging and validate in batches'
    elif size_mb < 25:
        staging = 'For small files, direct load is fine, but keep a validation query ready'

    return [
        '-- RECOMMENDED PATH',
        f'--   Best option   : {recommended}',
        f'--   Fastest path  : {fastest}',
        f'--   Lowest cost   : {lowest_cost}',
        f'--   Staging       : {staging}',
        '',
    ]


def _best_practices_warnings(metadata: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    encoding = metadata.get('encoding')
    confidence = metadata.get('encoding_confidence')
    file_type = metadata.get('file_type', 'csv')
    json_nesting = metadata.get('json_nesting') or {}
    max_lengths = metadata.get('max_string_lengths') or {}
    nullable = set(metadata.get('nullable_columns') or [])
    schema = metadata.get('schema') or []

    if encoding and encoding != 'binary' and confidence is not None and confidence < 70:
        warnings.append(f'--   Low encoding confidence ({confidence}%). Verify file encoding before loading.')
    if metadata.get('row_count_estimated'):
        warnings.append('--   Row count is estimated. Validate with a post-load COUNT(*) query.')
    if file_type == 'json' and any(kind in {'object', 'array'} for kind in json_nesting.values()):
        warnings.append('--   Nested JSON detected. Expect flattening or OPENJSON WITH (...) work before production load.')
    if any(length > 4000 for length in max_lengths.values()):
        warnings.append('--   Very long strings detected. Consider NVARCHAR(MAX) columns and downstream truncation checks.')

    numeric_markers = ('int', 'float', 'double', 'decimal', 'numeric', 'real')
    nullable_numeric = [name for name, dtype in schema if name in nullable and any(m in str(dtype).lower() for m in numeric_markers)]
    if nullable_numeric:
        warnings.append(f'--   Nullable numeric columns detected: {", ".join(nullable_numeric[:5])}. Stage as text if source quality is inconsistent.')

    if not warnings:
        return []

    return ['-- WARNINGS / WATCH-OUTS', *warnings, '']


def _best_practices_validation_sql(metadata: Dict[str, Any],
                                   table_name: str) -> List[str]:
    schema = metadata.get('schema') or []
    cols = [_clean_identifier(col) for col, _ in schema[:3]]
    select_cols = ', '.join(f'[{c}]' for c in cols) if cols else '*'

    lines = [
        '-- VALIDATION SQL AFTER LOAD',
        f'-- 1. Row count',
        f'SELECT COUNT(*) AS loaded_rows FROM [dbo].[{table_name}];',
        '',
        f'-- 2. Sample rows',
        f'SELECT TOP 10 {select_cols} FROM [dbo].[{table_name}];',
    ]

    if cols:
        null_checks = ', '.join(
            f'SUM(CASE WHEN [{c}] IS NULL THEN 1 ELSE 0 END) AS [{c}_nulls]'
            for c in cols
        )
        lines += [
            '',
            '-- 3. Null distribution check',
            f'SELECT {null_checks} FROM [dbo].[{table_name}];',
        ]

    lines.append('')
    return lines


def _best_practices_csv(size_mb: float, encoding: str, delimiter: str,
                        has_header: bool, compression: str) -> List[str]:
    delim_name = {',' : 'comma', '\t': 'tab', '|': 'pipe', ';': 'semicolon'}.get(delimiter, repr(delimiter))
    lines = [
        f'-- Detected: {delim_name}-delimited, encoding {encoding}',
        '',
        '-- 1. TOOL SELECTION',
        '--    < 1 GB   → BULK INSERT into SQL Server / Azure SQL (fastest local load)',
        '--    1–50 GB  → COPY INTO (Synapse Dedicated Pool, highest throughput)',
        '--    > 50 GB  → OPENROWSET or CREATE EXTERNAL TABLE (avoid materialising data)',
        '',
        '-- 2. ENCODING',
        f'--    Detected encoding : {encoding}',
        '--    Always specify CODEPAGE in BULK INSERT to avoid silent data corruption.',
        '--    UTF-8 → CODEPAGE = \'65001\'   |   UTF-16 → CODEPAGE = \'1200\'',
        '--    Latin-1 / CP1252 → CODEPAGE = \'1252\'',
        '',
        '-- 3. HEADER ROW',
        f'--    has_header = {has_header} → {"FIRSTROW = 2 (skip header)" if has_header else "FIRSTROW = 1 (no header detected)"}',
        '',
        '-- 4. STAGING PATTERN (recommended)',
        '--    a. Load raw data into a STAGING table (all columns NVARCHAR).',
        '--    b. Validate / transform via CTAS into the final typed table.',
        '--    c. This avoids cryptic conversion errors on bad rows.',
        '',
        '-- 5. PERFORMANCE',
        '--    Split large files into 256 MB chunks before importing.',
        '--    Use TABLOCK + BATCHSIZE for minimal logging.',
        '--    Pre-sort by the partition key when possible.',
        '',
        '-- 6. ERROR HANDLING',
        '--    Use MAXERRORS to log bad rows before aborting.',
        '--    Pair with ERRORFILE to capture rejected rows for inspection.',
        '',
        '-- 7. COPY INTO (Synapse Dedicated Pool — fastest bulk load)',
        '--    Requires data to be in Azure Data Lake Storage or Blob Storage.',
        '--    COPY INTO [dbo].[MyTable]',
        '--    FROM \'https://<storage>.blob.core.windows.net/<container>/<file.csv>\'',
        '--    WITH (',
        f'--        FILE_TYPE = \'CSV\',',
        f'--        FIRSTROW = {2 if has_header else 1},',
        f'--        FIELDTERMINATOR = \'{delimiter}\',',
        '--        CREDENTIAL = (IDENTITY = \'Storage Account Key\', SECRET = \'<key>\')',
        '--    );',
    ]
    return lines


def _best_practices_parquet(size_mb: float, compression: str,
                             metadata: Dict[str, Any]) -> List[str]:
    row_groups = (metadata.get('parquet_metadata') or {}).get('num_row_groups', 'unknown')
    comp_label = compression or 'UNCOMPRESSED'
    lines = [
        f'-- Detected: Parquet, compression={comp_label}, row_groups={row_groups}',
        '',
        '-- 1. TOOL SELECTION',
        '--    Synapse Serverless → OPENROWSET (zero-copy, pay-per-query)',
        '--    Synapse Dedicated  → CREATE EXTERNAL TABLE + CTAS to load',
        '--    SQL Server 2022+   → OPENROWSET with PolyBase',
        '',
        '-- 2. COMPRESSION',
        f'--    Detected: {comp_label}',
        '--    Snappy → best balance of speed and ratio (recommended for analytics)',
        '--    ZSTD   → better compression, requires pyarrow/Spark write options',
        '--    LZ4    → fastest decompression, slightly larger files',
        '--    Avoid GZIP for Parquet in PolyBase/Synapse (not splittable)',
        '',
        '-- 3. PARTITIONING',
        '--    For large datasets write Parquet partitioned by date or region:',
        '--    df.write.partitionBy("year","month").parquet("path/")',
        '--    Then use folder wildcards:  BULK \'path/year=*/month=*/*.parquet\'',
        '--    Synapse Serverless will prune partitions via WHERE clauses automatically.',
        '',
        '-- 4. ROW GROUP SIZE',
        '--    Ideal row group size: 128 MB (Spark default).',
        f'--    This file has {row_groups} row group(s).',
        '--    Too many small row groups → slow reads. Repartition / coalesce before write.',
        '',
        '-- 5. SCHEMA EVOLUTION',
        '--    Add new nullable columns at the end of the schema.',
        '--    Synapse OPENROWSET reads only the columns requested — missing columns return NULL.',
        '',
        '-- 6. COPY INTO (Synapse Dedicated)',
        '--    COPY INTO [dbo].[MyTable]',
        '--    FROM \'https://<storage>.dfs.core.windows.net/<container>/path/*.parquet\'',
        '--    WITH (FILE_TYPE = \'PARQUET\');',
        '',
        '-- 7. STATISTICS (Synapse Dedicated)',
        '--    Create column statistics after loading for the query optimiser:',
        '--    CREATE STATISTICS stats_col1 ON [dbo].[MyTable]([col1]);',
    ]
    return lines


def _best_practices_delta(metadata: Dict[str, Any]) -> List[str]:
    dm = metadata.get('delta_metadata') or {}
    version = dm.get('version', 'unknown')
    partition_cols = dm.get('partition_columns') or []
    lines = [
        f'-- Detected: Delta Lake table  (version {version})',
        f'-- Partition columns: {partition_cols or "none"}',
        '',
        '-- 1. TOOL SELECTION',
        '--    Azure Synapse Serverless → OPENROWSET FORMAT=\'DELTA\'  (GA in 2024)',
        '--    Azure Databricks         → spark.read.format("delta").load("path")',
        '--    SQL Server               → Not natively supported; export to Parquet first',
        '',
        '-- 2. TIME TRAVEL',
        '--    Read a specific version:  OPTION (timestamp AS OF \'2025-01-01\')',
        '--    In Databricks:  spark.read.format("delta").option("versionAsOf", 5).load("...")',
        '--    Vacuum regularly to avoid bloat:  VACUUM delta.`path` RETAIN 168 HOURS',
        '',
        '-- 3. SYNAPSE SERVERLESS QUERY',
        '--    SELECT TOP 100 *',
        '--    FROM OPENROWSET(',
        '--        BULK \'https://<adls>.dfs.core.windows.net/<container>/<delta_path>/\',',
        '--        FORMAT = \'DELTA\'',
        '--    ) AS [result];',
        '',
        '-- 4. PARTITION PRUNING',
        '--    Synapse Serverless respects Delta partition pruning.',
        f'--    Partition by: {partition_cols or "< not partitioned >"}',
        '--    Add matching WHERE clauses to eliminate partition scans.',
        '',
        '-- 5. OPTIMIZE & ZORDER (Databricks / OSS Delta)',
        '--    OPTIMIZE delta.`path` ZORDER BY (event_date, user_id)',
        '--    Reduces file scans for selective queries significantly.',
        '',
        '-- 6. CONVERT DELTA → PARQUET for SQL Server PolyBase',
        '--    spark.read.format("delta").load("path").write.parquet("out/")',
        '--    Then use CREATE EXTERNAL TABLE with FORMAT_TYPE = PARQUET.',
    ]
    return lines


def _best_practices_json(size_mb: float) -> List[str]:
    lines = [
        '-- Detected: JSON file',
        '',
        '-- 1. TOOL SELECTION',
        '--    Small files (< 100 MB): OPENJSON directly in T-SQL',
        '--    Large files           : Convert to Parquet with pandas/Spark, then use Parquet path',
        '',
        '-- 2. OPENJSON (SQL Server 2016+)',
        '--    DECLARE @json NVARCHAR(MAX) = (SELECT BulkColumn FROM OPENROWSET(',
        '--        BULK \'C:\\path\\file.json\', SINGLE_CLOB) AS j);',
        '--    SELECT * FROM OPENJSON(@json)',
        '--    WITH (',
        '--        [col1] INT     \'$.col1\',',
        '--        [col2] NVARCHAR(255) \'$.col2\'',
        '--    );',
        '',
        '-- 3. SYNAPSE SERVERLESS — JSON via OPENROWSET + OPENJSON',
        '--    SELECT j.*',
        '--    FROM OPENROWSET(BULK \'https://...\', FORMAT=\'CSV\',',
        '--        FIELDTERMINATOR=\'0x0b\', FIELDQUOTE=\'0x0b\')',
        '--    WITH (json_doc NVARCHAR(MAX)) AS src',
        '--    CROSS APPLY OPENJSON(src.json_doc)',
        '--    WITH ([col1] INT, [col2] NVARCHAR(255)) AS j;',
        '',
        '-- 4. PERFORMANCE',
        '--    JSON parsing in T-SQL is CPU-intensive.',
        '--    Pre-process JSON to Parquet with pandas/pyarrow for large datasets:',
        '--       import pandas as pd; df = pd.read_json("file.json")',
        '--       df.to_parquet("file.parquet", compression="snappy")',
    ]
    return lines


def _best_practices_generic() -> List[str]:
    return [
        '-- 1. Identify the exact file format and encoding before loading.',
        '-- 2. Use a staging table (all columns NVARCHAR) for initial load.',
        '-- 3. Validate and transform into typed production table.',
        '-- 4. Add column statistics after loading for the query optimiser.',
    ]


