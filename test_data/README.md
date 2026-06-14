# test_data samples

This folder contains local demo datasets for the External File Detection tool.
Designed to exercise edge cases in file-type detection, encoding detection,
delimiter sniffing, schema inference and table-format handling.

## CSV / delimited text
- sample.csv, employees.csv, employees_wide.csv, products_catalog.csv, sales_orders.csv
- web_access_logs.tsv (tab-delimited)
- transactions_pipe.csv (pipe-delimited)
- european_sales.csv (semicolon-delimited, comma decimal separator)
- no_header.csv (headerless CSV)
- messy_quoted.csv (quoted fields with commas, newlines, unicode)
- utf8_bom.csv (UTF-8 with byte-order mark)
- windows1252.csv (Windows-1252 / Latin-1 encoded)
- large_logs.csv (~2 MB — exercises row-count estimation)

## JSON
- sample.json, customers_nested.json (nested arrays/objects)
- events.jsonl (NDJSON / JSON Lines)
- sparse_events.jsonl (NDJSON where rows have different fields)
- single_object.json (root-level JSON object, not an array)
- deeply_nested.json (multi-level nested structure)

## Parquet
- sample.parquet, sales_transactions.parquet, sensor_readings.parquet
- types_showcase.parquet (int/float/decimal/timestamp/date/bool/nested)

## Excel
- inventory.xlsx (requires openpyxl)

## Table-style folders
- delta_table/: Delta-style layout with _delta_log and parquet data file
- iceberg_table/: Iceberg-style layout with v1.metadata.json
- iceberg_versioned/: Iceberg layout with v1 and v10 metadata — verifies that
  metadata version is picked by integer sort, not lexicographic (v10 > v2).
- sample_orders.delta/: additional Delta-style sample

Note: Delta/Iceberg folders are hand-crafted sample layouts. Install `deltalake`
and/or `pyiceberg` for richer metadata extraction, but the tool gracefully falls
back to parsing the log/metadata files directly when those packages are absent.
