import io
import json
import runpy
from pathlib import Path
from unittest.mock import Mock, patch


def test_request_stream_posts_json_and_prints_sse(capsys):
    script = Path(__file__).resolve().parents[1] / "scripts" / "request_stream.py"
    request_stream = runpy.run_path(str(script))["request_stream"]
    sse = 'event: message\ndata: {"content": "你好"}\n\n'
    open_url = Mock(return_value=io.BytesIO(sse.encode("utf-8")))
    with patch.dict(request_stream.__globals__, urlopen=open_url):
        request_stream("http://localhost:8001/", "demo thread", "你好", "local-user")

    request = open_url.call_args.args[0]
    assert request.full_url == "http://localhost:8001/api/threads/demo%20thread/stream"
    assert request.method == "POST"
    assert json.loads(request.data) == {"message": "你好", "user_id": "local-user"}
    assert request.get_header("Accept") == "text/event-stream"
    assert capsys.readouterr().out == sse


def test_stream_existing_run_sends_resume_header_without_body(capsys):
    script = Path(__file__).resolve().parents[1] / "scripts" / "request_stream.py"
    request_stream = runpy.run_path(str(script))["request_stream"]
    open_url = Mock(return_value=io.BytesIO(b"event: status\ndata: {}\n\n"))
    with patch.dict(request_stream.__globals__, urlopen=open_url):
        request_stream(
            "http://localhost:8001", "unused", "unused", "unused",
            run_id="run 123", last_event_id="7",
        )

    request = open_url.call_args.args[0]
    assert request.full_url == "http://localhost:8001/api/runs/run%20123/stream"
    assert request.method == "POST"
    assert request.data is None
    assert request.get_header("Last-event-id") == "7"
    assert capsys.readouterr().out == "event: status\ndata: {}\n\n"
