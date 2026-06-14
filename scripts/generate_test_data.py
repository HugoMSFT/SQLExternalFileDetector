from pathlib import Path
import json
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


root = Path('test_data')
root.mkdir(exist_ok=True)

employees = pd.DataFrame([
    {"employee_id": 1001, "first_name": "Alice", "last_name": "Ng", "department": "Engineering", "title": "Senior Engineer", "salary": 132500.75, "hire_date": "2021-03-15", "is_active": True, "office": "Seattle", "country": "USA"},
    {"employee_id": 1002, "first_name": "Bob", "last_name": "Patel", "department": "Finance", "title": "Analyst", "salary": 91500.00, "hire_date": "2022-09-01", "is_active": True, "office": "London", "country": "UK"},
    {"employee_id": 1003, "first_name": "Carla", "last_name": "Meyer", "department": "Sales", "title": "Account Manager", "salary": 105300.50, "hire_date": "2020-11-20", "is_active": False, "office": "Berlin", "country": "DE"},
])
employees.to_csv(root / 'employees_wide.csv', index=False)

orders = pd.DataFrame([
    {"order_id": "SO-001", "customer_id": 501, "region": "NA", "channel": "online", "item_count": 3, "subtotal": 89.90, "tax": 7.19, "shipping": 4.99, "total": 102.08, "order_ts": "2026-01-10T09:15:00Z"},
    {"order_id": "SO-002", "customer_id": 777, "region": "EU", "channel": "partner", "item_count": 1, "subtotal": 349.00, "tax": 69.80, "shipping": 0.00, "total": 418.80, "order_ts": "2026-01-11T14:42:00Z"},
    {"order_id": "SO-003", "customer_id": 321, "region": "APAC", "channel": "retail", "item_count": 2, "subtotal": 149.00, "tax": 11.92, "shipping": 6.50, "total": 167.42, "order_ts": "2026-01-12T18:05:00Z"},
])
orders.to_csv(root / 'sales_orders.csv', index=False)

customers = [
    {
        "customer_id": 501,
        "name": "Contoso Ltd",
        "tier": "gold",
        "contacts": [{"name": "Ana", "email": "ana@contoso.com"}, {"name": "Lee", "email": "lee@contoso.com"}],
        "address": {"city": "Seattle", "country": "USA"},
        "active": True,
    },
    {
        "customer_id": 777,
        "name": "Fabrikam GmbH",
        "tier": "silver",
        "contacts": [{"name": "Marta", "email": "marta@fabrikam.de"}],
        "address": {"city": "Berlin", "country": "DE"},
        "active": True,
    },
]
(root / 'customers_nested.json').write_text(json.dumps(customers, indent=2), encoding='utf-8')

jsonl_rows = [
    {"event_id": 1, "event_type": "login", "user_id": "u-100", "success": True, "ts": "2026-03-01T08:20:00Z"},
    {"event_id": 2, "event_type": "purchase", "user_id": "u-100", "success": True, "amount": 49.99, "ts": "2026-03-01T08:25:14Z"},
    {"event_id": 3, "event_type": "logout", "user_id": "u-100", "success": True, "ts": "2026-03-01T08:30:01Z"},
]
(root / 'events.jsonl').write_text("\n".join(json.dumps(r) for r in jsonl_rows) + "\n", encoding='utf-8')

delta_root = root / 'delta_table'
(delta_root / '_delta_log').mkdir(parents=True, exist_ok=True)
(delta_root / 'data').mkdir(parents=True, exist_ok=True)

delta_df = pd.DataFrame([
    {"id": 1, "product": "Laptop", "price": 1299.0, "category": "electronics"},
    {"id": 2, "product": "Chair", "price": 199.5, "category": "furniture"},
    {"id": 3, "product": "Notebook", "price": 4.2, "category": "office"},
])
parquet_rel = 'data/part-00000-00000.snappy.parquet'
pq.write_table(pa.Table.from_pandas(delta_df), delta_root / parquet_rel, compression='snappy')

delta_log = {
    "protocol": {"minReaderVersion": 1, "minWriterVersion": 2},
    "metaData": {
        "id": "sample-delta-table",
        "format": {"provider": "parquet", "options": {}},
        "schemaString": json.dumps({
            "type": "struct",
            "fields": [
                {"name": "id", "type": "long", "nullable": False, "metadata": {}},
                {"name": "product", "type": "string", "nullable": True, "metadata": {}},
                {"name": "price", "type": "double", "nullable": True, "metadata": {}},
                {"name": "category", "type": "string", "nullable": True, "metadata": {}},
            ],
        }),
        "partitionColumns": [],
        "configuration": {},
        "createdTime": 1760000000000,
    },
    "add": {
        "path": parquet_rel,
        "size": int((delta_root / parquet_rel).stat().st_size),
        "modificationTime": 1760000000000,
        "dataChange": True,
    },
}
(delta_root / '_delta_log' / '00000000000000000000.json').write_text(
    "\n".join(json.dumps({k: v}) for k, v in delta_log.items()) + "\n",
    encoding='utf-8'
)

