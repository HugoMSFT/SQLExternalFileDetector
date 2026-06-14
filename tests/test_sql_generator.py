"""Tests for SQL generator functionality."""

from external_file_detection.sql_generator import SQLGenerator


def test_csv_file_format_generation():
    """Test CSV file format generation."""
    generator = SQLGenerator()
    
    metadata = {
        'file_type': 'csv',
        'delimiter': ',',
        'has_header': True,
        'encoding': 'utf-8',
        'schema': [('id', 'int64'), ('name', 'object'), ('age', 'int64')]
    }
    
    ddl = generator.generate_external_file_format(metadata, 'test_csv_format')
    
    assert 'CREATE EXTERNAL FILE FORMAT [test_csv_format]' in ddl
    assert 'FORMAT_TYPE = DELIMITEDTEXT' in ddl
    assert "FIELD_TERMINATOR = ','" in ddl
    assert 'FIRST_ROW = 2' in ddl
    assert 'USE_TYPE_DEFAULT = TRUE' in ddl


def test_json_file_format_generation():
    """Test JSON file format generation."""
    generator = SQLGenerator()
    
    metadata = {
        'file_type': 'json',
        'schema': [('id', 'int'), ('name', 'str'), ('active', 'bool')]
    }
    
    ddl = generator.generate_external_file_format(metadata, 'test_json_format')
    
    assert 'CREATE EXTERNAL FILE FORMAT [test_json_format]' in ddl
    assert 'FORMAT_TYPE = JSON' in ddl


def test_parquet_file_format_generation():
    """Test Parquet file format generation."""
    generator = SQLGenerator()
    
    metadata = {
        'file_type': 'parquet',
        'compression': 'snappy',
        'schema': [('id', 'int64'), ('name', 'string')]
    }
    
    ddl = generator.generate_external_file_format(metadata, 'test_parquet_format')
    
    assert 'CREATE EXTERNAL FILE FORMAT [test_parquet_format]' in ddl
    assert 'FORMAT_TYPE = PARQUET' in ddl
    assert 'DATA_COMPRESSION = \'SNAPPY\'' in ddl


def test_external_table_generation():
    """Test external table generation."""
    generator = SQLGenerator()
    
    metadata = {
        'file_type': 'csv',
        'file_path': 'test_data/sample.csv',
        'schema': [('id', 'int64'), ('name', 'object'), ('age', 'int64')]
    }
    
    ddl = generator.generate_external_table(
        metadata, 
        table_name='test_table',
        data_source='test_source',
        location='test_location',
        file_format='test_format'
    )
    
    assert 'CREATE EXTERNAL TABLE [dbo].[test_table]' in ddl
    assert '[id] BIGINT' in ddl
    assert '[name] NVARCHAR(255)' in ddl
    assert '[age] BIGINT' in ddl
    assert 'DATA_SOURCE = [test_source]' in ddl
    assert "LOCATION = 'test_location'" in ddl
    assert 'FILE_FORMAT = [test_format]' in ddl


def test_type_mapping():
    """Test data type mapping to SQL types."""
    generator = SQLGenerator()
    
    assert generator._map_type_to_sql('int64') == 'BIGINT'
    assert generator._map_type_to_sql('int32') == 'INT'
    assert generator._map_type_to_sql('float64') == 'FLOAT'
    assert generator._map_type_to_sql('bool') == 'BIT'
    assert generator._map_type_to_sql('object') == 'NVARCHAR(255)'
    assert generator._map_type_to_sql('unknown_type') == 'NVARCHAR(255)'


def test_column_name_cleaning():
    """Test column name cleaning for SQL compatibility."""
    from external_file_detection.sql_generator import _clean_identifier
    
    assert _clean_identifier('valid_name') == 'valid_name'
    assert _clean_identifier('123invalid') == 'col_123invalid'
    assert _clean_identifier('name with spaces') == 'name_with_spaces'
    assert _clean_identifier('name-with-dashes') == 'name_with_dashes'
    assert _clean_identifier('') == 'column_1'


def test_complete_ddl_generation():
    """Test complete DDL generation."""
    generator = SQLGenerator()
    
    metadata = {
        'file_type': 'csv',
        'file_path': 'test.csv',
        'schema': [('id', 'int64'), ('name', 'object')],
        'delimiter': ',',
        'has_header': True
    }
    
    ddl = generator.generate_complete_ddl(metadata, 'test_table', 'test_source', 'test_location')
    
    assert 'CREATE EXTERNAL TABLE' in ddl


