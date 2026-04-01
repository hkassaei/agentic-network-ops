"""
CLI entry point for running a v5 investigation.

Usage:
    python -m agentic_ops_v5 "The 5G SA + IMS stack is experiencing issues."

Outputs JSON to stdout with the full investigation result.
Used by the chaos challenger to invoke v5 as a subprocess.
"""

import asyncio
import json
import logging
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m agentic_ops_v5 <question>", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # Quiet logging to stderr so stdout is clean JSON
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s: %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    from .orchestrator import investigate

    result = asyncio.run(investigate(question))

    # Output clean JSON to stdout
    json.dump(result, sys.stdout, indent=2, default=str)


if __name__ == "__main__":
    main()