iceberg_root = root / 'iceberg_table'
(iceberg_root / 'metadata').mkdir(parents=True, exist_ok=True)
(iceberg_root / 'data').mkdir(parents=True, exist_ok=True)

iceberg_df = pd.DataFrame([
    {"txn_id": "T-100", "store": "SEA-01", "amount": 120.5, "txn_date": "2026-02-01"},
    {"txn_id": "T-101", "store": "LON-04", "amount": 89.0, "txn_date": "2026-02-02"},
    {"txn_id": "T-102", "store": "BER-03", "amount": 210.7, "txn_date": "2026-02-03"},
])
iceberg_data_file = iceberg_root / 'data' / '00000-0.parquet'
pq.write_table(pa.Table.from_pandas(iceberg_df), iceberg_data_file, compression='snappy')

iceberg_metadata = {
    "format-version": 2,
    "table-uuid": "sample-iceberg-table",
    "location": str(iceberg_root.resolve()).replace('\\', '/'),
    "last-sequence-number": 1,
    "last-updated-ms": 1760000000000,
    "last-column-id": 4,
    "schema": {
        "type": "struct",
        "schema-id": 0,
        "fields": [
            {"id": 1, "name": "txn_id", "required": True, "type": "string"},
            {"id": 2, "name": "store", "required": False, "type": "string"},
            {"id": 3, "name": "amount", "required": False, "type": "double"},
            {"id": 4, "name": "txn_date", "required": False, "type": "date"},
        ],
    },
    "partition-spec": {"spec-id": 0, "fields": []},
    "sort-orders": [{"order-id": 0, "fields": []}],
    "default-sort-order-id": 0,
    "default-spec-id": 0,
    "current-snapshot-id": None,
    "snapshots": [],
    "snapshot-log": [],
    "metadata-log": [],
    "properties": {"write.format.default": "parquet"},
}
(iceberg_root / 'metadata' / 'v1.metadata.json').write_text(json.dumps(iceberg_metadata, indent=2), encoding='utf-8')

(root / 'README.md').write_text(
    '# test_data samples\n\n'
    'This folder contains local demo datasets for the External File Detection tool.\n'
    'Designed to exercise edge cases in file-type detection, encoding detection,\n'
    'delimiter sniffing, schema inference and table-format handling.\n\n'
    '## CSV / delimited text\n'
    '- sample.csv, employees.csv, employees_wide.csv, products_catalog.csv, sales_orders.csv\n'
    '- web_access_logs.tsv (tab-delimited)\n'
    '- transactions_pipe.csv (pipe-delimited)\n'
    '- european_sales.csv (semicolon-delimited, comma decimal separator)\n'
    '- no_header.csv (headerless CSV)\n'
    '- messy_quoted.csv (quoted fields with commas, newlines, unicode)\n'
    '- utf8_bom.csv (UTF-8 with byte-order mark)\n'
    '- windows1252.csv (Windows-1252 / Latin-1 encoded)\n'
    '- large_logs.csv (~2 MB — exercises row-count estimation)\n\n'
    '## JSON\n'
    '- sample.json, customers_nested.json (nested arrays/objects)\n'
    '- events.jsonl (NDJSON / JSON Lines)\n'
    '- sparse_events.jsonl (NDJSON where rows have different fields)\n'
    '- single_object.json (root-level JSON object, not an array)\n'
    '- deeply_nested.json (multi-level nested structure)\n\n'
    '## Parquet\n'
    '- sample.parquet, sales_transactions.parquet, sensor_readings.parquet\n'
    '- types_showcase.parquet (int/float/decimal/timestamp/date/bool/nested)\n\n'
    '## Excel\n'
    '- inventory.xlsx (requires openpyxl)\n\n'
    '## Table-style folders\n'
    '- delta_table/: Delta-style layout with _delta_log and parquet data file\n'
    '- iceberg_table/: Iceberg-style layout with v1.metadata.json\n'
    '- iceberg_versioned/: Iceberg layout with v1 and v10 metadata — verifies that\n'
    '  metadata version is picked by integer sort, not lexicographic (v10 > v2).\n'
    '- sample_orders.delta/: additional Delta-style sample\n\n'
    'Note: Delta/Iceberg folders are hand-crafted sample layouts. Install `deltalake`\n'
    'and/or `pyiceberg` for richer metadata extraction, but the tool gracefully falls\n'
    'back to parsing the log/metadata files directly when those packages are absent.\n',
    encoding='utf-8'
)

