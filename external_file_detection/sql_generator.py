"""SQL DDL generator for external file formats and tables."""

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
    """Generates SQL DDL statements for external file formats and tables."""
    
    # Mapping from detected types to SQL Server data types
    TYPE_MAPPING = {
        'int64': 'BIGINT',
        'int32': 'INT',
        'int': 'INT',
        'float64': 'FLOAT',
        'float32': 'REAL',
        'float': 'FLOAT',
        'bool': 'BIT',
        'object': 'NVARCHAR(MAX)',
        'str': 'NVARCHAR(MAX)',
        'string': 'NVARCHAR(MAX)',
        'datetime64[ns]': 'DATETIME2',
        'timestamp': 'DATETIME2',
        'date': 'DATE',
        'time': 'TIME'
    }
    
    def __init__(self):
        """Initialize the SQL generator."""
        pass
    
    def generate_external_file_format(self, metadata: Dict[str, Any], format_name: str = None) -> str:
        """
        Generate CREATE EXTERNAL FILE FORMAT statement.
        
        Args:
            metadata: File metadata from FileDetector
            format_name: Name for the file format (optional)
            
        Returns:
            SQL CREATE EXTERNAL FILE FORMAT statement
        """
        if not format_name:
            format_name = f"ff_{metadata['file_type']}_format"
        
        config = self._determine_format_config(metadata)
        
        sql_parts = [f"CREATE EXTERNAL FILE FORMAT [{format_name}]"]
        sql_parts.append("WITH (")
        
        format_options = []
        
        # FORMAT_TYPE is required
        format_options.append(f"    FORMAT_TYPE = {config.format_type}")
        
        # Add optional parameters based on file type and metadata
        if config.field_terminator:
            format_options.append(f"    FIELD_TERMINATOR = '{config.field_terminator}'")
        
        if config.string_delimiter:
            format_options.append(f"    STRING_DELIMITER = '{config.string_delimiter}'")
        
        if config.date_format:
            format_options.append(f"    DATE_FORMAT = '{config.date_format}'")
        
        if config.use_type_default:
            format_options.append(f"    USE_TYPE_DEFAULT = {str(config.use_type_default).upper()}")
        
        if config.encoding and config.encoding != 'UTF8':
            format_options.append(f"    ENCODING = '{config.encoding}'")
        
        if config.first_row != 1:
            format_options.append(f"    FIRST_ROW = {config.first_row}")
        
        if config.data_compression:
            format_options.append(f"    DATA_COMPRESSION = '{config.data_compression}'")
        
        if config.row_terminator:
            format_options.append(f"    ROW_TERMINATOR = '{config.row_terminator}'")
        
        if config.serialization_encoding:
            format_options.append(f"    SERIALIZATION_ENCODING = '{config.serialization_encoding}'")
        
        if config.serializer_method:
            format_options.append(f"    SERIALIZER_METHOD = '{config.serializer_method}'")
        
        if config.deserializer_method:
            format_options.append(f"    DESERIALIZER_METHOD = '{config.deserializer_method}'")
        
        sql_parts.append(",\n".join(format_options))
        sql_parts.append(");")
        
        return "\n".join(sql_parts)
    
    def generate_external_table(self, metadata: Dict[str, Any], table_name: str = None, 
                              data_source: str = None, location: str = None, 
                              file_format: str = None) -> str:
        """
        Generate CREATE EXTERNAL TABLE statement.
        
        Args:
            metadata: File metadata from FileDetector
            table_name: Name for the table (optional)
            data_source: External data source name
            location: File location
            file_format: File format name
            
        Returns:
            SQL CREATE EXTERNAL TABLE statement
        """
        if not table_name:
            base_name = metadata['file_path'].split('/')[-1].split('.')[0]
            table_name = f"ext_{base_name}"
        
        if not location:
            location = metadata['file_path']
        
        if not file_format:
            file_format = f"ff_{metadata['file_type']}_format"
        
        # Generate column definitions from schema
        columns = self._generate_column_definitions(metadata)
        
        if not columns:
            # Fallback for files without detectable schema
            columns = ["    [data] NVARCHAR(MAX)"]
        
        sql_parts = [f"CREATE EXTERNAL TABLE [{table_name}]"]
        sql_parts.append("(")
        sql_parts.append(",\n".join(columns))
        sql_parts.append(")")
        sql_parts.append("WITH (")
        
        # Required parameters
        with_options = []
        if data_source:
            with_options.append(f"    DATA_SOURCE = [{data_source}]")
        with_options.append(f"    LOCATION = '{location}'")
        with_options.append(f"    FILE_FORMAT = [{file_format}]")
        
        sql_parts.append(",\n".join(with_options))
        sql_parts.append(");")
        
        return "\n".join(sql_parts)
    
    def _determine_format_config(self, metadata: Dict[str, Any]) -> ExternalFileFormatConfig:
        """Determine file format configuration based on metadata."""
        file_type = metadata['file_type']
        
        if file_type == 'csv':
            return ExternalFileFormatConfig(
                format_type='DELIMITEDTEXT',
                field_terminator=metadata.get('delimiter', ','),
                string_delimiter='"',
                first_row=2 if metadata.get('has_header', False) else 1,
                encoding=metadata.get('encoding', 'UTF8').upper(),
                use_type_default=True
            )
        elif file_type == 'json':
            return ExternalFileFormatConfig(
                format_type='JSON'
            )
        elif file_type == 'parquet':
            return ExternalFileFormatConfig(
                format_type='PARQUET',
                data_compression=metadata.get('compression', 'SNAPPY').upper() if metadata.get('compression') else None
            )
        elif file_type == 'orc':
            return ExternalFileFormatConfig(
                format_type='ORC',
                data_compression='DEFAULT'
            )
        elif file_type == 'rc':
            return ExternalFileFormatConfig(
                format_type='RCFILE',
                serialization_encoding='UTF8',
                serializer_method='org.apache.hadoop.hive.serde2.columnar.ColumnarSerDe',
                deserializer_method='org.apache.hadoop.hive.serde2.columnar.ColumnarSerDe'
            )
        else:  # text and unknown
            return ExternalFileFormatConfig(
                format_type='DELIMITEDTEXT',
                field_terminator='\\n',
                encoding=metadata.get('encoding', 'UTF8').upper()
            )
    
    def _generate_column_definitions(self, metadata: Dict[str, Any]) -> List[str]:
        """Generate column definitions from file schema."""
        schema = metadata.get('schema')
        if not schema:
            return []
        
        columns = []
        for col_name, col_type in schema:
            # Clean column name for SQL
            clean_name = self._clean_column_name(col_name)
            sql_type = self._map_type_to_sql(col_type)
            columns.append(f"    [{clean_name}] {sql_type}")
        
        return columns
    
    def _clean_column_name(self, name: str) -> str:
        """Clean column name for SQL compatibility."""
        # Remove special characters and replace with underscores
        clean_name = ''.join(c if c.isalnum() else '_' for c in str(name))
        
        # Ensure it doesn't start with a number
        if clean_name and clean_name[0].isdigit():
            clean_name = 'col_' + clean_name
        
        # Ensure it's not empty
        if not clean_name:
            clean_name = 'column_1'
        
        return clean_name
    
    def _map_type_to_sql(self, data_type: str) -> str:
        """Map detected data type to SQL Server data type."""
        data_type = str(data_type).lower()
        
        # Handle pandas/numpy types
        for key, sql_type in self.TYPE_MAPPING.items():
            if key.lower() in data_type:
                return sql_type
        
        # Default to NVARCHAR for unknown types
        return 'NVARCHAR(MAX)'
    
    def generate_complete_ddl(self, metadata: Dict[str, Any], table_name: str = None,
                             data_source: str = None, location: str = None) -> str:
        """
        Generate complete DDL including both file format and table.
        
        Args:
            metadata: File metadata from FileDetector
            table_name: Name for the table (optional)
            data_source: External data source name
            location: File location
            
        Returns:
            Complete DDL script
        """
        format_name = f"ff_{metadata['file_type']}_format"
        
        ddl_parts = []
        ddl_parts.append("-- External File Format")
        ddl_parts.append(self.generate_external_file_format(metadata, format_name))
        ddl_parts.append("")
        ddl_parts.append("-- External Table")
        ddl_parts.append(self.generate_external_table(metadata, table_name, data_source, location, format_name))
        
        return "\n".join(ddl_parts)