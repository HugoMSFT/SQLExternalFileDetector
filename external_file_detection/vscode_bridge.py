"""
VS Code extension bridge — JSON-based interface for the extension to call.

Usage:
    python -m external_file_detection.vscode_bridge <command> [args_json]

Commands:
    analyze_file <path>       — Analyze a single file, return metadata JSON
    analyze_folder <path>     — Analyze all files in folder recursively
    generate_ddl <metadata_json> — Generate SQL DDL from metadata
    generate_all <metadata_json> — Generate all SQL statement types
    preview_data <path> [max_rows] — Get tabular preview data
    supported_types           — List supported file types
"""

import json
import sys
import os
import traceback


def _get_detector():
    from external_file_detection.file_detector import FileDetector
    return FileDetector()


def _get_generator():
    from external_file_detection.sql_generator import SQLGenerator
    return SQLGenerator()


def _clean_metadata(metadata: dict) -> dict:
    """Ensure metadata is JSON-serializable."""
    import math

    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_clean(v) for v in obj]
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        return obj

    return _clean(metadata)


def cmd_analyze_file(file_path: str) -> dict:
    detector = _get_detector()
    file_type = detector.detect_file_type(file_path)
    metadata = detector.analyze_file_metadata(file_path)
    return _clean_metadata({
        "file_path": file_path,
        "file_name": os.path.basename(file_path),
        "file_type": file_type,
        "metadata": metadata
    })


def cmd_analyze_folder(folder_path: str) -> dict:
    detector = _get_detector()
    results = detector.scan_directory(folder_path)
    cleaned = [_clean_metadata(r) for r in results]
    return {"folder": folder_path, "files": cleaned, "count": len(cleaned)}


def cmd_generate_ddl(args: dict) -> dict:
    generator = _get_generator()
    metadata = args.get("metadata", {})
    table_name = args.get("table_name", "MyTable")
    schema_name = args.get("schema_name", "dbo")
    data_source = args.get("data_source", "MyExternalDataSource")
    file_format = args.get("file_format", "")
    location = args.get("location", metadata.get("file_path", ""))
    target_platform = args.get("target_platform", "sql_server_2022")
    credential_name = args.get("credential_name", "")

    statements = {}

    try:
        statements["create_table"] = generator.generate_create_table(
            metadata, table_name, schema_name, target_platform
        )
    except Exception as e:
        statements["create_table"] = f"-- Error: {e}"

    try:
        statements["external_table"] = generator.generate_external_table(
            metadata, table_name, data_source, location,
            file_format or f"{table_name}Format",
            schema_name=schema_name, target_platform=target_platform
        )
    except Exception as e:
        statements["external_table"] = f"-- Error: {e}"

    try:
        statements["external_file_format"] = generator.generate_external_file_format(
            metadata, file_format or f"{table_name}Format", target_platform
        )
    except Exception as e:
        statements["external_file_format"] = f"-- Error: {e}"

    try:
        statements["openrowset"] = generator.generate_openrowset(
            metadata, location, credential_name, target_platform
        )
    except Exception as e:
        statements["openrowset"] = f"-- Error: {e}"

    file_type = metadata.get("file_type", "")
    if file_type in ("csv", "tsv", "txt"):
        try:
            statements["bulk_insert"] = generator.generate_bulk_insert(
                metadata, table_name, location, target_platform
            )
        except Exception as e:
            statements["bulk_insert"] = f"-- Error: {e}"

    if file_type in ("json", "jsonl", "ndjson"):
        try:
            statements["json_functions"] = generator.generate_json_functions(
                metadata, table_name, target_platform
            )
        except Exception as e:
            statements["json_functions"] = f"-- Error: {e}"

    try:
        statements["best_practices"] = generator.generate_best_practices(
            metadata, target_platform
        )
    except Exception as e:
        statements["best_practices"] = f"-- Error: {e}"

    try:
        statements["credential_setup"] = generator.generate_credential_setup(
            data_source, file_format or f"{table_name}Format",
            metadata, target_platform
        )
    except Exception as e:
        statements["credential_setup"] = f"-- Error: {e}"

    return {"statements": statements, "table_name": table_name}


def cmd_generate_all(args: dict) -> dict:
    generator = _get_generator()
    metadata = args.get("metadata", {})
    table_name = args.get("table_name", "MyTable")
    schema_name = args.get("schema_name", "dbo")
    data_source = args.get("data_source", "MyExternalDataSource")
    file_format = args.get("file_format", "")
    location = args.get("location", metadata.get("file_path", ""))
    target_platform = args.get("target_platform", "sql_server_2022")

    try:
        all_stmts = generator.generate_all_statements(
            metadata,
            table_name=table_name,
            schema_name=schema_name,
            data_source=data_source,
            location=location,
            file_format=file_format or f"{table_name}Format",
            target_platform=target_platform,
        )
        return {"statements": all_stmts, "table_name": table_name}
    except Exception as e:
        return {"error": str(e)}


def cmd_preview_data(args: dict) -> dict:
    detector = _get_detector()
    file_path = args if isinstance(args, str) else args.get("file_path", "")
    max_rows = 100 if isinstance(args, str) else args.get("max_rows", 100)
    preview = detector.get_preview_data(file_path, max_rows=max_rows)
    return _clean_metadata(preview)


def cmd_supported_types() -> dict:
    return {
        "types": [
            {"extension": ".csv", "name": "CSV (Comma-separated)"},
            {"extension": ".tsv", "name": "TSV (Tab-separated)"},
            {"extension": ".txt", "name": "Text file"},
            {"extension": ".json", "name": "JSON"},
            {"extension": ".jsonl", "name": "JSON Lines"},
            {"extension": ".ndjson", "name": "Newline-delimited JSON"},
            {"extension": ".parquet", "name": "Apache Parquet"},
            {"extension": ".orc", "name": "Apache ORC"},
            {"extension": ".xlsx", "name": "Excel (XLSX)"},
            {"extension": ".xls", "name": "Excel (XLS)"},
            {"extension": ".delta", "name": "Delta Lake table"},
            {"extension": ".iceberg", "name": "Apache Iceberg table"},
        ]
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: vscode_bridge <command> [args]"}))
        sys.exit(1)

    command = sys.argv[1]
    args_raw = sys.argv[2] if len(sys.argv) > 2 else "{}"

    try:
        if command == "analyze_file":
            result = cmd_analyze_file(args_raw)
        elif command == "analyze_folder":
            result = cmd_analyze_folder(args_raw)
        elif command == "generate_ddl":
            result = cmd_generate_ddl(json.loads(args_raw))
        elif command == "generate_all":
            result = cmd_generate_all(json.loads(args_raw))
        elif command == "preview_data":
            try:
                parsed = json.loads(args_raw)
            except json.JSONDecodeError:
                parsed = args_raw
            result = cmd_preview_data(parsed)
        elif command == "supported_types":
            result = cmd_supported_types()
        else:
            result = {"error": f"Unknown command: {command}"}

        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({
            "error": str(e),
            "traceback": traceback.format_exc()
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
