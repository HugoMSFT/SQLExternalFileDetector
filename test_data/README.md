# test_data samples

This folder contains local demo datasets for the External File Detection tool.

## Files
- sample.csv, sample.json, sample.parquet, sample.txt
- employees_wide.csv (wider CSV schema)
- sales_orders.csv (numeric/date-heavy CSV)
- customers_nested.json (nested JSON array)
- events.jsonl (NDJSON / JSON Lines)

## Table-style folders
- delta_table/: Delta-style layout with _delta_log and parquet data file
- iceberg_table/: Iceberg-style layout with metadata and parquet data file

Note: The Delta and Iceberg folders are sample layouts for testing tooling and metadata handling.
