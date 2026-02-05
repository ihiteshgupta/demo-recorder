"""Utility helpers: temp directories, logging, timing."""

import logging
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

console = Console()


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure rich logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )
    return logging.getLogger("demo_recorder")


@contextmanager
def temp_dir(prefix: str = "demo_recorder_"):
    """Create a temporary directory that auto-cleans on exit."""
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@contextmanager
def timer(label: str, logger: logging.Logger | None = None):
    """Context manager that logs elapsed time."""
    start = time.monotonic()
    yield
    elapsed = time.monotonic() - start
    msg = f"{label}: {elapsed:.1f}s"
    if logger:
        logger.info(msg)
    else:
        console.print(f"  [dim]{msg}[/dim]")


def ensure_output_dir(path: Path) -> Path:
    """Ensure output directory exists."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_file_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
