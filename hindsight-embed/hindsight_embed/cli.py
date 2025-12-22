"""
Hindsight Embedded CLI.

A simple CLI for local memory operations using embedded PostgreSQL (pg0).
No external server required - runs everything locally.

Usage:
    hindsight-embed configure              # Interactive setup
    hindsight-embed retain "User prefers dark mode"
    hindsight-embed recall "What are user preferences?"

Environment variables:
    HINDSIGHT_EMBED_LLM_API_KEY: Required. API key for LLM provider.
    HINDSIGHT_EMBED_LLM_PROVIDER: Optional. LLM provider (default: "openai").
    HINDSIGHT_EMBED_LLM_MODEL: Optional. LLM model (default: "gpt-4o-mini").
    HINDSIGHT_EMBED_BANK_ID: Optional. Memory bank ID (default: "default").
    HINDSIGHT_EMBED_LOG_LEVEL: Optional. Log level (default: "warning").
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".hindsight"
CONFIG_FILE = CONFIG_DIR / "embed"


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level_str = os.environ.get("HINDSIGHT_EMBED_LOG_LEVEL", "info").lower()
    if verbose:
        level_str = "debug"

    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    level = level_map.get(level_str, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        stream=sys.stderr,
    )
    return logging.getLogger(__name__)


def load_config_file():
    """Load configuration from file if it exists."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    # Handle 'export VAR=value' format
                    if line.startswith("export "):
                        line = line[7:]
                    key, value = line.split("=", 1)
                    if key not in os.environ:  # Don't override env vars
                        os.environ[key] = value


def get_config():
    """Get configuration from environment variables."""
    load_config_file()
    return {
        "llm_api_key": os.environ.get("HINDSIGHT_EMBED_LLM_API_KEY")
            or os.environ.get("HINDSIGHT_API_LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY"),
        "llm_provider": os.environ.get("HINDSIGHT_EMBED_LLM_PROVIDER")
            or os.environ.get("HINDSIGHT_API_LLM_PROVIDER", "openai"),
        "llm_model": os.environ.get("HINDSIGHT_EMBED_LLM_MODEL")
            or os.environ.get("HINDSIGHT_API_LLM_MODEL", "gpt-4o-mini"),
        "bank_id": os.environ.get("HINDSIGHT_EMBED_BANK_ID", "default"),
    }


def do_configure(args):
    """Interactive configuration setup with beautiful TUI."""
    import questionary
    from questionary import Style

    # If stdin is not a terminal (e.g., running via curl | bash),
    # reopen stdin from /dev/tty for interactive prompts
    if not sys.stdin.isatty():
        try:
            sys.stdin = open('/dev/tty', 'r')
        except OSError:
            print("Error: Cannot run interactive configuration without a terminal.", file=sys.stderr)
            print("Run directly: uvx hindsight-embed configure", file=sys.stderr)
            return 1

    # Custom style for the prompts
    custom_style = Style([
        ('qmark', 'fg:cyan bold'),
        ('question', 'fg:white bold'),
        ('answer', 'fg:cyan'),
        ('pointer', 'fg:cyan bold'),
        ('highlighted', 'fg:cyan bold'),
        ('selected', 'fg:green'),
        ('text', 'fg:white'),
    ])

    print()
    print("\033[1m\033[36m  ╭─────────────────────────────────────╮\033[0m")
    print("\033[1m\033[36m  │   Hindsight Embed Configuration    │\033[0m")
    print("\033[1m\033[36m  ╰─────────────────────────────────────╯\033[0m")
    print()

    # Check existing config
    if CONFIG_FILE.exists():
        if not questionary.confirm(
            "Existing configuration found. Reconfigure?",
            default=False,
            style=custom_style,
        ).ask():
            print("\n\033[32m✓\033[0m Keeping existing configuration.")
            return 0
        print()

    # Provider selection with descriptions
    providers = [
        questionary.Choice("OpenAI (recommended)", value=("openai", "o3-mini", "OpenAI")),
        questionary.Choice("Groq (fast & free tier)", value=("groq", "openai/gpt-oss-20b", "Groq")),
        questionary.Choice("Google Gemini", value=("google", "gemini-2.0-flash", "Google")),
        questionary.Choice("Ollama (local, no API key)", value=("ollama", "llama3.2", None)),
    ]

    result = questionary.select(
        "Select your LLM provider:",
        choices=providers,
        style=custom_style,
    ).ask()

    if result is None:  # User cancelled
        print("\n\033[33m⚠\033[0m Configuration cancelled.")
        return 1

    provider, default_model, key_name = result

    # API key
    api_key = ""
    if key_name:
        env_keys = {
            "OpenAI": "OPENAI_API_KEY",
            "Groq": "GROQ_API_KEY",
            "Google": "GOOGLE_API_KEY",
        }
        env_key = env_keys.get(key_name, "")
        existing = os.environ.get(env_key, "")

        if existing:
            masked = existing[:8] + "..." + existing[-4:] if len(existing) > 12 else "***"
            if questionary.confirm(
                f"Found {key_name} key in ${env_key} ({masked}). Use it?",
                default=True,
                style=custom_style,
            ).ask():
                api_key = existing

        if not api_key:
            api_key = questionary.password(
                f"Enter your {key_name} API key:",
                style=custom_style,
            ).ask()

            if not api_key:
                print("\n\033[31m✗\033[0m API key is required.", file=sys.stderr)
                return 1

    # Model selection
    model = questionary.text(
        "Model name:",
        default=default_model,
        style=custom_style,
    ).ask()

    if model is None:
        return 1

    # Bank ID
    bank_id = questionary.text(
        "Memory bank ID:",
        default="default",
        style=custom_style,
    ).ask()

    if bank_id is None:
        return 1

    # Save configuration
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_FILE, "w") as f:
        f.write("# Hindsight Embed Configuration\n")
        f.write(f"# Generated by hindsight-embed configure\n\n")
        f.write(f"HINDSIGHT_EMBED_LLM_PROVIDER={provider}\n")
        f.write(f"HINDSIGHT_EMBED_LLM_MODEL={model}\n")
        f.write(f"HINDSIGHT_EMBED_BANK_ID={bank_id}\n")
        if api_key:
            f.write(f"HINDSIGHT_EMBED_LLM_API_KEY={api_key}\n")

    CONFIG_FILE.chmod(0o600)

    # Stop existing daemon if running (it needs to pick up new config)
    from . import daemon_client

    if daemon_client._is_daemon_running():
        print("\n  \033[2mRestarting daemon with new configuration...\033[0m")
        daemon_client.stop_daemon()

    # Start daemon with new config
    new_config = {
        "llm_api_key": api_key,
        "llm_provider": provider,
        "llm_model": model,
        "bank_id": bank_id,
    }
    if daemon_client.ensure_daemon_running(new_config):
        print("  \033[32m✓ Daemon started\033[0m")
    else:
        print("  \033[33m⚠ Failed to start daemon (will start on first command)\033[0m")

    print()
    print("\033[32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m")
    print("\033[32m  ✓ Configuration saved!\033[0m")
    print("\033[32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m")
    print()
    print(f"  \033[2mConfig:\033[0m {CONFIG_FILE}")
    print()
    print("  \033[2mTest with:\033[0m")
    print('    \033[36mhindsight-embed retain "Test memory"\033[0m')
    print('    \033[36mhindsight-embed recall "test"\033[0m')
    print()

    return 0


