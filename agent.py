#!/usr/bin/env python3
"""Agent CLI entry point."""

import argparse
import logging
import sys


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.WARNING
    fmt = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"
    datefmt = "%H:%M:%S"
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, stream=sys.stderr)
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(description="波波蛋 - Interactive tool-assisted agent")
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)"
    )
    parser.add_argument(
        "--session-id",
        help="Resume from a saved session"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG level)"
    )
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    from cli.repl import REPL
    repl = REPL(config_path=args.config, resume_session_id=args.session_id)
    repl.run()


if __name__ == "__main__":
    main()
