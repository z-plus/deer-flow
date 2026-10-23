import runpy
from pathlib import Path
from unittest.mock import patch


def test_cli_starts_gateway():
    cli = runpy.run_path(str(Path(__file__).resolve().parents[1] / "app" / "cli.py"))
    with patch("sys.argv", ["mini-deerflow", "--port", "8003", "--reload"]):
        with patch("uvicorn.run") as run:
            cli["main"]()
    run.assert_called_once_with("app.gateway.app:app", host="127.0.0.1", port=8003, reload=True)
