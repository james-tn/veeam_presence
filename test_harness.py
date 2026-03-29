"""Veeam Presence — CLI Test Harness.

Interactive conversation loop for local testing.
Uses Claude API with tool_use against real pre-computed data.

Usage:
    python test_harness.py
    python test_harness.py --question "How's Prague trending?"
"""

import sys
import os
import json
import argparse

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))
import config

# Verify prerequisites
if not config.ANTHROPIC_API_KEY:
    print("ERROR: ANTHROPIC_API_KEY not set. Run via run_harness.ps1 or set the env var.")
    sys.exit(1)

if not os.path.exists(os.path.join(config.DATA_DIR, "baselines.pkl")):
    print("ERROR: Pipeline data not found. Run run_pipeline.ps1 first.")
    sys.exit(1)

from agent import run_agent
from tools.query_office_intel import load_cache
from tools.query_person import _load_enriched
load_cache()        # Pre-load Tier 1 cache
_load_enriched()    # Pre-load person data

# Card JSON output directory
os.makedirs(config.OUTPUT_DIR, exist_ok=True)


def display_response(text):
    """Display response — detect card JSON and format accordingly."""
    # Check if response contains a JSON card
    try:
        # Look for JSON block in the response
        if '{"card": true' in text or '{"card":true' in text:
            # Extract JSON from markdown code block if present
            if "```json" in text:
                start = text.index("```json") + 7
                end = text.index("```", start)
                card_json = text[start:end].strip()
            elif "```" in text:
                start = text.index("```") + 3
                end = text.index("```", start)
                card_json = text[start:end].strip()
            else:
                card_json = text.strip()

            card = json.loads(card_json)
            # Save card JSON
            card_file = os.path.join(config.OUTPUT_DIR, "last_card.json")
            with open(card_file, "w") as f:
                json.dump(card, f, indent=2)
            print(f"  [Card JSON saved to {card_file}]")
            # Display formatted
            print(f"\n  [{card.get('template', 'unknown')}] [{card.get('card_tone', 'default')}]")
            print(f"  {card.get('summary', card.get('headline', ''))}")
            if card.get("body"):
                print(f"  {card['body']}")
            for fact in card.get("facts", []):
                print(f"    {fact['title']}: {fact['value']}")
            if card.get("context_note"):
                print(f"  ({card['context_note']})")
            for action in card.get("actions", []):
                print(f"    [{action['label']}]")
            return
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    # Plain text response
    print(f"\n{text}")


def run_interactive():
    """Interactive conversation loop."""
    print("=" * 60)
    print("VEEAM PRESENCE — Test Harness")
    print("=" * 60)
    print("Type a question. Type 'quit' to exit, 'reset' to clear history.\n")

    history = []

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            break
        if question.lower() == "reset":
            history = []
            print("  [History cleared]\n")
            continue

        print("  [Thinking...]", flush=True)
        try:
            response, history = run_agent(question, history)
            display_response(response)
        except Exception as e:
            print(f"  ERROR: {e}")
        print()


def run_single(question):
    """Run a single question and exit."""
    print(f"Q: {question}")
    print("  [Thinking...]", flush=True)
    response, _ = run_agent(question)
    display_response(response)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Veeam Presence Test Harness")
    parser.add_argument("--question", "-q", help="Single question mode (non-interactive)")
    args = parser.parse_args()

    if args.question:
        run_single(args.question)
    else:
        run_interactive()
