#!/usr/bin/env python3
import argparse
import json
import shlex
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote


def run(command: str) -> str:
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or command)
    return result.stdout.strip()


def build_link(username: str, password: str, domain: str, port: int) -> str:
    encoded_username = quote(username, safe="")
    encoded_password = quote(password, safe="")
    label = quote(f"VPN_{username}", safe="")
    return f"ssh://{encoded_username}:{encoded_password}@{domain}:{port}#{label}"


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def cmd_create(args: argparse.Namespace) -> None:
    username = shlex.quote(args.username)
    exists = subprocess.run(
        f"id -u {username}",
        shell=True,
        capture_output=True,
        text=True,
    )
    if exists.returncode != 0:
        run(f"useradd -M -s /usr/sbin/nologin {username}")
    run(f"echo {shlex.quote(args.username + ':' + args.password)} | chpasswd")
    expire_at = datetime.now(timezone.utc) + timedelta(days=args.expire_days)
    run(f"chage -E {expire_at.date().isoformat()} {username}")
    run(f"usermod -U {username}")
    uid = run(f"id -u {username}")
    traffic_setup = Path("/usr/local/bin/setup_user_traffic.sh")
    if traffic_setup.exists():
        run(f"{traffic_setup} {username} {uid}")
    print_json(
        {
            "ok": True,
            "username": args.username,
            "password": args.password,
            "expires_at": expire_at.isoformat(),
            "max_connections": args.max_connections,
            "import_link": build_link(args.username, args.password, args.domain, args.port),
        }
    )


def cmd_renew(args: argparse.Namespace) -> None:
    username = shlex.quote(args.username)
    run(f"usermod -U {username}")
    run(f"chage -E {args.expire_date} {username}")
    print_json({"ok": True, "username": args.username, "expires_at": args.expire_date})


def cmd_lock(args: argparse.Namespace) -> None:
    username = shlex.quote(args.username)
    run(f"usermod -L {username}")
    subprocess.run(f"pkill -u {username}", shell=True, capture_output=True, text=True)
    print_json({"ok": True, "username": args.username, "locked": True})


def cmd_passwd(args: argparse.Namespace) -> None:
    username = shlex.quote(args.username)
    run(f"echo {shlex.quote(args.username + ':' + args.password)} | chpasswd")
    run(f"usermod -U {username}")
    print_json({"ok": True, "username": args.username, "password": args.password})


def cmd_traffic(args: argparse.Namespace) -> None:
    username = shlex.quote(args.username)
    traffic_script = Path("/usr/local/bin/read_user_traffic.sh")
    if traffic_script.exists():
        output = run(f"{traffic_script} {username}")
        try:
            payload = json.loads(output)
            print_json({"ok": True, "username": args.username, "bytes_used": int(payload.get("bytes_used", 0))})
            return
        except Exception:
            pass
    print_json({"ok": True, "username": args.username, "bytes_used": 0})


def cmd_exists(args: argparse.Namespace) -> None:
    username = shlex.quote(args.username)
    result = subprocess.run(
        f"id -u {username}",
        shell=True,
        capture_output=True,
        text=True,
    )
    print_json({"ok": True, "username": args.username, "exists": result.returncode == 0})


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--username", required=True)
    create_parser.add_argument("--password", required=True)
    create_parser.add_argument("--expire-days", type=int, required=True)
    create_parser.add_argument("--domain", required=True)
    create_parser.add_argument("--port", type=int, required=True)
    create_parser.add_argument("--max-connections", type=int, default=1)
    create_parser.set_defaults(func=cmd_create)

    renew_parser = subparsers.add_parser("renew")
    renew_parser.add_argument("--username", required=True)
    renew_parser.add_argument("--expire-date", required=True)
    renew_parser.set_defaults(func=cmd_renew)

    lock_parser = subparsers.add_parser("lock")
    lock_parser.add_argument("--username", required=True)
    lock_parser.set_defaults(func=cmd_lock)

    passwd_parser = subparsers.add_parser("passwd")
    passwd_parser.add_argument("--username", required=True)
    passwd_parser.add_argument("--password", required=True)
    passwd_parser.set_defaults(func=cmd_passwd)

    traffic_parser = subparsers.add_parser("traffic")
    traffic_parser.add_argument("--username", required=True)
    traffic_parser.set_defaults(func=cmd_traffic)

    exists_parser = subparsers.add_parser("exists")
    exists_parser.add_argument("--username", required=True)
    exists_parser.set_defaults(func=cmd_exists)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