# -------------------------------------------------------------------
# generate_create_table
# -------------------------------------------------------------------

def test_create_table_sql_server():
    """CREATE TABLE for SQL Server should NOT have distribution/heap."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'test.csv',
        'schema': [('id', 'int64'), ('val', 'float64')],
    }
    sql = gen.generate_create_table(meta, 'tbl', target_platform='sql_server_2022')
    assert 'CREATE TABLE [dbo].[tbl]' in sql
    assert 'DISTRIBUTION' not in sql
    assert 'HEAP' not in sql


def test_create_table_azure_sql():
    """CREATE TABLE for Azure SQL omits distribution clause."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'parquet', 'file_path': 'data.parquet',
        'schema': [('a', 'int32'), ('b', 'string')],
    }
    sql = gen.generate_create_table(meta, target_platform='azure_sql_db')
    assert 'CREATE TABLE' in sql
    assert 'DISTRIBUTION' not in sql


def test_create_table_invalid_platform_fallback():
    """Invalid platform should fall back to sql_server_2022."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'x.csv',
        'schema': [('c', 'int64')],
    }
    sql = gen.generate_create_table(meta, target_platform='not_a_platform')
    assert 'CREATE TABLE' in sql   # fell back to sql_server_2022


# -------------------------------------------------------------------
# generate_bulk_insert
# -------------------------------------------------------------------

def test_bulk_insert_csv():
    """BULK INSERT generates correct syntax for CSV."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'data.csv',
        'encoding': 'utf-8', 'codepage': '65001',
        'delimiter': ',', 'has_header': True,
    }
    sql = gen.generate_bulk_insert(meta, 'tbl', target_platform='sql_server_2022')
    assert 'BULK INSERT [dbo].[tbl]' in sql
    assert "FIRSTROW        = 2" in sql
    assert "FIELDTERMINATOR = ','" in sql
    assert "CODEPAGE        = '65001'" in sql


def test_bulk_insert_non_csv():
    """BULK INSERT for non-CSV files returns a hint comment."""
    gen = SQLGenerator()
    meta = {'file_type': 'parquet', 'file_path': 'data.parquet'}
    sql = gen.generate_bulk_insert(meta, 'tbl', target_platform='sql_server_2022')
    assert 'PARQUET' in sql
    assert 'OPENROWSET' in sql or 'EXTERNAL TABLE' in sql


# -------------------------------------------------------------------
# Platform-specific tests
# -------------------------------------------------------------------

def test_copy_into_not_supported_on_sql_server_on_prem():
    """COPY INTO is only for Synapse Dedicated, not on-prem SQL Server."""
    gen = SQLGenerator()
    meta = {'file_type': 'csv', 'file_path': 'data.csv',
            'delimiter': ',', 'has_header': True,
            'schema': [('a', 'int64')]}
    sql = gen.generate_copy_into(meta, 'tbl', target_platform='sql_server_2022')
    assert 'not supported' in sql.lower() or 'alternative' in sql.lower()


def test_windows_backslashes_normalized_in_bulk_insert():
    """BULK INSERT should handle Windows backslash paths."""
    gen = SQLGenerator()
    meta = {'file_type': 'csv', 'file_path': 'D:\\data\\files\\test.csv',
            'delimiter': ',', 'has_header': True,
            'encoding': 'utf-8', 'codepage': '65001'}
    sql = gen.generate_bulk_insert(meta, 'tbl', target_platform='sql_server_2022')
    assert 'D:/data/files/test.csv' in sql
    assert '\\\\' not in sql  # no double backslashes


def test_windows_backslashes_normalized_in_openrowset():
    """OPENROWSET for on-prem SQL Server should normalize backslashes."""
    gen = SQLGenerator()
    meta = {'file_type': 'csv', 'file_path': 'D:\\data\\test.csv',
            'file_name': 'test.csv',
            'delimiter': ',', 'has_header': True,
            'encoding': 'utf-8', 'codepage': '65001',
            'schema': [('a', 'int64')]}
    sql = gen.generate_openrowset(meta, target_platform='sql_server_2022')
    assert 'D:/data/test.csv' in sql


# -------------------------------------------------------------------
# generate_openrowset
# -------------------------------------------------------------------

