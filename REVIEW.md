# Review of PRD v0.1 and SRD v0.1

Reviewed: 22 Oct 2026, 14:00 IST, by a senior-AI-engineer pass.
Output of this review: `PRD.md` v0.2 and `SRD.md` v0.2 (fixes are mapped below).

## Facts verified before judging the documents

| Fact | Source | Consequence |
|---|---|---|
| Submission deadline is **Fri 23 Oct 2026, 12:00 PM PDT = Sat 24 Oct 00:30 IST**. About 34 hours were left at review time. | Devpost rules | v0.1 plans five phases and 13 FRs with no timeline. It must be cut down hard. |
| Alexa+ track = working Agent Skill **or** self-hosted MCP server (MCP 2025-11-25 or later, Streamable HTTP). A web page acting as a real MCP client (initialize, tools/list, tools/call) satisfies it. Gated Alexa+ tools are not available. | Rules + FAQ | The v0.1 approach is valid. The "simulated assistant" framing is fine. |
| Judging: 4 equal criteria (Tech Implementation, Design, Potential Impact, Quality of Idea). For Alexa+, "basic MCP wrapper around an existing API" is listed as *obvious*. Creative = state across sessions, cards/carousels, agentic workflows, MCP Apps, Agent Skills. Friction log can add up to 10%. | Rules | v0.1 has no differentiators and no friction-log process. |
| Repo must be on GitHub. Public needs a detectable license file. Private must be shared with 5 named reviewers plus Devpost, and invites expire after 7 days. Video under 3 min, public on YouTube or Vimeo, no third-party trademarks or copyrighted music. Product-feedback form is mandatory. | Rules + FAQ | The v0.1 checklist misses most of these. |
| **MCP Python SDK v2 is the current stable line.** `pip install mcp` installs 2.x. `FastMCP` became `MCPServer`. Transport options (`stateless_http`, `json_response`, host/port) moved from the constructor to `run()`. The client is now `from mcp import Client`. v2 speaks spec 2026-07-28 and still serves 2025-era clients. | SDK README, v2.0.0 release notes, migration guide | The SRD's "FastMCP / pinned SDK" assumption is stale and would fail on a fresh install. |
| "Afterbuy" is an established German e-commerce SaaS (ViA-Online GmbH, Krefeld; formerly owned by eBay). | Web search | Real trademark and IP risk. Rules require no IP violations, and the video may not show third-party trademarks. |

## Findings

Severity: **B** blocker, **H** high, **M** medium, **L** low.

