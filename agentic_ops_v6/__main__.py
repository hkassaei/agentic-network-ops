"""CLI entry point for v6.

Usage:
    python -m agentic_ops_v6 "<question>"

Outputs JSON to stdout. Used by the chaos framework as a subprocess.
"""

import asyncio
import json
import logging
import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m agentic_ops_v6 <question>", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s: %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    from .orchestrator import investigate

    result = asyncio.run(investigate(question))
    json.dump(result, sys.stdout, indent=2, default=str)


if __name__ == "__main__":
    main()
