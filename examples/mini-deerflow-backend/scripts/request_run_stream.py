"""订阅已有 Run 的 SSE 流，可携带 Last-Event-ID 续传。"""

import argparse
import sys

from request_stream import main as request_main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="创建 Run 接口返回的 run_id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--last-event-id", help="从指定事件之后续传")
    args = parser.parse_args()
    arguments = ["--run-id", args.run_id, "--base-url", args.base_url]
    if args.last_event_id is not None:
        arguments.extend(["--last-event-id", args.last_event_id])
    return request_main(arguments)


if __name__ == "__main__":
    sys.exit(main())
