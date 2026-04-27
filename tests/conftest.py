"""Shared test fixtures for External File Detection tests."""

import csv
import json
import os
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq
import pytest


@pytest.fixture
def temp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def sample_csv(temp_dir):
    """Create a sample CSV file and return its path."""
    path = os.path.join(temp_dir, "sample.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "age"])
        writer.writerow([1, "Alice", 30])
        writer.writerow([2, "Bob", 25])
        writer.writerow([3, "Charlie", 35])
    return path


@pytest.fixture
def sample_json(temp_dir):
    """Create a sample JSON file and return its path."""
    path = os.path.join(temp_dir, "sample.json")
    data = [
        {"id": 1, "name": "Alice", "active": True},
        {"id": 2, "name": "Bob", "active": False},
    ]
    with open(path, "w") as f:
        json.dump(data, f)
    return path


@pytest.fixture
def sample_ndjson(temp_dir):
    """Create a sample NDJSON file and return its path."""
    path = os.path.join(temp_dir, "sample.jsonl")
    with open(path, "w") as f:
        f.write('{"id": 1, "name": "Alice"}\n')
        f.write('{"id": 2, "name": "Bob"}\n')
    return path


@pytest.fixture
def sample_tsv(temp_dir):
    """Create a sample TSV file and return its path."""
    path = os.path.join(temp_dir, "data.tsv")
    with open(path, "w") as f:
        f.write("id\tname\tage\n1\tAlice\t30\n2\tBob\t25\n")
    return path


@pytest.fixture
def sample_parquet(temp_dir):
    """Create a sample Parquet file and return its path."""
    path = os.path.join(temp_dir, "sample.parquet")
    table = pa.table({
        "id": pa.array([1, 2, 3]),
        "name": pa.array(["Alice", "Bob", "Charlie"]),
        "score": pa.array([95.5, 87.3, 92.1]),
    })
    pq.write_table(table, path)
    return path


@pytest.fixture
def sample_text(temp_dir):
    """Create a sample text file and return its path."""
    path = os.path.join(temp_dir, "notes.txt")
    with open(path, "w") as f:
        f.write("Line 1\nLine 2\nLine 3\n")
    return path


@pytest.fixture
def empty_csv(temp_dir):
    """Create an empty CSV file and return its path."""
    path = os.path.join(temp_dir, "empty.csv")
    with open(path, "w") as f:
        pass
    return path


@pytest.fixture
def wide_csv(temp_dir):
    """Create a CSV with many columns and return its path."""
    path = os.path.join(temp_dir, "wide.csv")
    cols = [f"col_{i}" for i in range(25)]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        writer.writerow(list(range(25)))
        writer.writerow(list(range(25, 50)))
    return path


@pytest.fixture
def nested_json(temp_dir):
    """Create a JSON file with nested objects and return its path."""
    path = os.path.join(temp_dir, "nested.json")
    data = [
        {"id": 1, "name": "Alice", "address": {"city": "NYC", "zip": "10001"}, "tags": ["admin", "user"]},
        {"id": 2, "name": "Bob", "address": {"city": "LA", "zip": "90001"}, "tags": ["user"]},
    ]
    with open(path, "w") as f:
        json.dump(data, f)
    return path


@pytest.fixture
def delta_dir(temp_dir):
    """Create a minimal Delta table directory structure and return its path."""
    delta_path = os.path.join(temp_dir, "delta_table")
    os.makedirs(os.path.join(delta_path, "_delta_log"))
    # Create a dummy parquet file
    with open(os.path.join(delta_path, "part-0.parquet"), "wb") as f:
        f.write(b"PAR1" + b"\x00" * 100)
    return delta_path
