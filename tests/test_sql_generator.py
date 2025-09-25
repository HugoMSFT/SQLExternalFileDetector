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
    
    assert 'CREATE EXTERNAL TABLE [test_table]' in ddl
    assert '[id] BIGINT' in ddl
    assert '[name] NVARCHAR(MAX)' in ddl
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
    assert generator._map_type_to_sql('object') == 'NVARCHAR(MAX)'
    assert generator._map_type_to_sql('unknown_type') == 'NVARCHAR(MAX)'


def test_column_name_cleaning():
    """Test column name cleaning for SQL compatibility."""
    generator = SQLGenerator()
    
    assert generator._clean_column_name('valid_name') == 'valid_name'
    assert generator._clean_column_name('123invalid') == 'col_123invalid'
    assert generator._clean_column_name('name with spaces') == 'name_with_spaces'
    assert generator._clean_column_name('name-with-dashes') == 'name_with_dashes'
    assert generator._clean_column_name('') == 'column_1'


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
    
    assert '-- External File Format' in ddl
    assert '-- External Table' in ddl
    assert 'CREATE EXTERNAL FILE FORMAT' in ddl
    assert 'CREATE EXTERNAL TABLE' in ddl


if __name__ == '__main__':
    test_csv_file_format_generation()
    test_json_file_format_generation()
    test_parquet_file_format_generation()
    test_external_table_generation()
    test_type_mapping()
    test_column_name_cleaning()
    test_complete_ddl_generation()
    print("All tests passed!")