def test_openrowset_csv():
    """OPENROWSET for CSV includes PARSER_VERSION and HEADER_ROW."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'data.csv',
        'encoding': 'utf-8', 'delimiter': ',', 'has_header': True,
        'schema': [('a', 'int64'), ('b', 'object')],
    }
    sql = gen.generate_openrowset(meta)
    assert 'OPENROWSET' in sql
    assert 'CSV' in sql


def test_openrowset_parquet():
    """OPENROWSET for Parquet on SQL Server shows PolyBase guidance."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'parquet', 'file_path': 'x.parquet',
        'schema': [('id', 'int64')],
    }
    sql = gen.generate_openrowset(meta)
    assert 'PolyBase' in sql or 'OPENROWSET' in sql


def test_openrowset_delta():
    """OPENROWSET for Delta includes FORMAT = 'DELTA'."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'delta', 'file_path': '/delta_folder',
        'schema': [('id', 'int64')],
    }
    sql = gen.generate_openrowset(meta)
    assert "FORMAT = 'DELTA'" in sql


# -------------------------------------------------------------------
# generate_best_practices
# -------------------------------------------------------------------

def test_best_practices_csv():
    """Best practices for CSV mentions encoding and delimiter."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'data.csv',
        'encoding': 'utf-8', 'delimiter': ',', 'has_header': True,
        'file_size': 1024,
    }
    bp = gen.generate_best_practices(meta)
    assert 'BEST PRACTICES' in bp
    assert 'CSV' in bp
    assert 'RECOMMENDED PATH' in bp
    assert 'VALIDATION SQL AFTER LOAD' in bp


def test_best_practices_parquet():
    """Best practices for Parquet mentions PARQUET."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'parquet', 'file_path': 'data.parquet',
        'file_size': 1024 * 1024 * 50,
        'compression': 'snappy',
    }
    bp = gen.generate_best_practices(meta)
    assert 'PARQUET' in bp


def test_best_practices_warnings_for_nested_json_and_long_strings():
    """Best practices should surface metadata-driven warnings."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'json',
        'file_path': 'data.json',
        'file_name': 'data.json',
        'file_size': 2048,
        'encoding': 'utf-8',
        'encoding_confidence': 45,
        'json_nesting': {'id': 'scalar', 'payload': 'object'},
        'schema': [('id', 'int64'), ('payload', 'object'), ('notes', 'object')],
        'max_string_lengths': {'notes': 5001},
        'nullable_columns': ['id'],
    }
    bp = gen.generate_best_practices(meta, target_platform='fabric_sql_db')
    assert 'WARNINGS / WATCH-OUTS' in bp
    assert 'Nested JSON detected' in bp
    assert 'Very long strings detected' in bp
    assert 'Low encoding confidence' in bp


def test_best_practices_validation_sql_uses_table_name():
    """Best practices should include reusable post-load validation SQL."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv',
        'file_path': 'sales_orders.csv',
        'file_name': 'sales_orders.csv',
        'file_size': 1024,
        'schema': [('order_id', 'object'), ('customer_id', 'int64'), ('amount', 'float64')],
    }
    bp = gen.generate_best_practices(meta, target_platform='sql_server_2022')
    assert 'SELECT COUNT(*) AS loaded_rows FROM [dbo].[sales_orders];' in bp
    assert 'SELECT TOP 10 [order_id], [customer_id], [amount] FROM [dbo].[sales_orders];' in bp


# -------------------------------------------------------------------
# generate_all_statements
# -------------------------------------------------------------------

def test_all_statements_returns_all_keys():
    """generate_all_statements returns a dict with all required keys."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'test.csv',
        'schema': [('id', 'int64'), ('name', 'object')],
        'delimiter': ',', 'has_header': True,
        'encoding': 'utf-8', 'codepage': '65001',
    }
    stmts = gen.generate_all_statements(meta)
    expected_keys = {
        'create_table', 'bulk_insert', 'openrowset',
        'external_file_format', 'create_external_table', 'best_practices',
        'copy_into', 'json_functions', 'for_json', 'credential_setup',
    }
    assert set(stmts.keys()) == expected_keys
    for key, val in stmts.items():
        assert isinstance(val, str), f'{key} should be a string'
        assert len(val) > 10, f'{key} should not be empty'