# ---------------------------------------------------------------------------
# Extended samples — edge cases for delimiter, encoding, schema inference, etc.
# ---------------------------------------------------------------------------

# Pipe-delimited CSV
(root / 'transactions_pipe.csv').write_text(
    "txn_id|account|amount|currency|posted_on\n"
    "TX-1001|ACCT-100|1250.50|USD|2026-04-01\n"
    "TX-1002|ACCT-205|   89.99|EUR|2026-04-02\n"
    "TX-1003|ACCT-100|-45.00|USD|2026-04-03\n"
    "TX-1004|ACCT-311|9999.00|JPY|2026-04-03\n",
    encoding='utf-8'
)

# Semicolon-delimited CSV with comma decimal separator (European style)
(root / 'european_sales.csv').write_text(
    "product;qty;unit_price;total;sold_on\n"
    "Widget A;3;19,95;59,85;2026-03-15\n"
    "Widget B;1;249,00;249,00;2026-03-16\n"
    "Widget C;12;4,50;54,00;2026-03-17\n",
    encoding='utf-8'
)

# Headerless CSV
(root / 'no_header.csv').write_text(
    "1,2026-01-01,alpha,12.5\n"
    "2,2026-01-02,bravo,7.0\n"
    "3,2026-01-03,charlie,19.75\n"
    "4,2026-01-04,delta,0.5\n",
    encoding='utf-8'
)

# CSV with quoted fields containing commas, newlines and unicode
(root / 'messy_quoted.csv').write_text(
    'id,description,notes,price\n'
    '1,"Hello, world","Line1\nLine2",9.99\n'
    '2,"Café ☕ — grande","Contains, commas and ""quotes""",4.25\n'
    '3,"Simple item","",1.00\n',
    encoding='utf-8'
)

# UTF-8 BOM CSV
(root / 'utf8_bom.csv').write_bytes(
    b'\xef\xbb\xbf' + b'name,city,score\nJos\xc3\xa9,S\xc3\xa3o Paulo,92\nBj\xc3\xb6rn,Stockholm,87\n'
)

# Windows-1252 (Latin-1 superset) CSV
_w1252_content = "name,city,note\nJosé,Málaga,Olé!\nRené,Montréal,Très bien\n"
(root / 'windows1252.csv').write_bytes(_w1252_content.encode('cp1252'))

# ~2 MB CSV to exercise row-count estimation for files above LARGE_FILE_THRESHOLD
# (threshold is 100 MB so this won't actually trigger estimation, but gives a bigger file)
with open(root / 'large_logs.csv', 'w', encoding='utf-8') as f:
    f.write("ts,level,service,message\n")
    for i in range(50000):
        f.write(f"2026-04-{(i % 30) + 1:02d}T12:00:{i % 60:02d}Z,INFO,svc-{i % 8},"
                f"Request {i} completed in {i % 500} ms\n")

# Sparse NDJSON — rows have different fields to exercise schema union
sparse_rows = [
    {"event_id": 1, "type": "login", "user_id": "u-1"},
    {"event_id": 2, "type": "purchase", "user_id": "u-1", "amount": 12.5, "currency": "USD"},
    {"event_id": 3, "type": "error", "user_id": "u-2", "error_code": 500, "message": "boom"},
    {"event_id": 4, "type": "logout", "user_id": "u-1", "session_ms": 480000},
]
(root / 'sparse_events.jsonl').write_text(
    "\n".join(json.dumps(r) for r in sparse_rows) + "\n", encoding='utf-8'
)

# Single root JSON object (not an array)
(root / 'single_object.json').write_text(json.dumps({
    "report_id": "R-2026-04-16",
    "generated_at": "2026-04-16T08:00:00Z",
    "totals": {"orders": 1284, "revenue": 95412.33, "refunds": 12},
    "tags": ["daily", "sales", "auto"],
}, indent=2), encoding='utf-8')

# Deeply nested JSON
(root / 'deeply_nested.json').write_text(json.dumps([
    {
        "org": "Contoso",
        "departments": [
            {
                "name": "Engineering",
                "teams": [
                    {
                        "name": "Backend",
                        "members": [
                            {"id": 1, "name": "Alice", "skills": ["python", "sql"]},
                            {"id": 2, "name": "Bob", "skills": ["go", "rust"]},
                        ],
                    },
                    {"name": "Frontend", "members": []},
                ],
            },
        ],
    }
], indent=2), encoding='utf-8')

