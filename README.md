# External File Detection

A comprehensive Python application that detects file types and generates SQL DDL statements for external file formats and tables. Supports local storage, Amazon S3, and Azure Blob Storage.

## Features

- **File Type Detection**: Automatically detects text, CSV, JSON, Parquet, Delta, ORC, and RC files
- **Metadata Analysis**: Analyzes file structure, schema, and properties
- **SQL DDL Generation**: Creates `CREATE EXTERNAL FILE FORMAT` and `CREATE EXTERNAL TABLE` statements
- **Multi-Cloud Support**: Works with local storage, Amazon S3, and Azure Blob Storage
- **Command-Line Interface**: Easy-to-use CLI for batch processing
- **Comprehensive Parameter Support**: Includes all parameters from Microsoft SQL Server's external file format specification

## Supported File Types

- **Text files** (.txt)
- **CSV files** (.csv)
- **JSON files** (.json)
- **Parquet files** (.parquet)
- **Delta Lake files** (.delta)
- **ORC files** (.orc)
- **RC files** (.rc)

## Installation

```bash
pip install -e .
```

The project also includes a minimal `pyproject.toml`, so standard modern Python build tooling works as expected.

Optional Spark/Delta Spark support:

```bash
pip install -e .[spark]
```

## Quick Start

### Analyze a local directory

```bash
external-file-detector analyze /path/to/data/
```

### Analyze specific files

```bash
external-file-detector analyze-files file1.csv file2.json --data-source MyDataSource
```

### Generate external data source DDL

```bash
external-file-detector generate-data-source MyDataSource s3 's3://my-bucket/data/' --credential MyCredential
```

## Microsoft Fabric SQL Database Notes

- `OPENROWSET` is available in Fabric SQL Database (Data Virtualization):
  https://learn.microsoft.com/en-us/fabric/database/sql/data-virtualization
- `BULK INSERT` is **not** available in Fabric SQL Database.
- `COPY INTO` is **not** available in SQL Server, Azure SQL Database, Azure SQL Managed Instance, or Fabric SQL Database.

Use `OPENROWSET`-based loading patterns instead:

```sql
-- 1) Create a new table from external data
SELECT *
INTO dbo.stg_sales
FROM OPENROWSET(
    BULK 'https://<storage_account>.dfs.core.windows.net/<container>/sales/*.parquet',
    FORMAT = 'PARQUET'
) AS src;

-- 2) Insert into an existing table
INSERT INTO dbo.sales (order_id, customer_id, amount, order_date)
SELECT order_id, customer_id, amount, order_date
FROM OPENROWSET(
    BULK 'https://<storage_account>.dfs.core.windows.net/<container>/sales/*.parquet',
    FORMAT = 'PARQUET'
) AS src;
```

Other alternatives when `COPY INTO` is unavailable:
- `BULK INSERT` (SQL Server / Azure SQL MI / Azure SQL DB where supported)
- `OPENROWSET` + `OPENJSON` for JSON payloads
- Fabric Data Pipelines / Dataflows Gen2 for orchestrated ingestion

## CLI Commands

### `analyze`

Analyze all files in a directory and generate SQL DDL.

```bash
external-file-detector analyze <location> [OPTIONS]

Options:
  --data-source, -d TEXT          Name of the external data source for SQL DDL
  --output, -o TEXT               Output file path for results
  --format, -f [sql|json]         Output format (default: sql)
  --aws-access-key-id TEXT        AWS access key ID for S3 access
  --aws-secret-access-key TEXT    AWS secret access key for S3 access
  --aws-region TEXT               AWS region for S3 access (default: us-east-1)
  --azure-account-name TEXT       Azure storage account name
  --azure-account-key TEXT        Azure storage account key
  --azure-connection-string TEXT  Azure storage connection string
```

### `analyze-files`

Analyze specific files.

```bash
external-file-detector analyze-files <file1> [file2] ... [OPTIONS]

Options:
  --data-source, -d TEXT      Name of the external data source for SQL DDL
  --output, -o TEXT           Output file path for results
  --format, -f [sql|json]     Output format (default: sql)
```

### `generate-data-source`

Generate CREATE EXTERNAL DATA SOURCE statement.

```bash
external-file-detector generate-data-source <name> <storage_type> <location> [OPTIONS]

Arguments:
  name            Name of the data source
  storage_type    Type of storage (s3, azure, local)
  location        Base location/URL

Options:
  --credential TEXT    Name of the database credential to use
```

### `supported-types`

List supported file types.

```bash
external-file-detector supported-types
```

### `list-files`

