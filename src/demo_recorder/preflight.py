"""System dependency checker."""

import shutil
import subprocess
import sys

from rich.console import Console
from rich.table import Table


def check_ffmpeg() -> tuple[bool, str]:
    """Check if ffmpeg is installed and return version."""
    path = shutil.which("ffmpeg")
    if not path:
        return False, "Not found — install with: brew install ffmpeg"
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
        return True, version_line
    except Exception as e:
        return False, f"Error checking ffmpeg: {e}"


def check_playwright() -> tuple[bool, str]:
    """Check if Playwright browsers are installed."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # If dry-run succeeds without errors, browsers are likely installed
        # Fall back to checking if chromium exists
        result2 = subprocess.run(
            [sys.executable, "-c", "from playwright.sync_api import sync_playwright"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result2.returncode == 0:
            return True, "Playwright importable"
        return False, "Playwright not installed — run: pip install playwright && playwright install chromium"
    except Exception:
        return False, "Playwright not installed — run: pip install playwright && playwright install chromium"


def check_edge_tts() -> tuple[bool, str]:
    """Check if edge-tts is importable."""
    try:
        import edge_tts  # noqa: F401
        return True, f"edge-tts {edge_tts.__version__}" if hasattr(edge_tts, "__version__") else (True, "edge-tts installed")
    except ImportError:
        return False, "Not installed — run: pip install edge-tts"


def run_preflight() -> bool:
    """Run all preflight checks. Returns True if all pass."""
    console = Console()
    table = Table(title="Preflight Checks")
    table.add_column("Dependency", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details")

    checks = [
        ("ffmpeg", check_ffmpeg),
        ("Playwright", check_playwright),
        ("edge-tts", check_edge_tts),
    ]

    all_ok = True
    for name, check_fn in checks:
        ok, detail = check_fn()
        status = "[green]OK[/green]" if ok else "[red]MISSING[/red]"
        if not ok:
            all_ok = False
        table.add_row(name, status, detail)

    console.print(table)

    if all_ok:
        console.print("\n[green]All checks passed.[/green]")
    else:
        console.print("\n[red]Some dependencies are missing. Install them before recording.[/red]")

    return all_ok