# Parquet showcasing diverse Arrow types
types_table = pa.table({
    "id": pa.array([1, 2, 3], type=pa.int64()),
    "code": pa.array(["A", "B", "C"], type=pa.string()),
    "ratio": pa.array([0.25, 0.5, 0.75], type=pa.float32()),
    "amount": pa.array([1250.50, 89.99, 10000.00], type=pa.float64()),
    "is_active": pa.array([True, False, True], type=pa.bool_()),
    "event_date": pa.array([
        pd.Timestamp("2026-01-01").date(),
        pd.Timestamp("2026-02-15").date(),
        pd.Timestamp("2026-03-30").date(),
    ], type=pa.date32()),
    "event_ts": pa.array([
        pd.Timestamp("2026-01-01T09:00:00"),
        pd.Timestamp("2026-02-15T14:30:00"),
        pd.Timestamp("2026-03-30T22:15:00"),
    ], type=pa.timestamp("us")),
    "payload": pa.array([
        {"k": "a", "v": 1},
        {"k": "b", "v": 2},
        {"k": "c", "v": 3},
    ]),
})
pq.write_table(types_table, root / 'types_showcase.parquet', compression='snappy')

# Excel (.xlsx) — best-effort; skip if openpyxl unavailable
try:
    inventory = pd.DataFrame([
        {"sku": "SKU-001", "name": "Widget", "stock": 120, "reorder_at": 25, "unit_price": 9.99},
        {"sku": "SKU-002", "name": "Gadget", "stock": 38, "reorder_at": 10, "unit_price": 19.49},
        {"sku": "SKU-003", "name": "Gizmo", "stock": 0, "reorder_at": 5, "unit_price": 4.25},
    ])
    inventory.to_excel(root / 'inventory.xlsx', index=False, engine='openpyxl')
except Exception as exc:
    print(f"Skipped inventory.xlsx (install openpyxl to generate it): {exc}")

# Iceberg table with v1 and v10 metadata — verifies integer-version sort
iceberg_v_root = root / 'iceberg_versioned'
(iceberg_v_root / 'metadata').mkdir(parents=True, exist_ok=True)
(iceberg_v_root / 'data').mkdir(parents=True, exist_ok=True)

iceberg_v_df = pd.DataFrame([
    {"metric_id": "M-1", "metric_name": "latency_ms", "value": 42.1, "recorded_on": "2026-04-01"},
    {"metric_id": "M-2", "metric_name": "throughput", "value": 1285.0, "recorded_on": "2026-04-02"},
])
pq.write_table(
    pa.Table.from_pandas(iceberg_v_df),
    iceberg_v_root / 'data' / '00000-0.parquet',
    compression='snappy',
)

_iceberg_v_meta_template = {
    "format-version": 2,
    "table-uuid": "sample-iceberg-versioned",
    "location": str(iceberg_v_root.resolve()).replace('\\', '/'),
    "last-sequence-number": 1,
    "last-updated-ms": 1760000000000,
    "last-column-id": 4,
    "schema": {
        "type": "struct",
        "schema-id": 0,
        "fields": [
            {"id": 1, "name": "metric_id",   "required": True,  "type": "string"},
            {"id": 2, "name": "metric_name", "required": False, "type": "string"},
            {"id": 3, "name": "value",       "required": False, "type": "double"},
            {"id": 4, "name": "recorded_on", "required": False, "type": "date"},
        ],
    },
    "partition-spec": {"spec-id": 0, "fields": []},
    "sort-orders": [{"order-id": 0, "fields": []}],
    "default-sort-order-id": 0,
    "default-spec-id": 0,
    "current-snapshot-id": None,
    "snapshots": [],
    "snapshot-log": [],
    "metadata-log": [],
    "properties": {"write.format.default": "parquet", "note": "v1 metadata"},
}
(iceberg_v_root / 'metadata' / 'v1.metadata.json').write_text(
    json.dumps(_iceberg_v_meta_template, indent=2), encoding='utf-8'
)

_iceberg_v10 = dict(_iceberg_v_meta_template)
_iceberg_v10["last-sequence-number"] = 10
_iceberg_v10["last-updated-ms"] = 1761000000000
_iceberg_v10["properties"] = {"write.format.default": "parquet", "note": "v10 metadata (latest)"}
(iceberg_v_root / 'metadata' / 'v10.metadata.json').write_text(
    json.dumps(_iceberg_v10, indent=2), encoding='utf-8'
)

print('Created extended sample datasets in test_data/')