List files at the specified location.

```bash
external-file-detector list-files <location> [OPTIONS]
```

## Storage Support

### Local Storage

Simply provide a local directory path:

```bash
external-file-detector analyze /home/user/data/
```

### Amazon S3

Provide S3 URLs and credentials:

```bash
external-file-detector analyze s3://my-bucket/data/ \
  --aws-access-key-id YOUR_ACCESS_KEY \
  --aws-secret-access-key YOUR_SECRET_KEY \
  --aws-region us-west-2
```

### Azure Blob Storage

Provide Azure URLs and credentials:

```bash
external-file-detector analyze azure://container/prefix \
  --azure-account-name mystorageaccount \
  --azure-account-key YOUR_ACCOUNT_KEY
```

Or use connection string:

```bash
external-file-detector analyze azure://container/prefix \
  --azure-connection-string "DefaultEndpointsProtocol=https;AccountName=..."
```

## Example Output

### CSV File Analysis

For a CSV file with employee data:

```sql
-- External File Format
CREATE EXTERNAL FILE FORMAT [ff_csv_format]
WITH (
    FORMAT_TYPE = DELIMITEDTEXT,
    FIELD_TERMINATOR = ',',
    STRING_DELIMITER = '"',
    USE_TYPE_DEFAULT = TRUE,
    ENCODING = 'UTF-8',
    FIRST_ROW = 2
);

-- External Table
CREATE EXTERNAL TABLE [ext_employees]
(
    [id] BIGINT,
    [name] NVARCHAR(MAX),
    [age] BIGINT,
    [salary] FLOAT,
    [department] NVARCHAR(MAX)
)
WITH (
    DATA_SOURCE = [MyDataSource],
    LOCATION = 'employees.csv',
    FILE_FORMAT = [ff_csv_format]
);
```

### JSON File Analysis

For a JSON file with user data:

```sql
-- External File Format
CREATE EXTERNAL FILE FORMAT [ff_json_format]
WITH (
    FORMAT_TYPE = JSON
);

-- External Table
CREATE EXTERNAL TABLE [ext_users]
(
    [id] INT,
    [name] NVARCHAR(MAX),
    [active] BIT,
    [joined_date] NVARCHAR(MAX)
)
WITH (
    DATA_SOURCE = [MyDataSource],
    LOCATION = 'users.json',
    FILE_FORMAT = [ff_json_format]
);
```

## SQL Server External File Format Parameters

The application supports all parameters from the [Microsoft SQL Server documentation](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-external-file-format-transact-sql?view=sql-server-ver17):

- `FORMAT_TYPE` - File format type (DELIMITEDTEXT, JSON, PARQUET, ORC, RCFILE)
- `FIELD_TERMINATOR` - Field terminator for delimited text files
- `STRING_DELIMITER` - String delimiter for delimited text files
- `DATE_FORMAT` - Date format specification
- `USE_TYPE_DEFAULT` - Use type default values for missing fields
- `ENCODING` - File encoding (UTF8, UTF16, etc.)
- `FIRST_ROW` - First row to start reading data
- `DATA_COMPRESSION` - Compression method (GZIP, SNAPPY, etc.)
- `ROW_TERMINATOR` - Row terminator for delimited text files
- `SERIALIZATION_ENCODING` - Serialization encoding for complex formats
- `SERIALIZER_METHOD` - Serializer method for complex formats
- `DESERIALIZER_METHOD` - Deserializer method for complex formats

## Architecture

The application consists of several key components:

- **FileDetector**: Detects file types and analyzes metadata
- **SQLGenerator**: Generates SQL DDL statements
- **StorageHandlers**: Handle different storage types (local, S3, Azure)
- **ExternalFileDetectorApp**: Main application orchestrator
- **CLI**: Command-line interface

## Development

### Running Tests

```bash
python tests/test_file_detector.py
python tests/test_sql_generator.py
```

### Project Structure

```
external_file_detection/
├── __init__.py
├── cli.py                    # Command-line interface
├── external_file_detector.py # Main application
├── file_detector.py          # File type detection and metadata analysis
├── sql_generator.py          # SQL DDL generation
└── storage_handlers.py       # Storage abstraction layer
```

## Requirements

- Python 3.8+
- pandas >= 1.5.0
- pyarrow >= 10.0.0
- boto3 >= 1.26.0 (for S3 support)
- azure-storage-blob >= 12.14.0 (for Azure support)
- azure-identity >= 1.12.0 (for Azure support)
- click >= 8.1.0 (for CLI)

## License

This project is open source and available under the MIT License.