def do_daemon(args, config: dict, logger):
    """Handle daemon subcommands."""
    from pathlib import Path
    from . import daemon_client

    daemon_log_path = Path.home() / ".hindsight" / "daemon.log"

    if args.daemon_command == "start":
        if daemon_client._is_daemon_running():
            print("Daemon is already running")
            return 0

        print("Starting daemon...")
        if daemon_client.ensure_daemon_running(config):
            print("Daemon started successfully")
            print(f"  Port: {daemon_client.DAEMON_PORT}")
            print(f"  Logs: {daemon_log_path}")
            return 0
        else:
            print("Failed to start daemon", file=sys.stderr)
            return 1

    elif args.daemon_command == "stop":
        if not daemon_client._is_daemon_running():
            print("Daemon is not running")
            return 0

        print("Stopping daemon...")
        if daemon_client.stop_daemon():
            print("Daemon stopped")
            return 0
        else:
            print("Failed to stop daemon", file=sys.stderr)
            return 1

    elif args.daemon_command == "status":
        if daemon_client._is_daemon_running():
            # Get PID from lockfile
            lockfile = Path.home() / ".hindsight" / "daemon.lock"
            pid = "unknown"
            if lockfile.exists():
                try:
                    pid = lockfile.read_text().strip()
                except Exception:
                    pass
            print(f"Daemon is running (PID: {pid})")
            print(f"  URL: http://127.0.0.1:{daemon_client.DAEMON_PORT}")
            print(f"  Logs: {daemon_log_path}")
            return 0
        else:
            print("Daemon is not running")
            return 1

    elif args.daemon_command == "logs":
        if not daemon_log_path.exists():
            print("No daemon logs found", file=sys.stderr)
            print(f"  Expected at: {daemon_log_path}")
            return 1

        if args.follow:
            # Follow mode - like tail -f
            import subprocess
            try:
                subprocess.run(["tail", "-f", str(daemon_log_path)])
            except KeyboardInterrupt:
                pass
            return 0
        else:
            # Show last N lines
            try:
                with open(daemon_log_path) as f:
                    lines = f.readlines()
                    for line in lines[-args.lines:]:
                        print(line, end="")
                return 0
            except Exception as e:
                print(f"Error reading logs: {e}", file=sys.stderr)
                return 1

    else:
        print("Usage: hindsight-embed daemon {start|stop|status|logs}", file=sys.stderr)
        return 1


