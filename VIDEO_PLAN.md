# Video Plan: Billing Dispute AI Resolution Demo

## Overview

| Field | Value |
|-------|-------|
| **Title** | Channel AI Support — Billing Dispute Resolution |
| **Duration** | ~5 min 25s (intro + 4 chunks + transitions + outro) |
| **Output** | `billing_dispute_30_demo_branded.mp4` |
| **Audience** | Telco CxOs, product managers, solutioning teams |
| **Key Message** | A $30 billing dispute resolved end-to-end — from Telegram chat through AI workflow orchestration to a closed CRM ticket. No hold time, no transfers, no human agent. |

### Stitch Order

```
intro.mp4 → chunk_0 (from 15s) → chunk_1 (from 24s) → transition-1.mp4 → chunk_2 (from 20s) → transition-2.mp4 → chunk_3 (from 3s) → outro.mp4
```

---

## Chunk 0: Empty CRM Baseline (~10s)

### Purpose
Establish a clean starting point — the CRM has no open tickets. This creates a before/after contrast with chunk 3 where the AI-created ticket appears.

### Visual Direction
- CRM ticket list page with empty DataGrid (no rows)
- Clean, professional portal interface

### Recording Script (5 steps)

| Step | Action | Detail | Wait |
|------|--------|--------|------|
| s01 | navigate | `http://localhost:8010/health` (page context for API calls) | 1000ms |
| s02 | evaluate | Cleanup: `POST /channel-router/reset` + delete all tickets | 2000ms |
| s03 | navigate | `http://localhost:5173/ai-poc/crm-portal/tickets` | 12000ms |
| s04 | screenshot | Empty CRM + narration | 4000ms |
| s05 | wait | Final pause | 1500ms |

### Narration Script

| Step | Narration |
|------|-----------|
| s04 | "We start with a clean CRM — no open tickets. Let's see what happens when a customer reaches out." |

### Pacing
- 12s wait for CRM page load (React + MUI DataGrid render)
- Stitch trims first 15s (cleanup + page load), viewer only sees the loaded empty state
- Brief ~10s visible segment — just enough to establish the baseline

---

## Chunk 1: Telegram Chat (~2 min 40s)

### Purpose
Show a real customer interaction on Telegram — Sarah Mitchell disputes a $30 charge and the AI resolves it in 3 exchanges.

### Visual Direction
- Clean Telegram Web interface, sidebar hidden, chat header renamed to "Sarah Mitchell"
- Customer types messages with visible typing animation (40ms/char delay)
- AI responses appear after realistic wait times (25-30s)
- Camera stays static — the conversation IS the visual

### Narration Script

| Timing | Narration |
|--------|-----------|
| 0:03 | "A customer notices an unexpected charge on their bill. They open Telegram and message support — no app to install, no call center to dial." |
| 0:18 | "No hold music, no IVR menus — just a simple chat message to start." |
| 0:52 | "The AI instantly classifies this as a billing complaint and asks Sarah for her account details — all within seconds." |
| 1:31 | "Behind the scenes, the platform validates Sarah's identity against the CRM, confirming customer C006064 with an active account." |
| 2:13 | "A trouble ticket is automatically created following TMF621 standards, and the billing analysis engine is triggered." |
| 2:24 | "The AI explains the root cause of the charge, applies the appropriate resolution, and closes the ticket — three turns, zero human intervention." |
| 2:37 | "Now let's look behind the scenes at how the AI platform orchestrated this entire resolution." |

### Key Moments
- First message sent → shows simplicity of channel
- AI's first response → demonstrates instant classification
- Resolution message → the "wow" moment (fully automated)
- Transition narration → bridges to chunk 2

### Pacing
- Allow 25-30s for AI responses (realistic, builds anticipation)
- Scroll slowly to new messages (viewer follows the conversation)
- Final narration should feel like a confident transition

---

## Chunk 2: Platform Workflow (~45s)

### Purpose
Show the intelligent workflow DAG that orchestrated the resolution — the "brain" behind the conversation.

### Visual Direction
- Direct load of workflow diagram at `http://localhost:5173/ai-poc/workflow-demo`
- Full viewport, white background with dot pattern, animated edges flowing
- Three shots: overview → complaint branch zoom → resolution detail zoom
- Animated edges provide constant subtle motion (flowing blue dashes)
- Pulsing start (green) and end (red) nodes draw the eye

### Recording Script (8 steps)

| Step | Action | Detail | Wait |
|------|--------|--------|------|
| s01 | navigate | `/ai-poc/workflow-demo` | 2500ms |
| s02 | wait | React Flow fitView settles | 1500ms |
| s03 | screenshot | Full overview + narration | 3500ms |
| s04 | evaluate | Zoom to complaint branch: `scale(1.4) translate(-1000px, -165px)` | 2000ms |
| s05 | screenshot | Complaint path detail + narration | 3500ms |
| s06 | evaluate | Zoom to Resolution node: `scale(2.0) translate(-3140px, -576px)` | 2000ms |
| s07 | screenshot | Resolution close-up (silent) | 1000ms |
| s08 | wait | Final pause | 1500ms |

### Narration Script

| Step | Narration |
|------|-----------|
| s03 (overview) | "The platform orchestrates the entire resolution through an intelligent workflow — AI agents handle classification, validation, and resolution while business rules control the flow." |
| s05 (complaint zoom) | "For this billing dispute, the workflow detected a complaint, validated the customer against CRM, created a trouble ticket, and analyzed the billing data — all automated, all auditable." |

