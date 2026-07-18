"""Flask web UI for External File Detection.

This module is a backward-compatible wrapper around web_gui.py, which now
contains all routes (including /api/analyze-upload, /api/analyze-path,
/api/generate-ddl, /api/generate-data-source, and /api/export).

Use create_app() to get a Flask app, or run run_web_ui() to start
the server directly.
"""

from .web_gui import ExternalFileDetectionWebGUI


def create_app(root_dir: str = None):
    """Create and configure the Flask application.

    Delegates to ExternalFileDetectionWebGUI which hosts every route.
    """
    gui = ExternalFileDetectionWebGUI(root_dir=root_dir)
    return gui.app


def run_web_ui(host: str = "127.0.0.1", port: int = 5000, debug: bool = False,
               root_dir: str = None):
    """Run the web UI server."""
    gui = ExternalFileDetectionWebGUI(root_dir=root_dir)
    gui.run(host=host, port=port, debug=debug)