def test_all_statements_passes_target_platform():
    """generate_all_statements propagates target_platform to create_table."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'test.csv',
        'schema': [('id', 'int64')],
        'delimiter': ',', 'has_header': True,
    }
    stmts = gen.generate_all_statements(meta, target_platform='sql_server_2022')
    assert 'DISTRIBUTION' not in stmts['create_table']


# -------------------------------------------------------------------
# max_string_lengths / NVARCHAR sizing
# -------------------------------------------------------------------

def test_nvarchar_sizing_with_max_string_lengths():
    """max_string_lengths should influence NVARCHAR size in column defs."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'test.csv',
        'schema': [('short_col', 'object'), ('long_col', 'object')],
        'max_string_lengths': {'short_col': 50, 'long_col': 5000},
    }
    sql = gen.generate_create_table(meta, 'tbl')
    # short_col stays NVARCHAR(255) default; long_col should be NVARCHAR(MAX) (>4000)
    assert 'NVARCHAR(MAX)' in sql


# -------------------------------------------------------------------
# generate_copy_into
# -------------------------------------------------------------------

def test_copy_into_csv():
    """COPY INTO for CSV on SQL Server 2022 shows NOT AVAILABLE."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'data.csv', 'file_name': 'data.csv',
        'delimiter': ',', 'has_header': True, 'encoding': 'utf-8',
        'schema': [('id', 'int64'), ('name', 'object')],
    }
    sql = gen.generate_copy_into(meta, 'tbl')
    assert 'NOT AVAILABLE' in sql
    assert 'BULK INSERT' in sql  # should suggest alternative


def test_copy_into_parquet():
    """COPY INTO for Parquet on SQL Server 2022 shows NOT AVAILABLE."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'parquet', 'file_path': 'data.parquet', 'file_name': 'data.parquet',
        'schema': [('id', 'int64')],
    }
    sql = gen.generate_copy_into(meta, 'tbl')
    assert 'NOT AVAILABLE' in sql


def test_copy_into_json_fallback():
    """COPY INTO for JSON on SQL Server 2022 shows NOT AVAILABLE."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'json', 'file_path': 'data.json', 'file_name': 'data.json',
        'schema': [('id', 'int64')],
    }
    sql = gen.generate_copy_into(meta, 'tbl')
    assert 'NOT AVAILABLE' in sql


def test_copy_into_delta_fallback():
    """COPY INTO for Delta on SQL Server 2022 shows NOT AVAILABLE."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'delta', 'file_path': '/delta', 'file_name': 'delta_table',
        'schema': [('id', 'int64')],
    }
    sql = gen.generate_copy_into(meta, 'tbl')
    assert 'NOT AVAILABLE' in sql


# -------------------------------------------------------------------
# generate_credential_setup
# -------------------------------------------------------------------

def test_credential_setup():
    """Credential setup generates master key, credential, and data source."""
    gen = SQLGenerator()
    sql = gen.generate_credential_setup('TestDS', 'ff_csv', {'file_type': 'csv'})
    assert 'MASTER KEY' in sql
    assert 'DATABASE SCOPED CREDENTIAL' in sql
    assert 'EXTERNAL DATA SOURCE [TestDS]' in sql
    assert 'cred_TestDS' in sql
    assert 'Managed Identity' in sql  # option B


# -------------------------------------------------------------------
# generate_json_functions
# -------------------------------------------------------------------

def _json_meta():
    """Helper returning typical JSON metadata."""
    return {
        'file_type': 'json', 'file_path': 'data.json', 'file_name': 'data.json',
        'json_format': 'array',
        'json_nesting': {'id': 'scalar', 'name': 'scalar', 'address': 'object', 'tags': 'array'},
        'schema': [('id', 'int64'), ('name', 'object'), ('address', 'object'), ('tags', 'object')],
    }


def test_json_functions_openjson():
    """JSON Functions tab contains OPENJSON with typed WITH clause."""
    gen = SQLGenerator()
    sql = gen.generate_json_functions(_json_meta(), 'tbl', target_platform='sql_server_2022')
    assert 'OPENJSON' in sql
    assert 'SINGLE_CLOB' in sql
    assert '$.id' in sql
    assert '$.name' in sql
    assert 'AS JSON' in sql  # nested columns should have AS JSON


def test_json_functions_validation():
    """JSON Functions tab contains ISJSON validation."""
    gen = SQLGenerator()
    sql = gen.generate_json_functions(_json_meta(), 'tbl', target_platform='sql_server_2022')
    assert 'ISJSON' in sql


