import gzip
import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from kai import diag, logs

FAKE_KEY = "AIza" + "S" * 35


def test_redact_removes_keys_and_home():
    text = f"key {FAKE_KEY} url ?key=abc123&x=1 token AQ.Ab8RN6IKx9wxeTYUWKxx path {Path.home()}/x"
    out = logs.redact(text)
    assert FAKE_KEY not in out
    assert "abc123" not in out
    assert "AQ.Ab8" not in out
    assert str(Path.home()) not in out
    assert "key=[REDACTED]" in out


def test_report_never_contains_the_key(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    log = tmp_path / "kai.log"
    log.write_text(f"something logged {FAKE_KEY}\n")
    monkeypatch.setattr(logs, "log_file", lambda: log)
    report = diag.collect()
    assert report["api_key"]["configured"] and report["api_key"]["source"] == "env"
    assert FAKE_KEY not in json.dumps(report)
    assert "something logged" in report["log"]


@pytest.fixture
def server(tmp_path):
    path = Path(__file__).parents[1] / "server" / "diag_server.py"
    spec = importlib.util.spec_from_file_location("diag_server", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.args = type("Args", (), {"dir": str(tmp_path)})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/kai-diag/upload", tmp_path
    httpd.shutdown()


def _post(url, body, gz=True):
    data = gzip.compress(body) if gz else body
    headers = {"Content-Type": "application/json"}
    if gz:
        headers["Content-Encoding"] = "gzip"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_server_stores_valid_report_and_rate_limits(server):
    url, folder = server
    report = {"kai_version": "0", "system": {}, "log": "hello"}
    status, body = _post(url, json.dumps(report).encode())
    assert status == 200 and len(body["id"]) == 8
    saved = list(folder.glob("*.json"))
    assert len(saved) == 1 and json.loads(saved[0].read_text())["log"] == "hello"
    status, _ = _post(url, json.dumps(report).encode())
    assert status == 429


def test_server_rejects_invalid_reports(server):
    url, folder = server
    assert _post(url, b"not json")[0] == 400
    assert not list(folder.glob("*.json"))