### Key Moments
- Overview shot: viewer sees the full complexity → "this is sophisticated"
- Zoom into complaint branch: viewer follows the exact path their demo took
- Resolution diamond: visual proof of automated decision-making

### Pacing
- Hold overview for full narration duration (~10s) — let animated edges mesmerize
- Smooth CSS transition zoom (1.5s ease-in-out) — feels cinematic
- Silent resolution close-up is brief — just a visual punctuation

### Zoom Tuning Notes
The translate values assume fitView places the canvas at ~0.42 scale. If positions differ after recording:
- Complaint branch center: canvas coords ~(1400, 485)
- Resolution node center: canvas coords ~(2050, 545)
- Formula: `tx = viewport_center_x - canvas_x * scale`, `ty = viewport_center_y - canvas_y * scale`

---

## Chunk 3: CRM Portal (~1 min 5s)

### Purpose
Verify the ticket exists in the CRM — proof that the AI workflow produced a real, auditable business artifact.

### Visual Direction
- CRM ticket list page with DataGrid showing all tickets
- Click into the specific billing dispute ticket
- Scroll to show full ticket details
- Click "View Conversation" to show the linked Telegram chat

### Recording Script (8 steps)

| Step | Action | Detail | Wait |
|------|--------|--------|------|
| s01 | wait | Opening narration | 1500ms |
| s02 | navigate | `/ai-poc/crm-portal/tickets` | 15000ms |
| s03 | wait | Ticket list narration | 10000ms |
| s04 | click | First DataGrid row | 2500ms |
| s05 | screenshot | Ticket detail narration | 5000ms |
| s06 | scroll | Down 500px (silent) | 2000ms |
| s06b | click | "View Conversation" button | 3000ms |
| s06c | screenshot | Conversation view narration | 2000ms |
| s07 | screenshot | Closing narration | 25000ms |

### Narration Script

| Step | Narration |
|------|-----------|
| s01 | "Finally, let's verify the result in the CRM portal." |
| s03 | "The ticket list shows all customer issues. The billing dispute ticket was created automatically during the conversation." |
| s05 | "Category, priority, customer details, and resolution status — all populated by the AI, fully auditable." |
| s06c | "The complete Telegram conversation is attached to the ticket for compliance and quality review." |
| s07 | "A thirty-dollar billing dispute, resolved end-to-end — from Telegram chat, through AI workflow orchestration, to a closed CRM ticket. No hold time, no transfers, no human agent needed." |

### Key Moments
- Ticket appears in list → proves the workflow actually created something
- Ticket detail → shows TMF621 fields populated correctly
- Linked conversation → full audit trail
- Closing narration → powerful summary that ties all 3 chunks together

### Pacing
- 15s wait for CRM page load (data-heavy)
- Hold on ticket detail for viewer to read fields
- Closing narration is the longest single narration (~12s) — deliver with confidence

---

## Transitions

### Intro → Chunk 1
The intro establishes the Bluemarble Intelligence Platform brand. Cut directly into the Telegram chat — the viewer is immediately in the customer's shoes.

### Chunk 1 → Chunk 2 (transition-1.mp4)
**Bridge narration** (end of chunk 1): "Now let's look behind the scenes at how the AI platform orchestrated this."
The viewer shifts from customer perspective to platform perspective. The transition visual should feel like "pulling back the curtain."

### Chunk 2 → Chunk 3 (transition-2.mp4)
After seeing the workflow, the viewer naturally asks: "Did it actually work?" Chunk 3 answers this immediately with the CRM verification.

### Chunk 3 → Outro
The closing narration delivers the value proposition summary. Outro reinforces the brand.

---

## Visual Polish Notes

### Chunk 1 (Telegram)
- CSS injection hides sidebar, old messages, and renames header to "Sarah Mitchell"
- Bot "keyboard" buttons hidden via `.reply-markup` display:none
- Service messages hidden via `.service-msg` display:none
- Consider: increase font-size of chat bubbles for video readability

### Chunk 2 (Workflow)
- Page already has animated edges, pulsing nodes, glowing conditions — no extra CSS needed
- The `evaluate` zoom steps use CSS transitions on `.react-flow__viewport` — smooth 1.5s ease-in-out
- If zoom doesn't center correctly, adjust translate values per the formula in Zoom Tuning Notes
- The MiniMap in bottom-right provides spatial context during zoom

### Chunk 3 (CRM)
- 15s initial page load wait is necessary for MongoDB data
- The MUI DataGrid row selector `.MuiDataGrid-row:first-child` assumes the new ticket is first (sorted by creation date desc)
- "View Conversation" button must exist on the ticket detail page — ensure the backend returns conversation data via `GET /trouble-tickets/{ticketId}/conversation`

---

## Pre-Recording Checklist

- [ ] ai-poc-backend running on port 8010 (for Telegram bot + CRM data)
- [ ] ai-poc-frontend running on port 5173 (for workflow page + CRM portal)
- [ ] Telegram bot auth state valid (`telegram_auth.json` exists)
- [ ] Workflow demo page loads at `http://localhost:5173/ai-poc/workflow-demo`
- [ ] CRM portal loads at `http://localhost:5173/ai-poc/crm-portal/tickets`
- [x] **Auto-cleanup**: chunk_0 runs cleanup (`POST /channel-router/reset` + delete all tickets) during its trimmed portion, then shows the empty CRM to establish baseline
- [ ] Record chunks in order: 0, 1, 2, 3 (chunk 0 cleans DB + shows empty CRM, chunk 1 creates the ticket, chunk 3 verifies it)
- [ ] Stitch with `python stitch.py` after all chunks are recorded
- [ ] Review final video for audio sync, subtitle alignment, zoom smoothness