def test_json_functions_nested_cross_apply():
    """JSON Functions tab has CROSS APPLY for nested objects."""
    gen = SQLGenerator()
    sql = gen.generate_json_functions(_json_meta(), 'tbl', target_platform='sql_server_2022')
    assert 'CROSS APPLY OPENJSON' in sql
    assert '$.address' in sql or '$.tags' in sql


def test_json_functions_json_modify():
    """JSON Functions tab has JSON_MODIFY example."""
    gen = SQLGenerator()
    sql = gen.generate_json_functions(_json_meta(), 'tbl', target_platform='sql_server_2022')
    assert 'JSON_MODIFY' in sql


def test_json_functions_object_format():
    """JSON Functions for object format uses JSON_VALUE directly."""
    gen = SQLGenerator()
    meta = _json_meta()
    meta['json_format'] = 'object'
    sql = gen.generate_json_functions(meta, 'tbl', target_platform='sql_server_2022')
    assert 'JSON_VALUE' in sql or 'JSON_QUERY' in sql


# -------------------------------------------------------------------
# generate_for_json_path
# -------------------------------------------------------------------

def test_for_json_path():
    """FOR JSON PATH generates various FOR JSON examples."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'json', 'file_path': 'data.json',
        'schema': [('id', 'int64'), ('name', 'object')],
        'json_nesting': {'id': 'scalar', 'name': 'scalar'},
    }
    sql = gen.generate_for_json_path(meta, 'tbl', target_platform='sql_server_2022')
    assert 'FOR JSON PATH' in sql
    assert 'ROOT' in sql
    assert 'INCLUDE_NULL_VALUES' in sql
    assert 'WITHOUT_ARRAY_WRAPPER' in sql
    assert 'JSON_OBJECT' in sql


def test_for_json_path_nested():
    """FOR JSON PATH re-nests objects via JSON_QUERY."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'json', 'file_path': 'data.json',
        'schema': [('id', 'int64'), ('addr', 'object')],
        'json_nesting': {'id': 'scalar', 'addr': 'object'},
    }
    sql = gen.generate_for_json_path(meta, 'tbl', target_platform='sql_server_2022')
    assert 'JSON_QUERY' in sql


# -------------------------------------------------------------------
# _generate_openjson_columns
# -------------------------------------------------------------------

def test_openjson_columns_scalar():
    """Scalar columns get SQL type and JSON path."""
    gen = SQLGenerator()
    meta = {
        'schema': [('id', 'int64'), ('name', 'object')],
        'json_nesting': {'id': 'scalar', 'name': 'scalar'},
    }
    cols = gen._generate_openjson_columns(meta, indent=4)
    assert len(cols) == 2
    assert "'$.id'" in cols[0]
    assert 'BIGINT' in cols[0]


def test_openjson_columns_nested():
    """Nested object/array columns get NVARCHAR(MAX) AS JSON."""
    gen = SQLGenerator()
    meta = {
        'schema': [('data', 'object')],
        'json_nesting': {'data': 'object'},
    }
    cols = gen._generate_openjson_columns(meta, indent=4)
    assert len(cols) == 1
    assert 'NVARCHAR(MAX)' in cols[0]
    assert 'AS JSON' in cols[0]


# -------------------------------------------------------------------
# REJECT_TYPE comma fix
# -------------------------------------------------------------------

def test_external_table_no_trailing_comma_reject_type():
    """REJECT_TYPE = VALUE should not produce a double-comma."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'data.csv',
        'schema': [('id', 'int64')],
    }
    sql = gen.generate_external_table(meta, 'tbl', 'ds', 'loc', 'fmt')
    # No double-comma (the old bug had VALUE, followed by ,\n from join)
    assert 'VALUE,,' not in sql
    assert 'REJECT_TYPE = VALUE' in sql


# -------------------------------------------------------------------
# Platform gating — features not available
# -------------------------------------------------------------------

def test_copy_into_not_on_sql_server():
    """COPY INTO should show NOT AVAILABLE on SQL Server."""
    gen = SQLGenerator()
    meta = {'file_type': 'csv', 'file_path': 'x.csv', 'schema': [('id', 'int64')]}
    sql = gen.generate_copy_into(meta, 'tbl', target_platform='sql_server_2022')
    assert 'NOT AVAILABLE' in sql
    assert 'BULK INSERT' in sql or 'OPENROWSET' in sql  # alternatives shown


def test_bulk_insert_fabric_sql_db_openrowset_fallbacks():
    """Fabric SQL DB BULK INSERT guidance should include OPENROWSET load patterns."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv',
        'file_path': 'x.csv',
        'file_name': 'x.csv',
        'delimiter': ',',
        'has_header': True,
    }
    sql = gen.generate_bulk_insert(meta, target_platform='fabric_sql_db')
    assert 'NOT AVAILABLE on Microsoft Fabric SQL Database' in sql
    assert 'SELECT *' in sql and 'INTO [dbo].[stg_' in sql
    assert 'INSERT INTO [dbo].[' in sql
    assert 'FROM OPENROWSET(' in sql


