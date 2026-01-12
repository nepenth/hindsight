#!/usr/bin/env python3
"""
Profile a single recall operation to identify performance bottlenecks.

Usage:
    # With pyinstrument (async-aware profiler):
    EXTERNAL_DATABASE_URL="postgresql://hindsight:hindsight@localhost:5435/hindsight" \
        python scripts/profile_recall.py --bank load-test --query "What do I like?"

    # Generate HTML report:
    EXTERNAL_DATABASE_URL="postgresql://hindsight:hindsight@localhost:5435/hindsight" \
        python scripts/profile_recall.py --bank load-test --query "What do I like?" --html profile.html
"""

import argparse
import asyncio
import os
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run_recall(bank_id: str, query: str, max_tokens: int = 4096):
    """Run a single recall operation."""
    from hindsight_api import MemoryEngine, RequestContext
    from hindsight_api.engine.memory_engine import Budget

    # Create engine
    engine = MemoryEngine(run_migrations=False)
    await engine.initialize()

    try:
        # Run recall
        ctx = RequestContext()
        result = await engine.recall_async(
            bank_id=bank_id,
            query=query,
            budget=Budget.HIGH,
            max_tokens=max_tokens,
            request_context=ctx,
        )
        print(f"\nRecall returned {len(result.results)} facts")
        return result
    finally:
        await engine.close()


async def main():
    parser = argparse.ArgumentParser(description="Profile a recall operation")
    parser.add_argument("--bank", required=True, help="Bank ID to query")
    parser.add_argument("--query", required=True, help="Query text")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max tokens to return")
    parser.add_argument("--html", help="Output HTML profile to this file")
    parser.add_argument("--no-profile", action="store_true", help="Run without profiling")
    args = parser.parse_args()

    if args.no_profile:
        await run_recall(args.bank, args.query, args.max_tokens)
        return

    # Use pyinstrument for async-aware profiling
    try:
        from pyinstrument import Profiler
    except ImportError:
        print("pyinstrument not installed. Run: uv add pyinstrument")
        sys.exit(1)

    profiler = Profiler(async_mode="enabled")

    print(f"Profiling recall: bank={args.bank}, query={args.query!r}")
    print("-" * 60)

    profiler.start()
    try:
        await run_recall(args.bank, args.query, args.max_tokens)
    finally:
        profiler.stop()

    # Output results
    if args.html:
        with open(args.html, "w") as f:
            f.write(profiler.output_html())
        print(f"\nProfile saved to {args.html}")
    else:
        print(profiler.output_text(unicode=True, color=True))


if __name__ == "__main__":
    asyncio.run(main())
