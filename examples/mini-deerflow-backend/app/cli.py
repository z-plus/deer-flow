"""Mini DeerFlow Web 服务的命令行入口。"""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("app.gateway.app:app", host=args.host, port=args.port, reload=args.reload)

if __name__ == "__main__":
    main()