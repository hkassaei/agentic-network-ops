#!/usr/bin/env python3
"""Check availability of Gemini models on Vertex AI.

Usage:
    python check-model-availability.py                  # test all known models
    python check-model-availability.py --list            # list all available models
    python check-model-availability.py --filter gemini-3 # list models matching filter
    python check-model-availability.py --test gemini-2.5-flash  # test a specific model
"""

import argparse
import os
import sys

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

from google import genai

# Models to test — update this list as new models become available
MODELS_TO_TEST = [
    # 2.x series (GA)
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    # 3.x series (preview)
    "gemini-3.1-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
]


def test_model(client: genai.Client, model: str) -> tuple[bool, str]:
    """Test if a model is available by sending a minimal request."""
    try:
        r = client.models.generate_content(model=model, contents="hi")
        return True, r.text[:80] if r.text else "OK (empty response)"
    except Exception as e:
        return False, str(e)[:120]


def test_all(client: genai.Client, models: list[str] | None = None):
    """Test all models and print results."""
    targets = models or MODELS_TO_TEST
    print(f"Testing {len(targets)} models (project: {os.environ['GOOGLE_CLOUD_PROJECT']}, "
          f"location: {os.environ['GOOGLE_CLOUD_LOCATION']})")
    print()

    max_len = max(len(m) for m in targets)
    for model in targets:
        ok, detail = test_model(client, model)
        status = "OK" if ok else "FAIL"
        icon = "✓" if ok else "✗"
        print(f"  {icon} {model:<{max_len}}  {status}  {detail}")


def list_models(client: genai.Client, filter_str: str | None = None):
    """List all available models, optionally filtered."""
    print(f"Available models (project: {os.environ['GOOGLE_CLOUD_PROJECT']}, "
          f"location: {os.environ['GOOGLE_CLOUD_LOCATION']})")
    if filter_str:
        print(f"Filter: {filter_str}")
    print()

    count = 0
    for model in client.models.list():
        if filter_str and filter_str not in model.name:
            continue
        print(f"  {model.name}")
        count += 1

    print(f"\n{count} models found")


def main():
    parser = argparse.ArgumentParser(description="Check Gemini model availability on Vertex AI")
    parser.add_argument("--list", action="store_true", help="List all available models")
    parser.add_argument("--filter", type=str, help="Filter model list (e.g., 'gemini-3')")
    parser.add_argument("--test", type=str, help="Test a specific model by name")
    parser.add_argument("--project", type=str, help="Override GOOGLE_CLOUD_PROJECT")
    parser.add_argument("--location", type=str, help="Override GOOGLE_CLOUD_LOCATION")
    args = parser.parse_args()

    if args.project:
        os.environ["GOOGLE_CLOUD_PROJECT"] = args.project
    if args.location:
        os.environ["GOOGLE_CLOUD_LOCATION"] = args.location

    client = genai.Client()

    if args.list or args.filter:
        list_models(client, args.filter)
    elif args.test:
        test_all(client, [args.test])
    else:
        test_all(client)


if __name__ == "__main__":
    main()