async def do_retain(args, config: dict, logger):
    """Execute retain command via daemon."""
    from . import daemon_client

    logger.info(f"Retaining memory: {args.content[:50]}...")

    # Ensure daemon is running
    if not daemon_client.ensure_daemon_running(config):
        print("Error: Failed to start daemon", file=sys.stderr)
        return 1

    try:
        logger.debug("Calling daemon retain API...")
        await daemon_client.retain(
            bank_id=config["bank_id"],
            content=args.content,
            context=args.context or "general",
        )
        msg = f"Stored memory: {args.content[:50]}..." if len(args.content) > 50 else f"Stored memory: {args.content}"
        print(msg, flush=True)
        return 0
    except Exception as e:
        logger.error(f"Retain failed: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        return 1


async def do_recall(args, config: dict, logger):
    """Execute recall command via daemon."""
    import json
    from . import daemon_client

    logger.info(f"Recalling with query: {args.query}")

    # Ensure daemon is running
    if not daemon_client.ensure_daemon_running(config):
        print("Error: Failed to start daemon", file=sys.stderr)
        return 1

    try:
        logger.debug(f"Calling daemon recall API with budget={args.budget}...")
        result = await daemon_client.recall(
            bank_id=config["bank_id"],
            query=args.query,
            budget=args.budget.lower(),
            max_tokens=args.max_tokens,
        )

        # The API returns the results directly
        results = result.get("results", [])
        logger.debug(f"Recall returned {len(results)} results")

        # Output JSON response
        output = {
            "query": args.query,
            "results": [
                {
                    "text": fact.get("text"),
                    "type": fact.get("type"),
                    "occurred_start": fact.get("occurred_start"),
                    "occurred_end": fact.get("occurred_end"),
                    "entities": fact.get("entities", []),
                    "context": fact.get("context"),
                }
                for fact in results
            ],
            "total": len(results),
        }
        print(json.dumps(output, indent=2), flush=True)

        return 0
    except Exception as e:
        logger.error(f"Recall failed: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Hindsight Embedded CLI - local memory operations without a server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    hindsight-embed configure                              # Interactive setup
    hindsight-embed retain "User prefers dark mode"
    hindsight-embed retain "Meeting on Monday" -c work
    hindsight-embed recall "user preferences"
    hindsight-embed recall "meetings" --budget high

Daemon management:
    hindsight-embed daemon status                          # Check if daemon is running
    hindsight-embed daemon start                           # Start the daemon
    hindsight-embed daemon stop                            # Stop the daemon
    hindsight-embed daemon logs                            # View daemon logs
    hindsight-embed daemon logs -f                         # Follow daemon logs
        """
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Configure command
    subparsers.add_parser("configure", help="Interactive configuration setup")

    # Daemon command with subcommands
    daemon_parser = subparsers.add_parser("daemon", help="Manage the background daemon")
    daemon_subparsers = daemon_parser.add_subparsers(dest="daemon_command", help="Daemon commands")
    daemon_subparsers.add_parser("start", help="Start the daemon")
    daemon_subparsers.add_parser("stop", help="Stop the daemon")
    daemon_subparsers.add_parser("status", help="Check daemon status")
    daemon_logs_parser = daemon_subparsers.add_parser("logs", help="View daemon logs")
    daemon_logs_parser.add_argument(
        "--follow", "-f",
        action="store_true",
        help="Follow log output (like tail -f)"
    )
    daemon_logs_parser.add_argument(
        "--lines", "-n",
        type=int,
        default=50,
        help="Number of lines to show (default: 50)"
    )

    # Retain command
    retain_parser = subparsers.add_parser("retain", help="Store a memory")
    retain_parser.add_argument("content", help="The memory content to store")
    retain_parser.add_argument(
        "--context", "-c",
        help="Category for the memory (e.g., 'preferences', 'work')",
        default="general"
    )

    # Recall command
    recall_parser = subparsers.add_parser("recall", help="Search memories")
    recall_parser.add_argument("query", help="Search query")
    recall_parser.add_argument(
        "--budget", "-b",
        choices=["low", "mid", "high"],
        default="low",
        help="Search budget level (default: low)"
    )
    recall_parser.add_argument(
        "--max-tokens", "-m",
        type=int,
        default=4096,
        help="Maximum tokens in results (default: 4096)"
    )
    recall_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show additional details"
    )

    args = parser.parse_args()

    # Setup logging
    verbose = getattr(args, 'verbose', False)
    logger = setup_logging(verbose)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Handle configure separately (no config needed)
    if args.command == "configure":
        exit_code = do_configure(args)
        sys.exit(exit_code)

    # Handle daemon commands (some don't need config)
    if args.command == "daemon":
        config = get_config()
        exit_code = do_daemon(args, config, logger)
        sys.exit(exit_code)

    config = get_config()

    # Check for LLM API key
    if not config["llm_api_key"]:
        print("Error: LLM API key is required.", file=sys.stderr)
        print("Run 'hindsight-embed configure' to set up.", file=sys.stderr)
        sys.exit(1)

    # Run the appropriate command
    exit_code = 1
    try:
        if args.command == "retain":
            exit_code = asyncio.run(do_retain(args, config, logger))
        elif args.command == "recall":
            exit_code = asyncio.run(do_recall(args, config, logger))
        else:
            parser.print_help()
            exit_code = 1
    except KeyboardInterrupt:
        logger.debug("Interrupted")
        exit_code = 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
