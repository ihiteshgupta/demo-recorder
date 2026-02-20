#!/usr/bin/env python3
"""
Three-path ticketing demo recorder.
Records 7 chunks covering 3 billing dispute resolution paths, then stitches into one video.

Usage:
    source venv/bin/activate
    python record_demo.py                         # Record all chunks + stitch
    python record_demo.py --chunks 0124           # Re-record specific chunks + stitch
    python record_demo.py --chunks 4 --verify     # Record chunk 4, verify key frames
    python record_demo.py --verify-only           # Just show key frames from existing recordings
    python record_demo.py --skip-stitch           # Record without stitching
    python record_demo.py --no-open               # Don't open video after stitching

Chunk map:
    0 — CRM Baseline (empty)
    1 — Path 1: Self-Service Resolution (Telegram, no ticket)
    2 — Path 2: Ticket + Auto-Close (Telegram, $25 under threshold)
    3 — Path 2: CRM Verification (show auto-closed ticket)
    4 — Path 3: Ticket + Human Escalation (Telegram, $85 over threshold)
    5 — Path 3: Agent Dashboard Review (human accepts AI recommendation)
    6 — CRM Final (all tickets, closing narration)
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
    {"id": "0", "script": "chunk_0_crm_baseline.json",        "label": "CRM Baseline",           "needs": ["frontend"]},
    {"id": "1", "script": "chunk_1_path1_selfservice.json",    "label": "Path 1: Self-Service",    "needs": ["backend"]},
    {"id": "2", "script": "chunk_2_path2_autoclose.json",      "label": "Path 2: Auto-Close",      "needs": ["backend"]},
    {"id": "3", "script": "chunk_3_path2_crm.json",            "label": "Path 2: CRM Check",       "needs": ["frontend"]},
    {"id": "4", "script": "chunk_4_path3_escalation.json",     "label": "Path 3: Escalation",      "needs": ["backend"]},
    {"id": "5", "script": "chunk_5_path3_agent.json",          "label": "Path 3: Agent Review",    "needs": ["frontend"]},
    {"id": "6", "script": "chunk_6_crm_final.json",            "label": "CRM Final",               "needs": ["frontend"]},
]

# Key frames to verify after recording (chunk_id -> [(timestamp_s, description)])
VERIFY_FRAMES = {
    "1": [
        (30,  "Bot first reply — should explain the $25 activation fee (eSIM swap)"),
        (55,  "Customer accepts explanation — session should close without ticket"),
    ],
    "2": [
        (30,  "Bot explains fee — same as Path 1"),
        (70,  "Bot creates ticket — should show ticket ID"),
        (95,  "Auto-resolution — should show credit applied, ticket closed"),
    ],
    "4": [
        (30,  "Bot explains $85 Premium Setup Fee"),
        (70,  "Bot creates ticket"),
        (90,  "Escalation — should show ticket routed to human agent"),
    ],
    "5": [
        (15,  "Agent dashboard — should show escalated ticket with AI recommendation"),
    ],
}


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

def reset_conversations() -> None:
    """Reset conversations and optionally tickets."""
    try:
        r = requests.post(f"{BACKEND}/channel-router/reset", timeout=10)
        data = r.json()
        console.print(f"  [dim]Reset: {data.get('conversations_closed', 0)} conversations, "
                      f"{data.get('tickets_deleted', 0)} tickets[/dim]")
    except Exception as e:
        console.print(f"  [yellow]Reset warning: {e}[/yellow]")


def delete_all_tickets() -> None:
    """Delete all trouble tickets for a clean slate."""
    try:
        r = requests.get(f"{BACKEND}/trouble-tickets?limit=100", timeout=5)
        tickets = r.json().get("tickets", [])
        for t in tickets:
            requests.delete(f"{BACKEND}/trouble-tickets/{t['id']}", timeout=5)
        if tickets:
            console.print(f"  [dim]Deleted {len(tickets)} tickets[/dim]")
    except Exception as e:
        console.print(f"  [yellow]Ticket cleanup warning: {e}[/yellow]")


# ── Pre-seeded demo customers ────────────────────────────────────────────────

DEMO_CUSTOMERS = [
    {
        "id": "C007001",
        "name": "Sarah Mitchell", "firstName": "Sarah", "lastName": "Mitchell",
        "accountType": "individual", "status": "active", "paymentStatus": "current",
        "accountBalance": 125.0, "creditLimit": 5000.0, "segment": "residential",
        "contactMedium": [
            {"mediumType": "email", "preferred": True, "characteristic": {"emailAddress": "sarah.mitchell@email.com"}},
            {"mediumType": "mobile", "preferred": False, "characteristic": {"phoneNumber": "+1-555-0101"}},
        ],
        "characteristic": [
            {"name": "planName", "value": "eSIM Flex Plan 49", "valueType": "string"},
            {"name": "tenure", "value": "24", "valueType": "integer"},
            {"name": "monthlySpend", "value": "49", "valueType": "float"},
            {"name": "lastOrder", "value": "eSIM Swap - Feb 2, 2026", "valueType": "string"},
            {"name": "lastInvoice", "value": "INV-2026-0214", "valueType": "string"},
            {"name": "activationFee", "value": "25.00", "valueType": "float"},
        ],
    },
    {
        "id": "C007002",
        "name": "Michael Rodriguez", "firstName": "Michael", "lastName": "Rodriguez",
        "accountType": "individual", "status": "active", "paymentStatus": "current",
        "accountBalance": 89.0, "creditLimit": 5000.0, "segment": "residential",
        "contactMedium": [
            {"mediumType": "email", "preferred": True, "characteristic": {"emailAddress": "michael.rodriguez@email.com"}},
            {"mediumType": "mobile", "preferred": False, "characteristic": {"phoneNumber": "+1-555-0202"}},
        ],
        "characteristic": [
            {"name": "planName", "value": "eSIM Flex Plan 49", "valueType": "string"},
            {"name": "tenure", "value": "12", "valueType": "integer"},
            {"name": "monthlySpend", "value": "49", "valueType": "float"},
            {"name": "lastOrder", "value": "eSIM Swap - Feb 2, 2026", "valueType": "string"},
            {"name": "lastInvoice", "value": "INV-2026-0214", "valueType": "string"},
            {"name": "activationFee", "value": "25.00", "valueType": "float"},
        ],
    },
    {
        "id": "C007003",
        "name": "John Dawson", "firstName": "John", "lastName": "Dawson",
        "accountType": "individual", "status": "active", "paymentStatus": "current",
        "accountBalance": 235.0, "creditLimit": 8000.0, "segment": "residential",
        "contactMedium": [
            {"mediumType": "email", "preferred": True, "characteristic": {"emailAddress": "john.dawson@email.com"}},
            {"mediumType": "mobile", "preferred": False, "characteristic": {"phoneNumber": "+1-555-0303"}},
        ],
        "characteristic": [
            {"name": "planName", "value": "Fiber Home Premium 129", "valueType": "string"},
            {"name": "tenure", "value": "6", "valueType": "integer"},
            {"name": "monthlySpend", "value": "129", "valueType": "float"},
            {"name": "lastOrder", "value": "Fiber Home Installation (Standard) - ORD-91205", "valueType": "string"},
            {"name": "lastInvoice", "value": "INV-2026-0214", "valueType": "string"},
            {"name": "premiumSetupFee", "value": "85.00", "valueType": "float"},
            {"name": "coverageZone", "value": "Zone C - Premium Routing", "valueType": "string"},
        ],
    },
]


def ensure_demo_customers() -> None:
    """Ensure all 3 demo customers exist in CRM."""
    for cust in DEMO_CUSTOMERS:
        try:
            r = requests.get(f"{BACKEND}/crm-portal/customers/{cust['id']}", timeout=5)
            if r.status_code == 200:
                console.print(f"  [dim]Customer exists: {cust['id']} ({cust['name']})[/dim]")
                continue
        except Exception:
            pass
        try:
            r = requests.post(f"{BACKEND}/crm-portal/customers", json=cust, timeout=10)
            if r.status_code in (200, 201):
                console.print(f"  [green]Created customer: {cust['id']} ({cust['name']})[/green]")
            else:
                console.print(f"  [yellow]Customer create returned {r.status_code}: {r.text[:100]}[/yellow]")
        except Exception as e:
            console.print(f"  [yellow]Customer create warning: {e}[/yellow]")


def ensure_ticket_exists_for_path2_crm() -> str:
    """Ensure a resolved ticket from Path 2 (auto-close) exists for the CRM check."""
    r = requests.get(f"{BACKEND}/trouble-tickets?limit=5", timeout=5)
    tickets = r.json().get("tickets", [])

    if tickets:
        console.print(f"  [dim]Found existing ticket: {tickets[0]['id']}[/dim]")
        return tickets[0]["id"]

    console.print("  [yellow]No tickets from bot — creating Path 2 auto-closed ticket...[/yellow]")
    payload = {
        "name": "Billing Dispute - Activation Fee",
        "description": "Customer disputes $25 Activation Fee on Feb bill (INV-2026-0214). Fee applied after eSIM swap on Feb 2. Customer states fee was not disclosed during swap process.",
        "severity": "minor",
        "ticketType": "billing",
        "channel": {"name": "telegram"},
        "relatedParty": [{"id": "C007002", "name": "Michael Rodriguez", "role": "customer"}],
        "note": [{"text": (
            "AI Resolution: Valid dispute — fee disclosure not confirmed in eSIM swap order flow. "
            "$25 credit auto-approved (amount within $30 auto-close threshold). "
            "Ticket resolved automatically."
        ), "author": "Resolution Engine"}],
    }
    r = requests.post(f"{BACKEND}/trouble-tickets", json=payload, timeout=10)
    tid = r.json()["id"]
    requests.patch(f"{BACKEND}/trouble-tickets/{tid}",
                   json={"status": "resolved",
                         "statusChangeReason": "Auto-resolved: $25 credit applied (under $30 threshold)"},
                   timeout=5)
    console.print(f"  [dim]Created auto-closed ticket: {tid}[/dim]")
    return tid


def ensure_ticket_exists_for_path3() -> str:
    """Ensure an escalated ticket from Path 3 exists for the agent dashboard."""
    r = requests.get(f"{BACKEND}/trouble-tickets?limit=10", timeout=5)
    tickets = r.json().get("tickets", [])

    # Look for the escalated ticket (should have been created during chunk 4)
    for t in tickets:
        if t.get("status") in ("escalated", "pending", "open"):
            console.print(f"  [dim]Found escalated ticket: {t['id']}[/dim]")
            return t["id"]

    # Look for any non-resolved ticket
    for t in tickets:
        if t.get("status") != "resolved":
            console.print(f"  [dim]Using ticket: {t['id']} ({t.get('status')})[/dim]")
            return t["id"]

    console.print("  [yellow]No escalated ticket — creating Path 3 ticket...[/yellow]")
    payload = {
        "name": "Billing Dispute - Premium Setup Fee",
        "description": "Customer disputes $85 Premium Setup Fee on Feb bill (INV-2026-0214). Order ORD-91205 confirmation shows Standard Installation selected. Premium tier auto-added by coverage-zone routing rule (Zone C).",
        "severity": "major",
        "ticketType": "billing",
        "channel": {"name": "telegram"},
        "relatedParty": [{"id": "C007003", "name": "John Dawson", "role": "customer"}],
        "note": [{"text": (
            "AI Analysis: Order confirmation shows 'Standard Installation' selected. "
            "Premium Setup Fee ($85) auto-added by coverage-zone flag (Zone C — premium routing). "
            "Verdict: Valid dispute — customer did not opt into premium tier. "
            "Recommendation: Full $85 credit. Confidence: High."
        ), "author": "Resolution Engine"}],
    }
    r = requests.post(f"{BACKEND}/trouble-tickets", json=payload, timeout=10)
    tid = r.json()["id"]
    console.print(f"  [dim]Created escalated ticket: {tid}[/dim]")
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

    # Find actual mp4 by output_name in script
    script_path = SCRIPTS_DIR / chunk["script"]
    try:
        script = json.loads(script_path.read_text())
        output_name = script.get("metadata", {}).get("output_name", "")
        mp4 = OUTPUT_DIR / f"{output_name}.mp4" if output_name else None
    except Exception:
        mp4 = None

    if not mp4 or not mp4.exists():
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
        description="Record three-path ticketing demo end-to-end.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[1].strip() if "Usage:" in __doc__ else "",
    )
    parser.add_argument("--chunks", default="0123456",
                        help="Chunks to record: '0123456' (all), '124' (Telegram only), '35' (dashboards). Default: 0123456")
    parser.add_argument("--verify", action="store_true",
                        help="Show key frames after each chunk; prompt to re-record if bad")
    parser.add_argument("--verify-only", action="store_true",
                        help="Skip recording — just show key frames from existing files")
    parser.add_argument("--skip-stitch", action="store_true", help="Skip final stitch")
    parser.add_argument("--no-open", action="store_true", help="Don't open video after stitching")
    args = parser.parse_args()

    chunks_to_record = [c for c in CHUNKS if c["id"] in args.chunks]

    console.print(Panel(
        f"[bold]Three-Path Ticketing Demo Recorder[/bold]\n"
        f"Chunks: {', '.join(c['label'] for c in chunks_to_record)}\n"
        f"Verify: {'yes (interactive)' if args.verify else 'no'}\n"
        f"Output: {OUTPUT_DIR}",
        style="blue",
    ))

    # ── verify-only mode: just show frames
    if args.verify_only:
        for chunk in CHUNKS:
            verify_chunk(chunk["id"], auto=False)
        return

    # ── service checks
    services_needed = set()
    services_needed.update(
        svc for c in chunks_to_record for svc in c.get("needs", [])
    )
    wait_for_services(services_needed)

    # ── ensure demo customers exist
    console.print("\n[bold]Ensuring demo customers exist...[/bold]")
    ensure_demo_customers()

    # ── record chunks in dependency order
    chunk4_was_recorded = False
    for chunk in chunks_to_record:
        cid = chunk["id"]

        # Data setup per chunk
        if cid == "0":
            console.print("\n[bold]Cleaning up for baseline...[/bold]")
            reset_conversations()
            delete_all_tickets()

        elif cid in ("1", "2", "4"):
            console.print(f"\n[bold]Resetting conversations for chunk {cid}...[/bold]")
            reset_conversations()

        elif cid == "3":
            console.print("\n[bold]Ensuring Path 2 ticket exists for CRM check...[/bold]")
            ensure_ticket_exists_for_path2_crm()

        elif cid == "5":
            console.print("\n[bold]Ensuring escalated ticket exists for agent review...[/bold]")
            ensure_ticket_exists_for_path3()

        ok = record_with_verify(chunk, verify=args.verify, interactive=True)
        if not ok:
            console.print(f"\n[red]Aborting — chunk {cid} failed.[/red]")
            sys.exit(1)

        if cid == "4":
            chunk4_was_recorded = True

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
