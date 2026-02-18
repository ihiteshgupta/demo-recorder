"""Click CLI: record, voices, preflight, init commands."""

import asyncio
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .utils import setup_logging

console = Console()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """Demo Recorder: Create narrated demo videos from JSON scripts."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)


@main.command()
@click.argument("script_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default="./output", help="Output directory.")
@click.option("--skip-gif", is_flag=True, help="Skip GIF generation.")
@click.pass_context
def record(ctx: click.Context, script_path: str, output: str, skip_gif: bool) -> None:
    """Record a demo from a JSON script file."""
    from .recorder import run_pipeline
    from .script_loader import load_script

    verbose = ctx.obj["verbose"]

    console.print(f"[bold]Loading script:[/bold] {script_path}")

    try:
        script = load_script(script_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.print(f"  Title: {script.metadata.title}")
    console.print(f"  Steps: {len(script.steps)}")
    console.print(f"  Voice: {script.metadata.voice}")
    console.print(f"  Viewport: {script.metadata.viewport.width}x{script.metadata.viewport.height}")

    output_dir = Path(output)
    try:
        outputs = asyncio.run(
            run_pipeline(
                script=script,
                output_dir=output_dir,
                verbose=verbose,
                skip_gif=skip_gif,
            )
        )
    except Exception as e:
        console.print(f"\n[red]Recording failed:[/red] {e}")
        if verbose:
            console.print_exception()
        sys.exit(1)


@main.command()
@click.option("--language", "-l", default="en", help="Language prefix filter (e.g., en, fr, de).")
def voices(language: str) -> None:
    """List available Edge TTS voices."""
    from .narration import list_voices_sync

    console.print(f"[bold]Available voices for '{language}':[/bold]\n")

    voice_list = list_voices_sync(language)

    if not voice_list:
        console.print(f"[yellow]No voices found for language prefix '{language}'[/yellow]")
        return

    table = Table()
    table.add_column("Voice Name", style="cyan")
    table.add_column("Gender", style="magenta")
    table.add_column("Locale", style="green")

    for v in voice_list:
        table.add_row(v["name"], v["gender"], v["locale"])

    console.print(table)
    console.print(f"\n[dim]Total: {len(voice_list)} voices[/dim]")


@main.command()
def preflight() -> None:
    """Check system dependencies (ffmpeg, Playwright, edge-tts)."""
    from .preflight import run_preflight

    ok = run_preflight()
    sys.exit(0 if ok else 1)


@main.command("save-auth")
@click.argument("url", default="https://web.telegram.org/k/")
@click.option("--output", "-o", type=click.Path(), default="./auth_state.json", help="Where to save auth state.")
@click.option("--viewport", type=(int, int), default=(1920, 1080), help="Browser viewport width height.")
def save_auth(url: str, output: str, viewport: tuple[int, int]) -> None:
    """Open a browser to log in, then save auth state for demo recording.

    Usage: demo-recorder save-auth https://web.telegram.org/k/ -o telegram_auth.json
    """
    async def _run() -> None:
        from playwright.async_api import async_playwright

        console.print(f"[bold]Opening browser:[/bold] {url}")
        console.print("[dim]Log in, then close the browser window to save auth state.[/dim]\n")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
            )
            page = await context.new_page()
            await page.goto(url, wait_until="load")

            # Wait for the user to close the browser
            try:
                await page.wait_for_event("close", timeout=600_000)  # 10 min
            except Exception:
                pass

            # Save storage state
            state_path = Path(output).resolve()
            await context.storage_state(path=str(state_path))
            await browser.close()

        console.print(f"\n[green]Auth state saved:[/green] {state_path}")
        console.print(f'[dim]Use in script metadata: "storage_state": "{state_path}"[/dim]')

    asyncio.run(_run())


@main.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.argument("source_video", type=click.Path(exists=True), required=False, default=None)
@click.option("--output", "-o", type=click.Path(), default="./output", help="Output directory.")
@click.option("--base-dir", type=click.Path(exists=True), default=None, help="Base dir for resolving clip paths.")
def stitch(config_file: str, source_video: str | None, output: str, base_dir: str | None) -> None:
    """Stitch clips into a final branded demo video.

    Clips mode:   demo-recorder stitch stitch_config.json -o output/
    Legacy mode:  demo-recorder stitch stitch_config.json output/demo.mp4 -o output/
    """
    config_path = Path(config_file)
    with open(config_path) as f:
        config = json.load(f)

    try:
        if "clips" in config:
            from .stitch import stitch_clips

            console.print("[bold]Stitching clips in sequence[/bold]\n")
            result = stitch_clips(
                config_path=config_path,
                output_dir=Path(output),
                base_dir=Path(base_dir) if base_dir else None,
            )
        else:
            from .stitch import stitch_video

            if not source_video:
                console.print("[red]Error:[/red] Legacy mode requires a source video argument")
                sys.exit(1)
            console.print("[bold]Stitching branded transitions[/bold]\n")
            result = stitch_video(
                source_path=Path(source_video),
                config_path=config_path,
                output_dir=Path(output),
                base_dir=Path(base_dir) if base_dir else None,
            )
        console.print(f"\n[green]Output:[/green] {result}")
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except RuntimeError as e:
        console.print(f"[red]ffmpeg error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("output_path", type=click.Path(), default="demo_script.json")
def init(output_path: str) -> None:
    """Initialize a sample demo script template."""
    template = {
        "metadata": {
            "title": "My Demo",
            "description": "A demo walkthrough",
            "base_url": "http://localhost:8080",
            "viewport": {"width": 1280, "height": 720},
            "voice": "en-US-AriaNeural",
            "rate": "+0%",
            "output_name": "demo",
        },
        "steps": [
            {
                "id": "step_01",
                "action": "navigate",
                "url": "/",
                "narration": "Welcome to the demo. Let's start from the home page.",
                "wait_after": 2000,
            },
            {
                "id": "step_02",
                "action": "click",
                "selector": "button:has-text('Get Started')",
                "narration": "Click Get Started to begin.",
                "wait_after": 1000,
            },
            {
                "id": "step_03",
                "action": "type",
                "selector": "#name",
                "value": "Demo User",
                "narration": "Enter your name in the field.",
                "type_delay": 50,
                "wait_after": 500,
            },
        ],
    }

    path = Path(output_path)
    if path.exists():
        console.print(f"[yellow]File already exists:[/yellow] {path}")
        if not click.confirm("Overwrite?"):
            return

    path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    console.print(f"[green]Created template:[/green] {path}")
    console.print("[dim]Edit the script and run: demo-recorder record " + str(path) + "[/dim]")


if __name__ == "__main__":
    main()
