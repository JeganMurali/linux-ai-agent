"""
Headless tests for the Omarchy plugin's JavaScript (chatEvents.js), run inside
real Qt via `qml6` on the offscreen platform. The plugin lives outside this
repo for now, so point KOKKI_PLUGIN_DIR at it (default: the installed copy).
"""
import http.server
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

PLUGIN_DIR = Path(os.environ.get("KOKKI_PLUGIN_DIR", Path.home() / ".config/omarchy/plugins/kokki"))
QML_DIR = Path(__file__).parent / "qml"
QML_RUNNER = shutil.which("qml6")

pytestmark = pytest.mark.skipif(
    not QML_RUNNER or not (PLUGIN_DIR / "chatEvents.js").exists(),
    reason="needs qml6 and the plugin's chatEvents.js (set KOKKI_PLUGIN_DIR)",
)


def run_qml(workdir, name):
    # Without FORCE_STDERR, Qt routes console.log to the journal, not stderr.
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_FORCE_STDERR_LOGGING": "1"}
    return subprocess.run(
        [QML_RUNNER, name], cwd=workdir, env=env,
        capture_output=True, text=True, timeout=30,
    )


def stage(tmp_path, template, **substitutions):
    """Copy the plugin's JS next to a harness so its relative import works."""
    shutil.copy(PLUGIN_DIR / "chatEvents.js", tmp_path / "chatEvents.js")
    source = (QML_DIR / template).read_text()
    for key, value in substitutions.items():
        source = source.replace(key, value)
    (tmp_path / "harness.qml").write_text(source)
    return "harness.qml"


def test_chat_events_logic_passes_headless(tmp_path):
    result = run_qml(tmp_path, stage(tmp_path, "chat_events_test.qml"))
    output = result.stdout + result.stderr
    assert "ALL PASSED" in output, output
    assert result.returncode == 0, output


@pytest.fixture
def request_counter():
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], hits
    server.shutdown()


def render_markdown(tmp_path, port, text_expr):
    name = stage(tmp_path, "markdown_image_test.qml", __PORT__=str(port), __TEXT_EXPR__=text_expr)
    result = run_qml(tmp_path, name)
    assert result.returncode == 0, result.stdout + result.stderr


def test_unsanitized_markdown_fetches_images_which_is_why_we_sanitize(tmp_path, request_counter):
    port, hits = request_counter
    render_markdown(tmp_path, port, "raw")
    assert {"/inline.png", "/ref.png"} <= set(hits), hits


def test_sanitized_markdown_makes_no_network_request(tmp_path, request_counter):
    port, hits = request_counter
    render_markdown(tmp_path, port, "CE.safeMarkdown(raw)")
    assert hits == []