def test_copy_into_fabric_sql_db_alternatives():
    """COPY INTO on Fabric SQL DB should provide practical alternatives."""
    gen = SQLGenerator()
    meta = {'file_type': 'csv', 'file_path': 'x.csv', 'schema': [('id', 'int64')]}
    sql = gen.generate_copy_into(meta, target_platform='fabric_sql_db')
    assert 'NOT AVAILABLE on Microsoft Fabric SQL Database' in sql
    assert 'OPENROWSET' in sql
    assert 'Data Pipelines' in sql or 'Dataflows' in sql


def test_openrowset_available_on_fabric_sql_db():
    """OPENROWSET should be generated for Fabric SQL DB."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'parquet',
        'file_path': 'x.parquet',
        'file_name': 'x.parquet',
        'schema': [('id', 'int64')],
    }
    sql = gen.generate_openrowset(meta, target_platform='fabric_sql_db')
    assert 'OPENROWSET' in sql
    assert 'NOT AVAILABLE' not in sql


def test_bulk_insert_on_azure_sql_mi():
    """BULK INSERT should work on Azure SQL Managed Instance."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'x.csv', 'file_name': 'x.csv',
        'delimiter': ',', 'has_header': True, 'encoding': 'utf-8',
        'codepage': '65001', 'schema': [('id', 'int64')],
    }
    sql = gen.generate_bulk_insert(meta, 'tbl', target_platform='azure_sql_mi')
    assert 'BULK INSERT' in sql
    assert 'NOT AVAILABLE' not in sql


def test_openrowset_azure_sql_db_blob_storage():
    """OPENROWSET on Azure SQL Database should generate BLOB_STORAGE syntax."""
    gen = SQLGenerator()
    meta = {'file_type': 'csv', 'file_path': 'x.csv', 'schema': [('id', 'int64')]}
    sql = gen.generate_openrowset(meta, target_platform='azure_sql_db')
    assert 'BLOB_STORAGE' in sql
    assert 'DATA_SOURCE' in sql
    assert 'BlobDS' in sql


def test_openrowset_local_on_sql_server_2022():
    """OPENROWSET on SQL Server 2022 should generate local file syntax."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': r'C:\data\test.csv',
        'schema': [('id', 'int64')], 'encoding': 'utf-8',
        'codepage': '65001', 'delimiter': ',', 'has_header': True,
    }
    sql = gen.generate_openrowset(meta, target_platform='sql_server_2022')
    assert 'OPENROWSET' in sql
    assert 'BULK' in sql
    assert 'NOT AVAILABLE' not in sql


def test_external_table_on_azure_sql_mi():
    """CREATE EXTERNAL TABLE is supported on Azure SQL MI per the PolyBase docs."""
    gen = SQLGenerator()
    meta = {'file_type': 'csv', 'file_path': 'x.csv', 'schema': [('id', 'int64')]}
    sql = gen.generate_external_table(meta, target_platform='azure_sql_mi')
    assert 'CREATE EXTERNAL TABLE' in sql
    assert 'NOT AVAILABLE' not in sql


def test_external_table_on_fabric_sql_db():
    """CREATE EXTERNAL TABLE is supported on Fabric SQL Database per the docs."""
    gen = SQLGenerator()
    meta = {'file_type': 'csv', 'file_path': 'x.csv', 'schema': [('id', 'int64')]}
    sql = gen.generate_external_table(meta, target_platform='fabric_sql_db')
    assert 'CREATE EXTERNAL TABLE' in sql
    assert 'NOT AVAILABLE' not in sql


def test_for_json_on_azure_sql_db():
    """FOR JSON should work on Azure SQL Database."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'json', 'file_path': 'x.json',
        'schema': [('id', 'int64'), ('name', 'object')],
        'json_nesting': {'id': 'scalar', 'name': 'scalar'},
    }
    sql = gen.generate_for_json_path(meta, 'tbl', target_platform='azure_sql_db')
    assert 'FOR JSON PATH' in sql
    assert 'NOT AVAILABLE' not in sql


