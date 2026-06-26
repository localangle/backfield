"""Rich console helpers for the Backfield CLI."""

from __future__ import annotations

import sys

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

CONSOLE = Console()

BANNER = """
░████████                         ░██           ░████ ░██           ░██        ░██
░██    ░██                        ░██          ░██                  ░██        ░██
░██    ░██   ░██████    ░███████  ░██    ░██░████████ ░██ ░███████  ░██  ░████████
░████████         ░██  ░██    ░██ ░██   ░██    ░██    ░██░██    ░██ ░██ ░██    ░██
░██     ░██  ░███████  ░██        ░███████     ░██    ░██░█████████ ░██ ░██    ░██
░██     ░██ ░██   ░██  ░██    ░██ ░██   ░██    ░██    ░██░██        ░██ ░██   ░███
░█████████   ░█████░██  ░███████  ░██    ░██   ░██    ░██ ░███████  ░██  ░█████░██
""".strip("\n")

AGATE_UI_URL = "http://localhost:5173"
STYLEBOOK_UI_URL = "http://localhost:5175"
INTEGRATIONS_URL = f"{AGATE_UI_URL}/settings/integrations"

INIT_STEP_COUNT = 5


def is_interactive() -> bool:
    """True when stdout is a TTY (local terminal session)."""
    return sys.stdout.isatty()


def print_banner() -> None:
    logo = Text(BANNER, style="bold cyan", no_wrap=True)
    subtitle = Text("Local development setup", style="cyan")
    CONSOLE.print(
        Panel(
            Group(
                Align.center(logo),
                Text("\n\n"),
                Align.center(subtitle),
                Rule(style="bright_cyan"),
            ),
            border_style="cyan",
            padding=(1, 2),
            expand=True,
        )
    )


def print_intro() -> None:
    CONSOLE.print()
    CONSOLE.print("[bold]Welcome to the Backfield local setup utility.[/bold]")
    CONSOLE.print()
    CONSOLE.print(
        "Fill out the following information to bootstrap the Backfield platform on your "
        "machine. Running Backfield locally requires Docker and Docker Compose "
        "([link=https://docs.docker.com/compose/]https://docs.docker.com/compose/[/link])."
    )
    CONSOLE.print()
    CONSOLE.print("Supply the following information to get started.")
    CONSOLE.print()


def print_step(step: int, total: int, label: str) -> None:
    CONSOLE.print(f"[bold cyan]Step {step}/{total}:[/bold cyan] {label}")


def print_next_steps(admin_email: str) -> None:
    CONSOLE.print()
    CONSOLE.print("[bold green]Backfield is ready.[/bold green]")
    CONSOLE.print()
    CONSOLE.print("[bold]Your apps[/bold]")
    CONSOLE.print(f"  Agate UI:      [link={AGATE_UI_URL}]{AGATE_UI_URL}[/link]")
    CONSOLE.print(f"  Stylebook UI:  [link={STYLEBOOK_UI_URL}]{STYLEBOOK_UI_URL}[/link]")
    CONSOLE.print(f"  Admin login:   [cyan]{admin_email}[/cyan]")
    CONSOLE.print()
    CONSOLE.print("[bold]Next steps[/bold]")
    CONSOLE.print(
        "  1. Open [bold]Settings → Integrations[/bold] in the Agate UI\n"
        f"     [link={INTEGRATIONS_URL}]{INTEGRATIONS_URL}[/link]"
    )
    CONSOLE.print(
        "  2. Add API keys for geocoding, search, and storage\n"
        "     (Geocode Earth, Geocodio, Brave Search, Amazon S3)"
    )
    CONSOLE.print("  3. Open Agate and build or run your first flow")
    CONSOLE.print()
