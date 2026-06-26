"""Rich console helpers for the Backfield CLI."""

from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

CONSOLE = Console()

BANNER = r"""
 ____             _    __ _ _ _     _
| __ )  __ _  ___| | __/ _(_) | __| |
|  _ \ / _` |/ __| |/ / |_| | |/ _` |
| |_) | (_| | (__|   <|  _| | | (_| |
|____/ \__,_|\___|_|\_\_| |_|_|\__,_|
""".strip("\n")

AGATE_UI_URL = "http://localhost:5173"
STYLEBOOK_UI_URL = "http://localhost:5175"
INTEGRATIONS_URL = f"{AGATE_UI_URL}/settings/integrations"

INIT_STEP_COUNT = 5


def is_interactive() -> bool:
    """True when stdout is a TTY (local terminal session)."""
    return sys.stdout.isatty()


def print_banner() -> None:
    CONSOLE.print(Panel(Text(BANNER, style="bold cyan"), border_style="cyan", padding=(0, 2)))


def print_intro() -> None:
    CONSOLE.print()
    CONSOLE.print("[bold]Welcome to Backfield local setup.[/bold]")
    CONSOLE.print(
        "This will prepare your machine for local development:\n"
        "  • Generate or reuse repo-root [cyan].env[/cyan] secrets\n"
        "  • Start the Docker Compose stack\n"
        "  • Run database migrations\n"
        "  • Wait for API readiness\n"
        "  • Seed your organization, stylebook, and admin user"
    )
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