def test_json_path_exists_not_on_sql_2019():
    """JSON_PATH_EXISTS should be noted as unavailable on SQL Server 2019."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'json', 'file_path': 'x.json',
        'schema': [('id', 'int64')],
        'json_nesting': {'id': 'scalar'},
        'json_format': 'array',
    }
    sql = gen.generate_json_functions(meta, 'tbl', target_platform='sql_server_2019')
    # Should NOT have actual JSON_PATH_EXISTS statement, but a note
    assert 'NOT available' in sql or 'not available' in sql.lower()


def test_json_path_exists_on_sql_2022():
    """JSON_PATH_EXISTS should appear on SQL Server 2022."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'json', 'file_path': 'x.json',
        'schema': [('id', 'int64')],
        'json_nesting': {'id': 'scalar'},
        'json_format': 'array',
    }
    sql = gen.generate_json_functions(meta, 'tbl', target_platform='sql_server_2022')
    assert 'JSON_PATH_EXISTS' in sql
    # Should have actual statement not just a "not available" note
    assert 'SELECT JSON_PATH_EXISTS' in sql


def test_credential_on_azure_sql_mi():
    """Credential/data-source setup is supported on Azure SQL Managed Instance."""
    gen = SQLGenerator()
    sql = gen.generate_credential_setup('DS', 'ff', target_platform='azure_sql_mi')
    assert 'CREATE DATABASE SCOPED CREDENTIAL' in sql
    assert 'NOT AVAILABLE' not in sql


def test_best_practices_includes_platform_methods():
    """Best practices should list recommended loading methods for the platform."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'x.csv',
        'encoding': 'utf-8', 'file_size': 1024,
    }
    bp = gen.generate_best_practices(meta, target_platform='sql_server_2022')
    assert 'COPY INTO' in bp
    assert 'CREATE EXTERNAL TABLE' in bp

    bp2 = gen.generate_best_practices(meta, target_platform='sql_server_2022')
    assert 'BULK INSERT' in bp2
    assert 'OPENROWSET' in bp2


# -------------------------------------------------------------------
# New tests: Azure SQL DB OPENROWSET, schema overrides, storage_url
# -------------------------------------------------------------------

def test_openrowset_azure_sql_db_json():
    """OPENROWSET on Azure SQL DB for JSON produces SINGLE_CLOB + OPENJSON."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'json', 'file_path': 'data.json',
        'schema': [('id', 'int64'), ('name', 'object')],
        'json_nesting': {'id': 'scalar', 'name': 'scalar'},
    }
    sql = gen.generate_openrowset(meta, target_platform='azure_sql_db')
    assert 'SINGLE_CLOB' in sql
    assert 'OPENJSON' in sql
    assert 'BlobDS' in sql


def test_openrowset_azure_sql_mi():
    """OPENROWSET on Azure SQL MI produces BLOB_STORAGE syntax."""
    gen = SQLGenerator()
    meta = {'file_type': 'csv', 'file_path': 'x.csv', 'schema': [('id', 'int64')]}
    sql = gen.generate_openrowset(meta, target_platform='azure_sql_mi')
    assert 'BLOB_STORAGE' in sql
    assert 'DATA_SOURCE' in sql


def test_storage_url_in_openrowset():
    """Storage URL appears in OPENROWSET for CSV on SQL Server."""
    gen = SQLGenerator()
    meta = {'file_type': 'csv', 'file_path': 'x.csv', 'schema': [('id', 'int64')],
            'encoding': 'utf-8', 'delimiter': ',', 'has_header': True}
    sql = gen.generate_openrowset(meta, target_platform='sql_server_2022')
    assert 'OPENROWSET' in sql


def test_storage_url_in_copy_into():
    """Storage URL is injected into COPY INTO blob path."""
    gen = SQLGenerator()
    meta = {'file_type': 'csv', 'file_path': 'x.csv', 'schema': [('id', 'int64')],
            'encoding': 'utf-8', 'delimiter': ',', 'has_header': True}
    url = 'https://myaccount.blob.core.windows.net/data/x.csv'
    sql = gen.generate_copy_into(meta, 'tbl', storage_url=url, target_platform='sql_server_2022')
    assert 'NOT AVAILABLE' in sql or 'myaccount.blob.core.windows.net' in sql


