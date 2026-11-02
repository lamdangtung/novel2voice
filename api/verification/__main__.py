import argparse
import json

from api.verification import WorkspaceError, WorkspaceManager, self_check


def main():
    parser = argparse.ArgumentParser(description="T02: workspace kiểm thử offline, tách khỏi input/output thật.")
    parser.add_argument("command", choices=["init", "status", "reset", "self-check"])
    parser.add_argument("--workspace", default="demo", help="Tên workspace con trong .verification/workspaces.")
    parser.add_argument("--confirm", default="", help="Reset yêu cầu RESET <tên>.")
    parser.add_argument("--fail-provider", choices=["none", "tts", "translator"], default="none")
    parser.add_argument("--fail-on-call", type=int, default=None)
    parser.add_argument("--fail-chapter", default="")
    parser.add_argument("--delay-ms", type=int, default=0)
    args = parser.parse_args()
    try:
        manager = WorkspaceManager()
        if args.command == "init":
            result = manager.create(args.workspace)
        elif args.command == "reset":
            result = manager.reset(args.workspace, args.confirm)
        elif args.command == "status":
            result = manager.describe(args.workspace)
        else:
            result = self_check(manager, args.workspace, fail_provider=args.fail_provider,
                                fail_on_call=args.fail_on_call, fail_chapter=args.fail_chapter, delay_ms=args.delay_ms)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") == "failed" else 0
    except (WorkspaceError, ValueError) as error:
        print(json.dumps({"error": {"code": getattr(error, "code", "INVALID_OPTIONS"), "message": str(error)}}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
