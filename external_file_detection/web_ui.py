"""Flask web UI for External File Detection."""

import os
import json
import logging
import tempfile
from pathlib import Path
from typing import Dict, Any

from flask import Flask, render_template, request, jsonify, send_file

from .file_detector import FileDetector
from .sql_generator import SQLGenerator
from .external_file_detector import ExternalFileDetectorApp

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB upload limit
    app.secret_key = os.urandom(24)

    # Shared instances
    file_detector = FileDetector()
    sql_generator = SQLGenerator()

    @app.route("/")
    def index():
        """Main page."""
        return render_template("index.html")

    @app.route("/api/supported-types", methods=["GET"])
    def supported_types():
        """Return supported file types."""
        detector_app = ExternalFileDetectorApp()
        return jsonify({"types": detector_app.get_supported_file_types()})

    @app.route("/api/analyze-upload", methods=["POST"])
    def analyze_upload():
        """Analyze uploaded files."""
        if "files" not in request.files:
            return jsonify({"error": "No files uploaded"}), 400

        files = request.files.getlist("files")
        data_source = request.form.get("data_source", "")
        results = []

        with tempfile.TemporaryDirectory() as temp_dir:
            for uploaded_file in files:
                if uploaded_file.filename:
                    safe_name = Path(uploaded_file.filename).name
                    temp_path = os.path.join(temp_dir, safe_name)
                    uploaded_file.save(temp_path)

                    try:
                        metadata = file_detector.analyze_file_metadata(temp_path)
                        table_name = _generate_table_name(safe_name)
                        ddl = sql_generator.generate_complete_ddl(
                            metadata,
                            table_name,
                            data_source if data_source else None,
                            uploaded_file.filename,
                        )

                        # Make metadata JSON-serializable
                        clean_metadata = _clean_metadata(metadata)

                        results.append(
                            {
                                "file_name": uploaded_file.filename,
                                "metadata": clean_metadata,
                                "sql_ddl": ddl,
                                "table_name": table_name,
                                "success": True,
                            }
                        )
                    except Exception as e:
                        logger.exception("Error analyzing %s", uploaded_file.filename)
                        results.append(
                            {
                                "file_name": uploaded_file.filename,
                                "error": str(e),
                                "success": False,
                            }
                        )

        return jsonify({"results": results, "total": len(results)})

    @app.route("/api/analyze-path", methods=["POST"])
    def analyze_path():
        """Analyze files at a local path."""
        data = request.get_json()
        if not data or "path" not in data:
            return jsonify({"error": "No path specified"}), 400

        location = data["path"]
        if not isinstance(location, str) or not location.strip():
            return jsonify({"error": "Path cannot be empty"}), 400
        location = location.strip()
        if len(location) > 2048:
            return jsonify({"error": "Path too long"}), 400
        if '..' in Path(location).parts:
            return jsonify({"error": "Path traversal not allowed"}), 400

        data_source = data.get("data_source", "")
        storage_config = {}

        # Cloud storage credentials
        if data.get("aws_access_key_id"):
            storage_config["aws_access_key_id"] = data["aws_access_key_id"]
        if data.get("aws_secret_access_key"):
            storage_config["aws_secret_access_key"] = data["aws_secret_access_key"]
        if data.get("aws_region"):
            storage_config["region_name"] = data["aws_region"]
        if data.get("azure_account_name"):
            storage_config["azure_account_name"] = data["azure_account_name"]
        if data.get("azure_account_key"):
            storage_config["azure_account_key"] = data["azure_account_key"]
        if data.get("azure_connection_string"):
            storage_config["azure_connection_string"] = data["azure_connection_string"]

        try:
            app_instance = ExternalFileDetectorApp(storage_config)
            results = app_instance.analyze_location(
                location, data_source if data_source else None
            )

            # Clean results for JSON serialization
            clean_results = _clean_results(results)
            return jsonify(clean_results)
        except Exception as e:
            logger.exception("Error analyzing path %s", location)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/generate-data-source", methods=["POST"])
    def generate_data_source():
        """Generate CREATE EXTERNAL DATA SOURCE DDL."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required = ["name", "storage_type", "location"]
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

        try:
            app_instance = ExternalFileDetectorApp()
            ddl = app_instance.generate_data_source_ddl(
                data["name"],
                data["storage_type"],
                data["location"],
                data.get("credential"),
            )
            return jsonify({"sql_ddl": ddl})
        except Exception as e:
            logger.exception("Error generating data source DDL")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/generate-ddl", methods=["POST"])
    def generate_ddl():
        """Generate DDL from manual metadata input."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        file_type = data.get("file_type", "csv")
        table_name = data.get("table_name", "ext_table")
        data_source = data.get("data_source")
        location = data.get("location", "")
        columns = data.get("columns", [])

        metadata = {
            "file_type": file_type,
            "file_path": location,
            "schema": [(col["name"], col["type"]) for col in columns] if columns else None,
            "delimiter": data.get("delimiter", ","),
            "has_header": data.get("has_header", True),
            "encoding": data.get("encoding", "utf-8"),
            "compression": data.get("compression"),
        }

        try:
            ddl = sql_generator.generate_complete_ddl(
                metadata, table_name, data_source, location
            )
            return jsonify({"sql_ddl": ddl})
        except Exception as e:
            logger.exception("Error generating DDL")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/export", methods=["POST"])
    def export_results():
        """Export results as a downloadable file."""
        data = request.get_json()
        if not data or "content" not in data:
            return jsonify({"error": "No content provided"}), 400

        fmt = data.get("format", "sql")
        content = data["content"]

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=f".{fmt}",
            delete=False,
            prefix="efd_export_",
        ) as f:
            f.write(content)
            temp_path = f.name

        try:
            return send_file(
                temp_path,
                as_attachment=True,
                download_name=f"external_file_detection.{fmt}",
                mimetype="text/plain" if fmt == "sql" else "application/json",
            )
        finally:
            # Clean up after send (Flask handles this after response)
            pass

    return app


def _generate_table_name(filename: str) -> str:
    """Generate a SQL table name from a filename."""
    name = Path(filename).stem
    clean = "".join(c if c.isalnum() else "_" for c in name)
    if clean and clean[0].isdigit():
        clean = "tbl_" + clean
    return f"ext_{clean}" if clean else "ext_table"


def _clean_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Make metadata JSON-serializable."""
    cleaned = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool, type(None))):
            cleaned[key] = value
        elif isinstance(value, list):
            cleaned[key] = [
                list(item) if isinstance(item, tuple) else item for item in value
            ]
        else:
            cleaned[key] = str(value)
    return cleaned


def _clean_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively clean results for JSON serialization."""
    if isinstance(results, dict):
        return {k: _clean_results(v) for k, v in results.items()}
    elif isinstance(results, list):
        return [_clean_results(item) for item in results]
    elif isinstance(results, tuple):
        return list(results)
    elif isinstance(results, (str, int, float, bool, type(None))):
        return results
    else:
        return str(results)


def run_web_ui(host: str = "127.0.0.1", port: int = 5000, debug: bool = False):
    """Run the web UI server."""
    app = create_app()
    print(f"\n  External File Detection Web UI")
    print(f"  Running at: http://{host}:{port}")
    print(f"  Press Ctrl+C to stop\n")
    app.run(host=host, port=port, debug=debug)
