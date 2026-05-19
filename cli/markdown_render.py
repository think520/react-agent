import re

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GRAY = "\033[90m"
CYAN = "\033[38;5;117m"
PINK = "\033[37m"
ORANGE = "\033[1;37m"
GREEN = "\033[32m"


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
UNORDERED_RE = re.compile(r"^(\s*)[-*+]\s+(.+)$")
ORDERED_RE = re.compile(r"^(\s*)\d+[.)]\s+(.+)$")
BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
RICH_AVAILABLE = True

_console = Console(theme=Theme({
    "info": "bright_cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "green",
    "agent": "white",
    "tool": "dim bright_black",
    "thinking": "dim italic",
    "muted": "bright_black",
    "accent": "bright_cyan",
}))


def strip_table_separator(line: str) -> bool:
    """Return true for Markdown table separator rows like |---|:---:|."""
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if not cells or any(not cell for cell in cells):
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def is_table_row(line: str) -> bool:
    return line.strip().startswith("|") and line.strip().endswith("|") and "|" in line.strip()[1:-1]


def render_inline(text: str) -> str:
    """Render a small, safe subset of Markdown inline markers."""
    text = re.sub(r"`([^`]+)`", rf"{CYAN}\1{RESET}", text)
    text = re.sub(r"\*\*([^*]+)\*\*", rf"{BOLD}\1{RESET}", text)
    text = re.sub(r"__([^_]+)__", rf"{BOLD}\1{RESET}", text)
    return text


def render_markdown_lines(text: str) -> list[str]:
    """Render common Markdown syntax for terminal output.

    This intentionally handles a small subset: headings, lists, blockquotes,
    fenced code, simple tables, bold, and inline code.
    """
    rendered: list[str] = []
    in_code = False
    code_lang = ""

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if not in_code:
                code_lang = stripped[3:].strip()
                label = f" code: {code_lang} " if code_lang else " code "
                rendered.append(f"  {DIM}{label}{RESET}")
                in_code = True
            else:
                in_code = False
                code_lang = ""
            continue

        if in_code:
            rendered.append(f"  {GRAY}|{RESET} {CYAN}{line}{RESET}")
            continue

        if not stripped:
            rendered.append("")
            continue

        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            title = render_inline(heading.group(2))
            color = ORANGE if level <= 2 else PINK
            rendered.append(f"  {color}{title}{RESET}")
            continue

        if strip_table_separator(line):
            continue

        if is_table_row(line):
            cells = [render_inline(cell.strip()) for cell in stripped.strip("|").split("|")]
            rendered.append(f"  {DIM}|{RESET} " + f" {DIM}|{RESET} ".join(cells))
            continue

        unordered = UNORDERED_RE.match(line)
        if unordered:
            indent = " " * (len(unordered.group(1)) + 2)
            rendered.append(f"{indent}{PINK}-{RESET} {render_inline(unordered.group(2))}")
            continue

        ordered = ORDERED_RE.match(line)
        if ordered:
            indent = " " * (len(ordered.group(1)) + 2)
            rendered.append(f"{indent}{GREEN}>{RESET} {render_inline(ordered.group(2))}")
            continue

        blockquote = BLOCKQUOTE_RE.match(line)
        if blockquote:
            rendered.append(f"  {DIM}| {render_inline(blockquote.group(1))}{RESET}")
            continue

        rendered.append(f"  {render_inline(line)}")

    return rendered


def make_console():
    return _console


def console() -> Console:
    return _console


def print_markdown(text: str) -> None:
    """Render Markdown with a calm, lightweight terminal renderer."""
    for line in render_markdown_lines(text):
        make_console().print(Text.from_ansi(line), markup=False)


def print_error(message: str) -> None:
    make_console().print(f"[error][Error][/error] {message}")


def print_success(message: str) -> None:
    make_console().print(f"[success][OK][/success] {message}")


def print_notice(message: str) -> None:
    make_console().print(f"[warning]{message}[/warning]")


def print_kv_panel(title: str, rows: list[tuple[str, object]]) -> None:
    console = make_console()
    table = Table.grid(padding=(0, 2))
    table.add_column(style="accent", no_wrap=True)
    table.add_column()
    for key, value in rows:
        table.add_row(str(key), str(value))
    console.print(Panel(table, title=title, border_style="bright_black"))


def print_startup_panel(rows: list[tuple[str, object]]) -> None:
    console = make_console()
    table = Table.grid(padding=(0, 2))
    table.add_column(style="accent", no_wrap=True)
    table.add_column(style="white", ratio=1, overflow="fold")
    for key, value in rows:
        table.add_row(str(key), str(value))

    panel = Panel(
        table,
        title="[bold white]bobodan[/bold white]",
        subtitle="[muted]Type / for suggestions, /help for full guide[/muted]",
        border_style="bright_black",
        padding=(1, 3),
    )
    console.print()
    console.print(panel)
    console.print()




def print_search_table(results: list[dict]) -> None:
    console = make_console()
    table = Table(title="RAG Search Results", border_style="bright_black", show_lines=True)
    table.add_column("#", style="muted", justify="right", no_wrap=True)
    table.add_column("Source", style="accent", no_wrap=True)
    table.add_column("Score", style="green", no_wrap=True)
    table.add_column("Preview", overflow="fold")
    for index, item in enumerate(results, start=1):
        text = " ".join(item.get("text", "").split())
        table.add_row(
            str(index),
            item.get("source", ""),
            str(item.get("score", 0)),
            text,
        )
    console.print(table)
