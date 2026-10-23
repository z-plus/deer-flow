"""调用 Mini DeerFlow 的流式接口，收到一行就立即打印。"""

import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import json


def request_stream(
    base_url: str, thread_id: str, message: str, user_id: str,
    *, run_id: str | None = None, last_event_id: str | None = None,
) -> None:
    headers = {"Accept": "text/event-stream"}
    if run_id is not None:
        path = f"/api/runs/{quote(run_id, safe='')}/stream"
        data = None
        if last_event_id is not None:
            headers["Last-Event-ID"] = last_event_id
    else:
        path = f"/api/threads/{quote(thread_id, safe='')}/stream"
        data = json.dumps({"message": message, "user_id": user_id}).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers=headers,
        method="POST",
    )
    # SSE 是长连接；超时限制连续两次收到数据之间的等待时间。
    with urlopen(request, timeout=120) as response:
        for line in response:
            print(line.decode("utf-8").rstrip("\r\n"), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", nargs="?", default="请计算 12 + 30")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--thread-id", default="demo-thread")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--run-id", help="订阅已有 Run，而非创建新 Run")
    parser.add_argument("--last-event-id", help="从指定事件之后续传，需配合 --run-id")
    args = parser.parse_args(argv)
    if args.last_event_id is not None and not args.run_id:
        parser.error("--last-event-id 需要配合 --run-id")
    try:
        request_stream(
            args.base_url, args.thread_id, args.message, args.user_id,
            run_id=args.run_id, last_event_id=args.last_event_id,
        )
    except HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, OSError) as exc:
        print(f"流式请求失败: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
