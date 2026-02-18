#!/usr/bin/env python3
"""
One-shot billing dispute demo recorder.
Handles service checks, data setup, recording order, frame verification, stitching, and playback.

Usage:
    source venv/bin/activate
    python record_demo.py                         # Record all chunks + stitch
    python record_demo.py --chunks 13             # Re-record only chunks 1 and 3 + stitch
    python record_demo.py --chunks 1 --verify     # Record chunk 1, verify key frames before stitching
    python record_demo.py --verify-only           # Just show key frames from existing recordings
    python record_demo.py --skip-stitch           # Record without stitching
    python record_demo.py --no-open               # Don't open video after stitching

Key frame verification timestamps (tweaked to match narrations):
    Chunk 1 (Telegram): 100s — should show bot resolution message with root cause
    Chunk 3 (CRM):       30s — should show ticket detail with status "resolved"
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests
from rich.console import Console
from rich.panel import Panel

console = Console()

BACKEND = "http://localhost:8010"
FRONTEND = "http://localhost:5173"
DEMO_DIR = Path(__file__).parent
OUTPUT_DIR = DEMO_DIR / "output"
SCRIPTS_DIR = DEMO_DIR / "sample_scripts"

CHUNKS = [
    {"id": "0", "script": "chunk_0_empty_crm.json",   "label": "Empty CRM Baseline",  "needs": []},
    {"id": "1", "script": "chunk_1_telegram.json",     "label": "Telegram Chat",        "needs": ["backend"]},
    {"id": "2", "script": "chunk_2_platform.json",     "label": "Platform Workflow",    "needs": ["frontend"]},
    {"id": "3", "script": "chunk_3_crm.json",          "label": "CRM Portal",           "needs": ["frontend"]},
]

# Key frames to verify after recording (chunk_id -> [(timestamp_s, description)])
VERIFY_FRAMES = {
    "1": [
        (28,  "Bot first reply — should ask for customer ID and billing month"),
        (100, "Bot resolution — MUST name the Streaming+ HD add-on as root cause"),
    ],
    "3": [
        (30,  "Ticket list — should show resolved ticket"),
        (55,  "Ticket detail — category, priority, customer, resolution note"),
    ],
}

CUSTOMER_ID = "C006064"
CUSTOMER_CHARACTERISTICS = [
    {"name": "churnScore",     "value": "0.12",                                                                    "valueType": "float"},
    {"name": "sentiment",      "value": "positive",                                                                "valueType": "string"},
    {"name": "planName",       "value": "Unlimited Plus 599",                                                      "valueType": "string"},
    {"name": "tenure",         "value": "36",                                                                      "valueType": "integer"},
    {"name": "monthlySpend",   "value": "599",                                                                     "valueType": "float"},
    {"name": "activeAddOns",   "value": "Streaming+ HD ($30/mo, added 2025-12-18)",                                "valueType": "string"},
    {"name": "lastPlanChange", "value": "Added Streaming+ HD package on 2025-12-18 — increases monthly bill by $30", "valueType": "string"},
]


# ── Service checks ────────────────────────────────────────────────────────────

def check_service(url: str, key: str = None, expected: str = None) -> bool:
    try:
        r = requests.get(url, timeout=5)
        if key and expected:
            return r.json().get(key) == expected
        return r.status_code < 400
    except Exception:
        return False


def wait_for_services(required: set[str]) -> None:
    console.print("\n[bold]Checking services...[/bold]")
    checks = {
        "backend":  (f"{BACKEND}/health", "mongodb", "connected"),
        "frontend": (FRONTEND,            None,       None),
    }
    failed = []
    for name, (url, key, val) in checks.items():
        if name not in required:
            continue
        ok = check_service(url, key, val)
        status = "[green]OK[/green]" if ok else "[red]DOWN[/red]"
        console.print(f"  {name:<12} {status}  {url}")
        if not ok:
            failed.append(name)

    if failed:
        console.print(f"\n[red]Services not ready:[/red] {', '.join(failed)}")
        console.print("Start them and re-run this script.")
        sys.exit(1)
    console.print()


# ── Data setup ────────────────────────────────────────────────────────────────

def _read_env(key: str, default: str = None) -> str:
    env_file = DEMO_DIR.parent / "ai-poc-backend" / "ai-poc-backend" / ".env"
    for line in env_file.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return default


def ensure_customer_data() -> None:
    """Verify C006064 has the add-on characteristics; update MongoDB if missing."""
    try:
        r = requests.get(f"{BACKEND}/crm-portal/customers/{CUSTOMER_ID}", timeout=5)
    except Exception:
        console.print("  [yellow]Skipping customer data check (backend unavailable)[/yellow]")
        return

    if r.status_code != 200:
        console.print(f"  [red]Customer {CUSTOMER_ID} not found[/red]")
        sys.exit(1)

    chars = {c["name"]: c["value"] for c in r.json().get("characteristic", [])}
    if chars.get("activeAddOns") and chars.get("lastPlanChange"):
        console.print(f"  [dim]Customer data OK — add-on fields present[/dim]")
        return

    console.print(f"  [yellow]Updating customer characteristics...[/yellow]")
    try:
        from pymongo import MongoClient
        client = MongoClient(_read_env("MONGODB_URL"), serverSelectionTimeoutMS=5000)
        db = client[_read_env("MONGODB_DATABASE", "ai_poc_backend")]
        db.crm_customers.update_one(
            {"id": CUSTOMER_ID},
            {"$set": {"characteristic": CUSTOMER_CHARACTERISTICS}},
        )
        client.close()
        console.print(f"  [green]Customer data updated[/green]")
    except Exception as e:
        console.print(f"  [red]Failed to update customer data:[/red] {e}")
        sys.exit(1)


def reset_conversations() -> None:
    r = requests.post(f"{BACKEND}/channel-router/reset", timeout=10)
    data = r.json()
    console.print(f"  [dim]Reset: {data.get('conversations_closed', 0)} conversations, "
                  f"{data.get('tickets_deleted', 0)} tickets[/dim]")


def ensure_ticket_exists() -> str:
    """Prefer the real ticket from chunk 1 (has conversation_id). Fallback: create one."""
    r = requests.get(f"{BACKEND}/trouble-tickets?limit=5", timeout=5)
    tickets = r.json().get("tickets", [])

    if tickets:
        tid = tickets[0]["id"]
        status = tickets[0].get("status")
        console.print(f"  [dim]Using existing ticket: {tid} ({status})[/dim]")
        if status != "resolved":
            requests.patch(f"{BACKEND}/trouble-tickets/{tid}",
                           json={"status": "resolved",
                                 "statusChangeReason": "AI auto-resolved - Streaming+ HD add-on explained"},
                           timeout=5)
        return tid

    console.print("  [yellow]No tickets found — creating representative ticket...[/yellow]")
    payload = {
        "name": "Billing Dispute - Priya Sharma",
        "description": "Customer reported $30 overcharge on January 2026 bill for Unlimited Plus 599 plan",
        "severity": "minor",
        "ticketType": "billing",
        "channel": {"name": "telegram"},
        "relatedParty": [{"id": CUSTOMER_ID, "name": "Priya Sharma", "role": "customer"}],
        "note": [{"text": (
            "Root cause: Streaming+ HD add-on ($30/mo) added on 2025-12-18 increased "
            "monthly bill from $599 to $629. Ticket resolved by AI."
        ), "author": "AI Support Agent"}],
    }
    r = requests.post(f"{BACKEND}/trouble-tickets", json=payload, timeout=10)
    tid = r.json()["id"]
    requests.patch(f"{BACKEND}/trouble-tickets/{tid}",
                   json={"status": "resolved", "statusChangeReason": "AI auto-resolved"},
                   timeout=5)
    console.print(f"  [dim]Created ticket: {tid}[/dim]")
    return tid


# ── Frame verification ────────────────────────────────────────────────────────

def extract_and_show_frame(mp4: Path, ts: int, label: str) -> None:
    """Extract a frame from the video and open it for visual inspection."""
    out = OUTPUT_DIR / f"_verify_{mp4.stem}_{ts}s.jpg"
    result = subprocess.run(
        ["ffmpeg", "-y", "-ss", str(ts), "-i", str(mp4),
         "-frames:v", "1", "-q:v", "2", str(out)],
        capture_output=True,
    )
    if result.returncode != 0:
        console.print(f"  [red]Frame extraction failed at {ts}s[/red]")
        return
    console.print(f"  [cyan]Frame @ {ts}s:[/cyan] {label}")
    subprocess.run(["open", str(out)])


def verify_chunk(chunk_id: str, auto: bool = False) -> bool:
    """Extract and show key frames for a chunk. Return True if user approves."""
    frames = VERIFY_FRAMES.get(chunk_id)
    if not frames:
        return True

    chunk = next(c for c in CHUNKS if c["id"] == chunk_id)
    mp4 = OUTPUT_DIR / f"chunk_{chunk_id}_{chunk['script'].replace('chunk_' + chunk_id + '_', '').replace('.json', '')}.mp4"

    # Find actual mp4 by output_name in script
    script_path = SCRIPTS_DIR / chunk["script"]
    try:
        script = json.loads(script_path.read_text())
        output_name = script.get("metadata", {}).get("output_name", "")
        if output_name:
            mp4 = OUTPUT_DIR / f"{output_name}.mp4"
    except Exception:
        pass

    if not mp4.exists():
        console.print(f"  [yellow]No video found for chunk {chunk_id}, skipping verify[/yellow]")
        return True

    console.print(f"\n[bold]Verifying chunk {chunk_id}: {chunk['label']}[/bold]")
    for ts, label in frames:
        extract_and_show_frame(mp4, ts, label)

    if auto:
        return True

    answer = console.input("\n  [bold]Approve this chunk? (y/n/r to re-record):[/bold] ").strip().lower()
    return answer != "n"


# ── Recording ─────────────────────────────────────────────────────────────────

def record_chunk(chunk: dict) -> bool:
    script_path = SCRIPTS_DIR / chunk["script"]
    console.print(f"\n[bold]Recording chunk {chunk['id']}: {chunk['label']}[/bold]")
    result = subprocess.run(
        ["demo-recorder", "record", str(script_path), "--output", str(OUTPUT_DIR), "--skip-gif"],
        capture_output=False,
        cwd=DEMO_DIR,
    )
    if result.returncode != 0:
        console.print(f"[red]Chunk {chunk['id']} recording failed[/red]")
        return False
    return True


def record_with_verify(chunk: dict, verify: bool, interactive: bool) -> bool:
    """Record a chunk, optionally verify key frames, re-record if rejected."""
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            console.print(f"\n[yellow]Re-recording (attempt {attempt}/{max_attempts})...[/yellow]")

        ok = record_chunk(chunk)
        if not ok:
            return False

        if verify:
            approved = verify_chunk(chunk["id"], auto=not interactive)
            if not approved:
                if attempt < max_attempts:
                    continue
                console.print("[red]Max re-record attempts reached.[/red]")
                return False

        return True
    return False


# ── Stitching ─────────────────────────────────────────────────────────────────

def stitch() -> Path:
    console.print("\n[bold]Stitching final video...[/bold]")
    result = subprocess.run(
        ["demo-recorder", "stitch", "stitch_config.json", "--output", str(OUTPUT_DIR)],
        capture_output=False,
        cwd=DEMO_DIR,
    )
    if result.returncode != 0:
        console.print("[red]Stitch failed[/red]")
        sys.exit(1)

    with open(DEMO_DIR / "stitch_config.json") as f:
        config = json.load(f)
    return OUTPUT_DIR / f"{config['output_name']}.mp4"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record billing dispute demo end-to-end.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[1].strip() if "Usage:" in __doc__ else "",
    )
    parser.add_argument("--chunks", default="0123",
                        help="Chunks to record: '0123' (all), '1' (Telegram only), '13' (Telegram+CRM). Default: 0123")
    parser.add_argument("--verify", action="store_true",
                        help="Show key frames after each chunk; prompt to re-record if bad")
    parser.add_argument("--verify-only", action="store_true",
                        help="Skip recording — just show key frames from existing files")
    parser.add_argument("--skip-stitch", action="store_true", help="Skip final stitch")
    parser.add_argument("--no-open", action="store_true", help="Don't open video after stitching")
    args = parser.parse_args()

    chunks_to_record = [c for c in CHUNKS if c["id"] in args.chunks]

    console.print(Panel(
        f"[bold]Billing Dispute Demo Recorder[/bold]\n"
        f"Chunks: {', '.join(c['label'] for c in chunks_to_record)}\n"
        f"Verify: {'yes (interactive)' if args.verify else 'no'}\n"
        f"Output: {OUTPUT_DIR}",
        style="blue",
    ))

    # ── verify-only mode: just show frames
    if args.verify_only:
        for chunk in CHUNKS:  # verify all
            verify_chunk(chunk["id"], auto=False)
        return

    # ── service checks
    services_needed = {"backend"}
    services_needed.update(
        svc for c in chunks_to_record for svc in c.get("needs", [])
    )
    wait_for_services(services_needed)

    # ── data setup
    console.print("[bold]Setting up data...[/bold]")
    ensure_customer_data()

    # ── record chunks in dependency order
    chunk1_was_recorded = False
    for chunk in chunks_to_record:
        if chunk["id"] == "1":
            console.print("\n[bold]Resetting conversations...[/bold]")
            reset_conversations()
        elif chunk["id"] == "3":
            console.print("\n[bold]Ensuring resolved ticket exists...[/bold]")
            # If chunk 1 was just recorded, ticket already exists from bot interaction
            if not chunk1_was_recorded:
                ensure_ticket_exists()

        ok = record_with_verify(chunk, verify=args.verify, interactive=True)
        if not ok:
            console.print(f"\n[red]Aborting — chunk {chunk['id']} failed.[/red]")
            sys.exit(1)

        if chunk["id"] == "1":
            chunk1_was_recorded = True

    # ── stitch
    if not args.skip_stitch:
        output_path = stitch()
        console.print(f"\n[green bold]Done![/green bold] {output_path}")
        if not args.no_open:
            subprocess.run(["open", str(output_path)])
    else:
        console.print("\n[dim]Stitch skipped.[/dim]")


if __name__ == "__main__":
    main()