| # | Sev | Finding | Fix (where) |
|---|---|---|---|
| 1 | B | No realistic schedule. Five phases, 13 FRs, 6 tools, tests and a clean-clone check cannot fit in about 34 hours solo. There is no cut line. | PRD §12 timeline with IST blocks and an explicit cut order. P0 list reduced. |
| 2 | B | Product name collides with an existing e-commerce product. | Renamed to working title **GraceDays** (not trademark-checked). It is one config constant and one package name. PRD §1. |
| 3 | B | SDK API is stale (FastMCP, constructor transport options). | SRD §2 and §8 target v2 (`MCPServer`, `run(...)`, `Client`). A one-hour spike gate has a documented v1.28 fallback. SRD §16. |
| 4 | B | The chat LLM is given all six tools, including `save_purchase` and `delete_purchase`. A `confirmed: bool` argument is trivially forgeable by the model or by injected text. This defeats the "confirm before saving" and "never delete from pasted text" rules. | Tool tiers: agent-facing tools vs UI-only vs admin. The agent's allowlist excludes save, delete, seed and reset. Update tools take one ID (no bulk). The threat model is stated honestly. SRD §3.3. |
| 5 | B | The UI promises one-click demo data and reset, but there is no MCP tool for it. The UI is also forbidden to write the DB directly, and "delete only sample records" needs a column the schema lacks. | `seed_demo_data` and `reset_demo_data` tools plus an `is_demo` column. SRD §6, §8. |
| 6 | B | Sample data uses fixed dates (e.g. 2026-10-10 / 10-24). "This week" demos break once the date moves, and judging runs 9–20 Nov. | Date-relative seed data and sample templates. `APP_FAKE_TODAY` for recording. SRD §7, §14. |
| 7 | H | The LLM is asked to normalize dates and do date arithmetic. LLMs are unreliable at both. | The LLM returns verbatim date text and a rule (anchor + amount + unit). Code parses and computes. Ambiguous or year-less dates become `needs_review`. SRD §9. |
| 8 | H | Nothing checks that an "evidence excerpt" really appears in the source. The model can fabricate quotes, which breaks the evidence-first rule. | Normalized substring verification before review. Unverified evidence is flagged. SRD §9.4. |
| 9 | H | Indirect prompt injection: stored excerpts come back as tool results into the chat model's context. The v0.1 rules only cover the extraction step. | Extraction runs tool-less. Excerpts are length-capped and delimited as data. The agent has no destructive tools. A grounding guard and injection tests are added. SRD §10, §14. |
| 10 | H | The status model is inconsistent. `upcoming` is both stored and derived. "Resolved" is undefined. A returned purchase still shows open return deadlines. FR-05 "undated/unknown" has no storage. | Stored deadline status is `open/completed/dismissed`. Derived states are `overdue/due_today/upcoming/passed/completed/dismissed/closed`. Added `purchases.unknown_fields`. Semantics table in PRD §9 and SRD §7. |
| 11 | H | "Overdue" is applied to warranty expiry and renewal dates, which is meaningless for informational dates. | `passed` state for `warranty_expires` and `renewal_on`. SRD §7.2. |
| 12 | H | The "classify intent, then call a tool" design is brittle and ignores MCP tool discovery. The provider adapter has no tool-calling contract. Gemini rejects some JSON-Schema constructs. | Native tool calling over tools discovered via MCP `list_tools`. Agent-facing tools use flat primitive parameters. Provider interface defined. Max 5 loop steps. SRD §10. |
| 13 | H | The PRD promises a deterministic fallback when the API fails, but the SRD never defines it. Tests also need it. | `mock` provider (scripted, clearly labelled) and an offline-mode banner. SRD §10.6. |
| 14 | H | No judging alignment. The design reads as the "basic MCP wrapper" the rules call obvious. No voice-friendly output, no cards. | PRD §5 maps differentiators to the criteria: state across sessions, evidence cards, a multi-step agentic workflow, and a proactive briefing. Replies are short and voice-friendly, with an optional read-aloud button. |
| 15 | H | The submission checklist is incomplete (GitHub-only, license detectable, reviewer invites, 5 feedback questions, friction log, trademark-free video). | PRD §14 rewritten against the actual rules. |
| 16 | H | The repo layout uses generic top-level packages (`agent`, `domain`, `config`, `tests`) with no package root. Imports will break or collide. | `src/gracedays/` package layout with `pyproject.toml`. SRD §4. |
| 17 | H | SQLite pitfalls. Foreign keys are off by default, so `ON DELETE CASCADE` silently does nothing without `PRAGMA foreign_keys=ON` on every connection. The relative `DATABASE_URL` depends on cwd. The "SQLAlchemy or sqlite3" choice is left open. The `product_name` index does not help `LIKE '%x%'`. | stdlib `sqlite3`, a PRAGMA per connection, CHECK constraints, an absolute DB path. SRD §6. |
| 17a | M | `date.today()` contradicts the "configured timezone" rule. There is no clock injection for tests. | `Clock` abstraction with `ZoneInfo`, plus a `tzdata` dependency. SRD §7.1. |
| 18 | M | The LLM-reported `confidence` float is uncalibrated and misleading. | Replaced with a `verification` enum (`explicit`, `derived`, `user_entered`) plus ambiguity flags. SRD §6, §9. |
| 19 | M | Multi-item orders and double pastes are not handled. | Duplicate detection is P0. The extractor returns up to 5 items and the user picks one (single-item P0, multi-item P1). SRD §8, §9. |
| 20 | M | A free-form LLM draft can invent order numbers and addresses. | A deterministic template tool, `draft_action_message`, with placeholders and a "DRAFT, not sent" label. SRD §8. |
| 21 | M | Name matching ("my laptop") against product names is naive. | Tokenized matching, a fallback to `list_purchases`, and `needs_choice` on multiple matches. SRD §8. |
| 22 | M | Streamlit reruns the script on every interaction. v0.1 does not address async MCP calls, session state or double-submits. | A sync `McpGateway` with short-lived `Client` sessions against a stateless server. Form-based submits. SRD §11. |
| 23 | M | Privacy is only a warning. Card numbers can still reach the provider. | Luhn-based card redaction before any provider call. SRD §9.2, §13. |
| 24 | M | Missing fields: the renewal price is the most useful subscription fact. `unknown_fields` is not persisted. | Added `price_text` and `unknown_fields`. SRD §6. |
| 25 | M | There are no measurable success criteria and no extraction eval. | PRD §3 metrics. SRD §14 eval harness with 8 fixtures, including negative, ambiguous and injection cases. |
| 26 | M | A "health indicator" is required but the mechanism depends on a custom-route API that is unverified in v2. | Health = `list_tools` ping through the client. SRD §15. |
| 27 | M | The AWS Builder mini-challenge is deferred without a plan. | Bedrock adapter is P1, behind the provider interface. Mock Bedrock in dev, per the FAQ. PRD §5. |
| 28 | L | The `software_service` / `subscription` categories overlap. | `digital_purchase` replaces `software_service`. |
| 29 | L | Both documents end with truncated reference lines and no URLs. | References completed. |
| 30 | L | The Python target is ambiguous (3.11 vs 3.12). | Python 3.12, with a floor of 3.10 imposed by the SDK. |
| 31 | L | Open-source mini-challenge is unmentioned. | PRD §14 notes it. Ask Devpost whether this repo qualifies. A docs PR from the friction log is a cheap fallback. |

## Things in v0.1 that were right and are kept

- The trust principles: evidence first, never invent dates, confirm before saving, a draft is not a submission.
- Using a real MCP server and client over HTTP rather than direct function calls.
- Pasted text only, with no inbox, OCR or auto-actions.
- SQLite plus Streamlit as the speed-first stack.
- A server-side revalidation mindset, and loopback binding.
