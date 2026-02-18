"""Playwright browser automation and video recording."""

import time
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Page, async_playwright

from .models import ActionType, DemoScript, Step


@dataclass
class StepTiming:
    """Timing info for a recorded step."""
    step_id: str
    action_start_ms: int  # when the action began in the video timeline
    pause_start_ms: int  # when the narration pause began
    pause_end_ms: int  # when the pause ended


async def execute_action(page: Page, step: Step, base_url: str) -> None:
    """Execute a single browser action."""
    action = step.action

    if action == ActionType.NAVIGATE:
        url = step.url
        if url and not url.startswith(("http://", "https://", "file://")):
            url = base_url.rstrip("/") + "/" + url.lstrip("/")
        await page.goto(url, wait_until="load")

    elif action == ActionType.CLICK:
        await page.click(step.selector)
        # Wait for any navigation triggered by the click to complete
        try:
            await page.wait_for_load_state("load", timeout=10000)
        except Exception:
            pass

    elif action == ActionType.TYPE:
        await page.wait_for_selector(step.selector, state="visible", timeout=15000)
        await page.fill(step.selector, "")  # Clear first
        await page.type(step.selector, step.value, delay=step.type_delay)

    elif action == ActionType.PRESS:
        await page.keyboard.press(step.key)

    elif action == ActionType.SCROLL:
        if step.selector:
            element = page.locator(step.selector)
            await element.scroll_into_view_if_needed()
        else:
            direction = step.direction or "down"
            amount = step.amount or 300
            delta = amount if direction == "down" else -amount
            await page.mouse.wheel(0, delta)

    elif action == ActionType.HOVER:
        await page.hover(step.selector)

    elif action == ActionType.SELECT:
        await page.select_option(step.selector, step.value)

    elif action == ActionType.WAIT:
        await page.wait_for_timeout(step.duration)

    elif action == ActionType.EVALUATE:
        await page.evaluate(step.expression)

    elif action == ActionType.SCREENSHOT:
        pass  # Video is already recording; screenshot is a marker


async def record_demo(
    script: DemoScript,
    narration_durations: list[int],
    video_dir: Path,
) -> tuple[Path, list[StepTiming]]:
    """Record the browser demo as video with timed pauses for narration.

    Args:
        script: The validated demo script.
        narration_durations: Duration in ms for each step's narration audio.
        video_dir: Directory to save the recorded video.

    Returns:
        Tuple of (video_path, list of StepTiming).
    """
    viewport = {
        "width": script.metadata.viewport.width,
        "height": script.metadata.viewport.height,
    }

    timings: list[StepTiming] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context_opts = {
            "viewport": viewport,
            "record_video_dir": str(video_dir),
            "record_video_size": viewport,
        }
        if script.metadata.storage_state:
            context_opts["storage_state"] = script.metadata.storage_state
        context = await browser.new_context(**context_opts)
        page = await context.new_page()

        # Wall-clock reference for accurate video timeline tracking
        recording_start = time.monotonic()

        def elapsed_ms() -> int:
            return int((time.monotonic() - recording_start) * 1000)

        # Small initial settle time
        await page.wait_for_timeout(500)

        for i, step in enumerate(script.steps):
            narration_ms = narration_durations[i] if i < len(narration_durations) else 0

            # Ensure any pending navigation from previous step has completed
            try:
                await page.wait_for_load_state("load", timeout=5000)
            except Exception:
                pass

            # Record action start time (wall-clock)
            action_start = elapsed_ms()

            # Execute the browser action
            await execute_action(page, step, script.metadata.base_url)

            # Small settle time after action (300ms)
            await page.wait_for_timeout(300)

            # Pause start = where narration audio will be placed (wall-clock)
            pause_start = elapsed_ms()

            # Insert pause matching narration duration
            if narration_ms > 0:
                await page.wait_for_timeout(narration_ms)

            # Additional wait_after pause
            if step.wait_after > 0:
                await page.wait_for_timeout(step.wait_after)

            # Pause end (wall-clock)
            pause_end = elapsed_ms()

            timings.append(StepTiming(
                step_id=step.id,
                action_start_ms=action_start,
                pause_start_ms=pause_start,
                pause_end_ms=pause_end,
            ))

        # Final settle
        await page.wait_for_timeout(1000)

        # Close context to finalize video
        await context.close()

        # Get the video path (Playwright saves it in video_dir)
        video_path = await page.video.path()
        await browser.close()

    return Path(video_path), timings