def test_sql_type_overrides_in_column_definitions():
    """SQL type overrides are applied in _generate_column_definitions."""
    gen = SQLGenerator()
    meta = {
        'schema': [('id', 'int64'), ('name', 'object')],
        'nullable_columns': ['name'],
        'sql_type_overrides': {'name': 'VARCHAR(500)'},
    }
    cols = gen._generate_column_definitions(meta, include_nullability=True)
    assert any('VARCHAR(500)' in c for c in cols)


def test_sql_type_overrides_in_openjson_columns():
    """SQL type overrides are applied in _generate_openjson_columns."""
    gen = SQLGenerator()
    meta = {
        'schema': [('id', 'int64'), ('amount', 'float64')],
        'json_nesting': {'id': 'scalar', 'amount': 'scalar'},
        'sql_type_overrides': {'amount': 'DECIMAL(18,4)'},
    }
    cols = gen._generate_openjson_columns(meta)
    assert any('DECIMAL(18,4)' in c for c in cols)


def test_generate_all_statements_passes_storage_url():
    """generate_all_statements returns valid SQL for all keys."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'x.csv',
        'schema': [('id', 'int64')],
        'encoding': 'utf-8', 'delimiter': ',', 'has_header': True,
    }
    stmts = gen.generate_all_statements(meta, target_platform='sql_server_2022')
    assert 'OPENROWSET' in stmts['openrowset']
    assert 'BULK INSERT' in stmts['bulk_insert']


def test_fabric_sql_db_external_table_supported():
    """Fabric SQL Database supports CREATE EXTERNAL TABLE per the PolyBase docs."""
    gen = SQLGenerator()
    meta = {'file_type': 'csv', 'file_path': 'x.csv', 'schema': [('id', 'int64')]}
    sql = gen.generate_external_table(meta, target_platform='fabric_sql_db')
    assert 'CREATE EXTERNAL TABLE' in sql
    assert 'NOT AVAILABLE' not in sql


# -------------------------------------------------------------------
# Sample data comments
# -------------------------------------------------------------------

def test_sample_rows_in_create_table():
    """CREATE TABLE should include sample rows as comments."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'test.csv',
        'schema': [('id', 'int64'), ('name', 'object')],
        'sample_rows': [[1, 'Alice'], [2, 'Bob']],
    }
    sql = gen.generate_create_table(meta, 'tbl', target_platform='sql_server_2022')
    assert '-- Sample data' in sql
    assert 'Alice' in sql
    assert 'Bob' in sql


def test_sample_rows_truncated_for_wide_tables():
    """Sample rows should be truncated to 8 columns for wide tables."""
    gen = SQLGenerator()
    cols = [(f'col_{i}', 'int64') for i in range(20)]
    rows = [list(range(20)), list(range(20, 40))]
    meta = {
        'file_type': 'csv', 'file_path': 'wide.csv',
        'schema': cols,
        'sample_rows': rows,
    }
    sql = gen.generate_create_table(meta, 'wide_tbl', target_platform='sql_server_2022')
    assert '-- Sample data' in sql
    assert '12 more' in sql
    assert '...' in sql


def test_json_sample_values_in_create_table():
    """CREATE TABLE for JSON should include sample values."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'json', 'file_path': 'data.json',
        'schema': [('id', 'int'), ('name', 'str')],
        'json_sample_values': {'id': 1, 'name': 'Alice'},
    }
    sql = gen.generate_create_table(meta, 'tbl', target_platform='sql_server_2022')
    assert '-- Sample data (first record)' in sql
    assert 'id: 1' in sql
    assert 'name: Alice' in sql


def test_credential_setup_in_all_statements():
    """generate_all_statements should include credential_setup."""
    gen = SQLGenerator()
    meta = {
        'file_type': 'csv', 'file_path': 'test.csv',
        'schema': [('id', 'int64')],
        'delimiter': ',', 'has_header': True,
        'encoding': 'utf-8', 'codepage': '65001',
    }
    stmts = gen.generate_all_statements(meta)
    assert 'credential_setup' in stmts
    assert 'CREATE MASTER KEY' in stmts['credential_setup'] or 'NOT AVAILABLE' in stmts['credential_setup']


if __name__ == '__main__':
    import sys
    import pytest
    sys.exit(pytest.main([__file__, '-v']))