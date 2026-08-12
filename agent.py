#!/usr/bin/env python3
"""Agent CLI entry point."""

import argparse
import json
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
    subparsers = parser.add_subparsers(dest="command")
    library_parser = subparsers.add_parser("library", help="Manage portable Bobodan libraries")
    library_commands = library_parser.add_subparsers(dest="library_command", required=True)
    library_init = library_commands.add_parser("init", help="Initialize or register a library folder")
    library_init.add_argument("path")
    library_init.add_argument("--name")
    library_sync = library_commands.add_parser("sync", help="Index changed original materials")
    library_sync.add_argument("path", nargs="?")
    library_commands.add_parser("list", help="List registered libraries")
    web_parser = subparsers.add_parser("web", help="Start the single-process local Web server (P5G.1)")
    from cli.web_serve import build_parser
    build_parser(web_parser)
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    if args.command == "web":
        from cli.web_serve import run_web
        raise SystemExit(run_web(
            host=args.host,
            port=args.port,
            no_browser=args.no_browser,
            dev=args.dev,
        ))

    if args.command == "library":
        from providers.factory import ProviderFactory
        from service.library_service import LibraryService

        service = LibraryService()
        try:
            if args.library_command == "init":
                result = service.initialize(args.path, name=args.name)
            elif args.library_command == "sync":
                if args.path:
                    record = service.register(args.path, activate=True)
                    library_id = record["library_id"]
                else:
                    resolved = service.resolve()
                    if resolved is None:
                        parser.error("No active library. Pass a folder path first.")
                    library_id = resolved["library_id"]
                result = service.sync(library_id, ProviderFactory.load_config(args.config))
            else:
                result = service.list_libraries()
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    from cli.repl import REPL
    repl = REPL(config_path=args.config, resume_session_id=args.session_id)
    repl.run()


if __name__ == "__main__":
    main()
