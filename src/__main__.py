"""CLI entry point: python -m kaizen create-key --label "my-team"."""

import argparse
import asyncio
import secrets
import sys

from src.api.auth import hash_api_key
from src.database import async_session_factory
from src.models.base import ApiKey


async def _create_key(label: str) -> str:
    raw_key = "kaizen_" + secrets.token_hex(16)
    key_hash = hash_api_key(raw_key)

    async with async_session_factory() as session:
        row = ApiKey(key_hash=key_hash, label=label)
        session.add(row)
        await session.commit()

    return raw_key


def main() -> None:
    parser = argparse.ArgumentParser(prog="kaizen")
    sub = parser.add_subparsers(dest="command")

    create_key_parser = sub.add_parser("create-key", help="Create a new API key")
    create_key_parser.add_argument("--label", default="cli", help="Key label")

    args = parser.parse_args()

    if args.command == "create-key":
        key = asyncio.run(_create_key(args.label))
        print(key)  # noqa: T201
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
