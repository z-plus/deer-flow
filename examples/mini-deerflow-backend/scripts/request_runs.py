"""调用 Mini DeerFlow Gateway，创建 Run 并轮询执行结果。"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


# 本脚本只调用本机 Gateway，显式绕过系统代理，避免 localhost 被转发出去。
LOCAL_OPENER = build_opener(ProxyHandler({}))


def request_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """发送 JSON 请求，并把 JSON 响应转换为字典。"""

    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with LOCAL_OPENER.open(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"无法连接 Gateway: {exc.reason}") from exc


def create_run(base_url: str, thread_id: str, message: str) -> dict[str, Any]:
    """向 Gateway 提交一次异步 Agent Run。"""

    return request_json(
        "POST",
        f"{base_url}/api/threads/{thread_id}/runs",
        {"user_id": "request-script-user", "message": message},
    )


def wait_for_run(
    base_url: str,
    run_id: str,
    timeout_seconds: float = 60,
) -> dict[str, Any]:
    """轮询 Run，直到完成、失败或超时。"""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        run = request_json("GET", f"{base_url}/api/runs/{run_id}")
        print(f"当前状态: {run['status']}")
        if run["status"] in {"completed", "failed"}:
            return run
        time.sleep(0.5)
    raise TimeoutError(f"等待 Run 超时: {run_id}")


def main() -> None:
    """解析命令行参数并执行一次完整请求流程。"""

    parser = argparse.ArgumentParser(description="调用 Mini DeerFlow Gateway")
    parser.add_argument("message", nargs="?", default="请计算 18 加 24 等于多少")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--thread-id", default="request-demo-thread")
    args = parser.parse_args()

    created = create_run(args.base_url.rstrip("/"), args.thread_id, args.message)
    print("创建 Run:")
    print(json.dumps(created, ensure_ascii=False, indent=2))

    finished = wait_for_run(args.base_url.rstrip("/"), created["run_id"])
    print("最终结果:")
    print(json.dumps(finished, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
