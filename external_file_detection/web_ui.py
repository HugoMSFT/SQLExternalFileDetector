"""Flask web UI for External File Detection.

This module is a backward-compatible wrapper around web_gui.py, which now
contains all routes (including /api/analyze-upload, /api/analyze-path,
/api/generate-ddl, /api/generate-data-source, and /api/export).

Use create_app() to get a Flask app, or run run_web_ui() to start
the server directly.
"""

import logging

from .web_gui import ExternalFileDetectionWebGUI, _safe_debug

logger = logging.getLogger(__name__)


def create_app(root_dir: str = None):
    """Create and configure the Flask application.

    Delegates to ExternalFileDetectionWebGUI which hosts every route.
    """
    gui = ExternalFileDetectionWebGUI(root_dir=root_dir)
    return gui.app


def run_web_ui(host: str = "127.0.0.1", port: int = 5000, debug: bool = False,
               root_dir: str = None):
    """Run the web UI server."""
    app = create_app(root_dir=root_dir)
    debug = _safe_debug(host, debug)
    print(f"\n  External File Detection Web UI")
    print(f"  Running at: http://{host}:{port}")
    print(f"  Press Ctrl+C to stop\n")
    app.run(host=host, port=port, debug=debug)
