#!/usr/bin/env python3
"""Generate narration audio files for review — separate from video recording."""

import asyncio
from pathlib import Path
import edge_tts

VOICE = "en-US-AndrewNeural"
RATE = "-5%"
OUTPUT_DIR = Path(__file__).parent / "output" / "narrations"

# ── Narration scripts per video ──────────────────────────────────────────────

VIDEOS = {
    "video1_selfservice": [
        ("01_intro", "A customer notices an unexpected charge on their bill and reaches out on Telegram. The AI agent will handle this end-to-end — no ticket, no human involvement."),
        ("02_processing", "The AI Customer Care Agent classifies this as a billing inquiry and queries the platform's TMF-compliant APIs — Billing and Account — to retrieve invoice details, order history, and account context. No scripted decision trees. The agent reasons about the data in real time."),
        ("03_reply", "The agent traces the charge to an eSIM swap the customer requested last week. It returns a contextual explanation with the specific invoice reference and the triggering order."),
        ("04_resolved", "The customer is satisfied. The agent detects the issue is resolved and closes the session. No ticket was created because none was needed — the platform only escalates when the customer or the situation requires it."),
        ("05_closing", "First-contact resolution. One conversation, zero overhead."),
    ],
    "video2_autoclose": [
        ("01_intro", "A customer disputes a twenty-five dollar activation fee they believe was never disclosed. This time, the explanation won't be enough — the customer wants a formal dispute."),
        ("02_processing", "The AI agent queries billing and account APIs, identifies the eSIM swap as the trigger, and provides the explanation."),
        ("03_dispute", "The customer disagrees and requests a ticket. The agent detects the escalation intent and activates the Ticket Ingestion Engine. It validates that all required fields are present — dispute type, charge amount, invoice reference, related order, and the customer's stated reason — before creating the ticket in the CRM."),
        ("04_resolution", "The Resolution Engine evaluates the dispute — checks the claim, calculates the variance, classifies the impact. Twenty-five dollars falls within the auto-close threshold, a configurable business rule. Credit applied, ticket closed, customer notified — all within the conversation."),
        ("05_crm", "The full audit trail is in the CRM. Dispute type, charge, invoice, resolution, and the auto-close rule that was applied. Every field populated by the AI workflow — no manual data entry."),
        ("06_closing", "End-to-end resolution without any human agent involvement. The platform applies deterministic rules where appropriate and reserves human judgment for cases that need it."),
    ],
    "video3_escalation": [
        ("01_intro", "A customer disputes an eighty-five dollar Premium Setup Fee they say they never agreed to. The amount exceeds the auto-close threshold — this one needs a human decision."),
        ("02_processing", "The AI agent queries a broader set of APIs — Billing, Orders, Product Catalog, and Account — to build a complete picture. It identifies the charge as linked to a Fiber Home Installation order and explains the premium tier."),
        ("03_dispute", "Same ingestion flow — the agent collects dispute type, charge, invoice, related order, and the customer's reason. The Ingestion Engine validates completeness and creates the ticket. But eighty-five dollars exceeds the auto-close threshold."),
        ("04_escalation", "The AI completes its full analysis — the order confirmation shows standard installation was selected, the premium fee was added by a coverage-zone rule. The verdict: valid dispute, recommend full credit. But the platform doesn't auto-apply it. It attaches the analysis and routes the ticket to a human agent."),
        ("05_customer_told", "The customer is told a specialist will review their case. Behind the scenes, the agent receives everything — conversation, ticket details, AI analysis, and a confidence-scored recommendation."),
        ("06_agent_dashboard", "The agent doesn't need to re-investigate. The AI found the order shows standard installation was selected. The premium fee was auto-added by a zone routing rule. Recommendation: full eighty-five dollar credit, high confidence."),
        ("07_agent_accepts", "The agent reviews the reasoning, verifies the data, and makes the call. Human judgment where it matters — augmented, not replaced, by AI."),
        ("08_crm", "Credit approved, ticket resolved. The agent spent thirty seconds reviewing instead of thirty minutes investigating."),
        ("09_closing", "The same platform handled all three outcomes — self-service, automated resolution, and human-assisted review — calibrated to the complexity and value of each case."),
    ],
    "workflow_shared": [
        ("01_overview", "Each customer interaction triggers a directed acyclic graph — a sequence of AI agents with built-in branching logic. Adding a new resolution type doesn't require code changes, just a new workflow configuration."),
        ("02_classification", "The classification stage uses a large language model to parse free-text messages into structured intents. It doesn't rely on keyword matching — it understands context."),
        ("03_validation", "Customer validation happens against the live CRM in real time. The trouble ticket follows TMF six-two-one standards — interoperable with any downstream system without custom integration."),
        ("04_resolution", "The resolution engine performs root cause analysis. Every decision is logged, every data point is traceable. The full reasoning chain is available for audit."),
    ],
}


async def generate_audio(text: str, output_path: Path) -> float:
    """Generate TTS audio and return duration in seconds."""
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    await communicate.save(str(output_path))

    # Get duration using ffprobe
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-i", str(output_path), "-show_entries", "format=duration",
         "-v", "quiet", "-of", "csv=p=0"],
        capture_output=True, text=True,
    )
    duration = float(result.stdout.strip()) if result.stdout.strip() else 0
    return duration


async def generate_all():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for video_name, segments in VIDEOS.items():
        video_dir = OUTPUT_DIR / video_name
        video_dir.mkdir(exist_ok=True)

        print(f"\n{'='*60}")
        print(f"  {video_name}")
        print(f"{'='*60}")

        total_duration = 0
        for seg_id, text in segments:
            out_path = video_dir / f"{seg_id}.mp3"
            duration = await generate_audio(text, out_path)
            total_duration += duration
            print(f"  {seg_id:<25} {duration:5.1f}s  {out_path.name}")

        # Also generate a combined audio for the full video narration
        full_text = " ".join(text for _, text in segments)
        full_path = video_dir / f"_full_{video_name}.mp3"
        full_dur = await generate_audio(full_text, full_path)
        print(f"  {'_FULL':<25} {full_dur:5.1f}s  {full_path.name}")
        print(f"  Total segment duration: {total_duration:.1f}s")


if __name__ == "__main__":
    asyncio.run(generate_all())
