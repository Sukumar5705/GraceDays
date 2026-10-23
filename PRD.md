# GraceDays: Product Requirements Document (PRD)

| | |
|---|---|
| Document version | 0.2 (corrected; supersedes 0.1) |
| Date | 22 October 2026 |
| Status | Ready to build |
| Hackathon | Amazon Developer Hackathon, **Alexa+ track** (self-hosted MCP server over Streamable HTTP, plus a simulated assistant web app) |
| Working title | **GraceDays**. The v0.1 title "AfterBuy" is an existing e-commerce product (ViA-Online GmbH). Neither name has had a trademark check. The name lives in one config constant and one package name. |
| Related | `SRD.md` v0.2, `REVIEW.md` |

## 0. What changed from v0.1

- Added the verified deadline and a time-boxed plan with a cut line (§12).
- Added measurable success metrics (§3) and mapping to the judging criteria (§5).
- Tightened the trust rules so they hold for the chat agent too (§8).
- Defined status semantics (§9). v0.1 contradicted itself here.
- Added an offline/mock mode, relative-date demo data, duplicate detection and a proactive briefing.
- Rewrote the submission checklist against the actual rules (§14).
- Removed or deferred scope that cannot fit in about 34 hours (§6, §10).

## 1. Product summary

GraceDays is a consumer assistant for the obligations that start after a purchase: return windows, subscription-trial cancellations, renewals and warranty dates.

The user pastes an order confirmation, subscription email or policy text. GraceDays proposes the key dates and **shows the exact source text each date came from**. The user confirms, and the record is saved. Later the user asks "what needs my attention?" or "can I still return my headphones?". The assistant answers from saved data through real MCP tool calls. It can also draft the return or cancellation message.

GraceDays does not buy anything. It does not read inboxes or retailer accounts. It does not return, refund or cancel anything, and it never says it did.

**Pitch:** GraceDays remembers the deadlines hidden in your purchase emails and helps you act before you miss them.

## 2. Context and constraints

- **Deadline:** Fri 23 Oct 2026, 12:00 PM PDT = **Sat 24 Oct 00:30 IST**. Plan to submit by **21:30 IST on 23 Oct** at the latest.
- **Team assumption:** one developer, Python-first. If the team is larger, keep this scope and finish earlier.
- **Track fit** (from the official rules and FAQ):
  - Alexa+ accepts a self-hosted MCP server (spec 2025-11-25 or later) over Streamable HTTP.
  - A web page that acts as a real MCP client (initialize, tools/list, tools/call) counts as the simulated Alexa+ path.
  - Gated Alexa+ tools are unavailable. The project demos on its own web front end.
  - A locally runnable public repo plus the demo video is enough for judging. No hosting is needed.
- **Judges may score from the description and video alone**, so the video and README matter as much as the code.

## 3. Goals and success metrics

### Goals

1. Turn pasted text into a structured, **evidence-backed** purchase record.
2. Persist confirmed records across refresh and restart.
3. Answer record questions only from saved data, via MCP tool calls.
4. Make real MCP use visible in the demo.
5. Ship one polished, repeatable end-to-end demo.

### Measurable acceptance targets

| # | Metric | Target |
|---|---|---|
| M1 | Extraction eval (8 synthetic fixtures, SRD §14.4): fabricated deadlines on negative fixtures | **0** |
| M2 | Extraction eval: expected deadlines with the exact correct date | ≥ 90% |
| M3 | Saved evidence excerpts that are verbatim substrings of the source | 100% (unverified excerpts must be flagged, never silently saved) |
| M4 | Scripted chat questions about records that make at least one MCP tool call | 100% |
| M5 | Dates in assistant answers that are not present in tool results | 0 (enforced by the grounding guard) |
| M6 | MCP tool-call latency, local p95 | < 300 ms |
| M7 | Live extraction latency, p95 | ≤ 15 s |
| M8 | Clean clone to running demo, following the README | ≤ 10 min |
| M9 | Demo video length | ≤ 2:50 |

## 4. Users and needs

**Primary:** students and early-career professionals buying electronics, software or subscriptions who do not want to connect their inbox.

**Needs:**

- Capture purchase info without filling every field.
- Know which deadline matters first.
- See why a date was extracted and where it came from.
- Ask in plain language and get an answer grounded in saved data.
- Get a ready-to-send **draft** for a return or cancellation.

Multi-user and household use are out of scope.

## 5. Judging alignment

The four criteria are equally weighted. The rules list "basic MCP wrapper" and "single-turn Q&A bot" as *obvious* for Alexa+. These differentiators are built on purpose:

| Criterion | How GraceDays addresses it | Requirements |
|---|---|---|
| **Tech implementation** | A real MCP server (official Python SDK, Streamable HTTP, protocol version asserted in tests). The web app is a real MCP client that discovers tools via `tools/list`. Tiered tool exposure, schema validation, deterministic date engine and a grounding guard. | FR-02, FR-06, FR-08 |
| **Design** | A coherent Capture → Review → Save → Ask → Act flow. Evidence cards, a visible tool-activity pane, and explicit unknown, ambiguous and error states. | FR-03, FR-05, FR-06 |
| **Potential impact** | A common, costly problem (missed return windows and silent renewals), with a clear trust model. | §1, §8 |
| **Quality of the idea** | The "creative" Alexa+ markers: **state that persists across sessions**, **cards**, a **multi-step agentic workflow** ("help me return X" = find → verify window → draft → track), and a **proactive briefing** on open. Replies are short and voice-friendly, with an optional read-aloud button. | FR-05, FR-06, FR-07, FR-13 |

**Mini-challenges (opportunistic, never at the expense of P0):**

- **AWS Builder:** a Bedrock provider adapter behind the provider interface (FR-14, P1). Document the integration in the product-feedback form.
- **Open Source:** the repo will be public with a license. Confirm with Devpost whether the primary repo counts. The rules say "new, additional" project or contribution. A small docs or bug PR from the friction log is the fallback.
- **Friction log:** worth up to a 10% bonus. Keep `FRICTION.md` from hour 0. Real entries only (FR-15).

## 6. Non-goals (hackathon MVP)

- Gmail, Outlook, retailer, bank or payment integrations.
- Any automatic external action (return, refund, cancel, contact a merchant).
- Real email, SMS or push delivery. Reminders must never be faked.
- Accounts, auth, teams, cloud sync, public hosting.
- Real Alexa+ device or gated-toolkit integration.
- PDF/image/OCR/attachment parsing, browser automation.
- Business-day or holiday arithmetic, recurring-renewal projection, multi-currency pricing logic.
- Shopping recommendations, price tracking, checkout.

## 7. User journeys

**A. Capture:**

1. The user pastes an order or subscription email, or loads a synthetic sample.
2. The system redacts card-like numbers and shows a privacy notice.
3. It proposes fields plus deadlines. Each deadline shows its **evidence quote** and a state: *explicit*, *derived* (with the rule shown) or *needs review*.
4. Ambiguous, year-less or unsupported dates stay empty and are flagged. The system never invents them.
5. If the text may describe several items, the user picks the one to track.
6. If a likely duplicate exists, the user is told before saving.
7. The user edits or removes fields, then confirms. Nothing is stored before this step.

**B. Briefing and attention:**

1. On opening the Assistant tab, a deterministic briefing runs (one `list_deadlines` call): "2 items need attention".
2. The user can ask "What needs my attention this week?". The answer ranks overdue items first, then due today, then upcoming. Each item shows product, date, days remaining, reason and evidence.
3. With no matches, the assistant says there is no saved deadline. It does not make one up.

**C. Prepare the next action:**

1. The user says "Help me return my headphones".
2. The assistant finds the record and checks the return deadline state (computed by code).
3. If several records match, it asks the user to choose.
4. It produces a **DRAFT** from a template filled with saved facts. Missing facts are placeholders.
5. The assistant states that nothing was submitted. The user acts outside the app, then marks the item resolved.

**D. Persistence:** The user updates a status, refreshes or restarts both processes, and the state is unchanged.

**E. Offline fallback:** If the AI provider fails, the app shows a clear banner. Scripted demo mode (labelled) still runs the bundled flows. Nothing fails silently.

## 8. Trust and safety rules (product level)

1. **Evidence first.** Every saved date has an evidence excerpt or a visible derivation rule.
2. **Never invent a deadline.** Unknown stays unknown, with a prompt saying what is missing.
3. **Confirm before saving.** Only the UI's confirm action saves a purchase. The chat assistant cannot create or delete records.
4. **Draft ≠ submitted.** Drafts are labelled. The product never claims an external action occurred.
5. **Record answers come from tool results.** The assistant must not state a date that is not in the data it retrieved.
6. **Pasted and stored text is untrusted data.** Instructions inside emails or evidence must not change behavior or trigger tools.
7. **Minimum retention.** Store structured fields and short evidence excerpts only, never the full email.
8. **Privacy disclosure.** The UI says pasted text is sent to the configured AI provider. Card-like numbers are masked before sending. There is no inbox integration.
9. **No bulk or destructive action by chat.** Status changes apply to one record at a time. Deletion is a UI-only, separately confirmed action.

## 9. Domain semantics

**Purchase status:** `active`, `returned`, `cancelled`, `resolved`.

- "Resolved" means the user is done and wants no further attention on it.
- Any non-active status removes the purchase's open deadlines from "needs attention". They show as *closed*.
- Rows are not rewritten. Reactivating the purchase restores them.

**Deadline types:** `return_by`, `trial_cancel_by`, `renewal_on`, `warranty_expires`, `other`.

**Stored deadline status:** `open`, `completed`, `dismissed`.

**Derived state (computed daily, never stored):**

| State | Meaning |
|---|---|
| `overdue` | An actionable deadline (`return_by`, `trial_cancel_by`, `other`) is in the past and still open. |
| `due_today` | The due date is today. |
| `upcoming` | The due date is in the future. |
| `passed` | An informational date (`renewal_on`, `warranty_expires`) is in the past. |
| `completed` / `dismissed` | Set by the user. |
| `closed` | The purchase is not active. |

**"This week"** means today through today + 7 days, plus all overdue items.

**Unknown vs none:** a missing date is recorded as an *unknown field* on the purchase ("Return deadline: not found, add a date"). This is distinct from "this purchase has no deadline".

**Sorting:** overdue (oldest first), then due today, then upcoming (earliest first). The UI explains this rule.

## 10. Functional requirements

P0 = required for a credible submission. P1 = only after all P0 passes. P2 = future.

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-01 | P0 | **Pasted-text capture** with privacy notice and card redaction | Non-empty text accepted; empty or over-limit input gets an inline message with no provider call; the UI discloses third-party AI processing; card-like numbers are masked and the user is told how many. |
| FR-02 | P0 | **Structured extraction** | The model returns verbatim date text and relative rules, never computed dates. Code parses dates, computes derived dates and verifies evidence. Output is schema-validated, with one controlled retry then a recoverable error. Year-less or ambiguous dates (e.g. 03/04/2026) stay null and flagged. Unverified evidence is flagged. |
| FR-03 | P0 | **Review and confirm** | The user can edit any field and remove deadlines. Flagged items must be fixed or removed before save. Nothing is persisted before the confirm click. Duplicate warning shown. |
| FR-04 | P0 | **Persistent records** (SQLite) | Records survive refresh and restart. The detail view shows fields, deadlines and evidence. The user can delete a record via a confirm dialog. |
| FR-05 | P0 | **Dashboard and briefing** | Summary cards (overdue / due soon / active). Lists show the §9 states with distinct labels. Overdue is never hidden. "Unknown" is distinct from "none". Each deadline shows type, date, days remaining and evidence. A deterministic briefing runs when the Assistant tab opens. |
| FR-06 | P0 | **Conversational assistant over MCP** | Required demo questions work: "What needs my attention this week?", "Can I still return my headphones?", "Show me the details for my laptop.", "Mark the headphones as resolved." Record-dependent questions always call MCP tools. Several matches → the assistant asks which. Answers are 1–3 sentences plus code-rendered evidence cards. A visible tool-activity pane lists calls. The grounding guard blocks unsupported dates. |
| FR-07 | P0 | **Draft next-step message** | Template-based draft for a return or cancellation. Labelled "DRAFT, not sent". Missing details are placeholders. If the window has passed, the draft says so and suggests checking with the seller. It never claims submission. |
| FR-08 | P0 | **MCP server and client over Streamable HTTP** | A separate server process. The app uses the official Python MCP client against the running endpoint. Tests assert the negotiated protocol version is ≥ 2025-11-25. The repo contains the real implementation. Tool tiers per SRD §3.3. |
| FR-09 | P0 | **Status updates** | Set purchase status; mark a deadline completed or dismissed. Invalid values are rejected. Changes persist. Evidence and due dates are never altered by completion. |
| FR-10 | P0 | **Synthetic demo data** | One-click seed and reset, with date-relative sample records (always valid whenever the demo runs). All brands are fictional. Reset touches demo rows only. |
| FR-11 | P0 | **Offline/mock mode** | `LLM_PROVIDER=mock` runs scripted extraction (bundled samples) and scripted intent routing for the four required questions, so the demo and tests work without an API key. A persistent banner says "Offline demo mode, scripted responses, not live AI". The final video uses a live provider. |
| FR-12 | P0 | **Duplicate detection** | Saving the same product, seller and order reference or date returns a warning instead of silently creating a copy. |
| FR-13 | P1 | **Read-aloud button** | Browser speech synthesis (client-side) on assistant replies, for the Alexa-like feel. |
| FR-14 | P1 | **Bedrock provider adapter** | Opt-in via env vars, behind the provider interface. Documented for the AWS Builder challenge. The core demo never requires AWS. |
| FR-15 | P1 | **Friction log and feedback notes** | `FRICTION.md` kept from the start with real entries only. It feeds the Devpost product-feedback form. |
| FR-16 | P1 | **Multi-item selection** | When an email lists several items, the user ticks which to track. (P0 behavior: single item, with a "multiple items detected, choose one" selector.) |
| FR-17 | P1 | **CSV export** | Download purchases and deadlines. |
| FR-18 | P1 | **One-command launcher** | `python -m gracedays.run_all` starts the MCP server, waits for health, then starts Streamlit. |
| FR-19 | P2 | Reminders (email/push) | Not for MVP. Must never be simulated as delivered. |
| FR-20 | P2 | PDF/image extraction, MCP Apps UI, packaged Agent Skill, voice input | Future. |

## 11. UX requirements

- Screens: Dashboard, Add purchase (capture and review), Assistant, Purchase detail (dialog or expander).
- Keep the Capture → Review → Save → Ask → Act flow visible.
- Plain language only. Avoid the terms "MCP" and "LLM" in primary UI copy. The activity pane may say "Tools used".
- Every deadline shows date, type, urgency state, days remaining and evidence.
- States designed for: loading, empty, error (provider and MCP), ambiguous data, unverified evidence, duplicate, success and offline mode.
- Fictional data only. No real retailer names or logos anywhere, including the video.

## 12. Timeline and cut line (solo, IST)

Hard deadline is 00:30 IST on 24 Oct. These blocks leave a buffer and sleep.

| When (IST) | Block | Exit criteria |
|---|---|---|
| Thu 22 Oct 14:15–15:45 | **Spike gate** plus repo setup | `MCPServer` hello tool served over Streamable HTTP and called from a Python `Client`; protocol version printed; a Streamlit button calls it. Repo on GitHub with license, `.gitignore`, `.env.example`, `FRICTION.md`. If the v2 SDK blocks for over 60 min, switch to the v1.28 fallback (SRD §16). |
| 15:45–19:15 | **Backend** | SQLite schema, domain rules (clock, derived state, date engine), all MCP tools, unit tests, in-memory and real-HTTP MCP tests. |
| 19:15–20:00 | Break | |
| 20:00–00:00 | **Extraction** | Provider adapter, mock provider, extraction pipeline with evidence verification, 8 eval fixtures, Capture and Review UI. |
| 00:00–07:00 | Sleep | Skipping this costs more than it saves. |
| Fri 23 Oct 07:00–10:30 | **Dashboard** | Dashboard, detail view, seed/reset, persistence check across restart. |
| 10:30–14:00 | **Assistant** | Orchestrator loop, cards, activity pane, drafts, grounding guard, injection tests, briefing. **Feature freeze at 14:00.** |
| 14:00–14:45 | Break | |
| 14:45–17:00 | **Hardening** | Full test run, clean-clone test with the README, fixes. Optional P1 only if everything above is green. **Code freeze at 17:00.** |
| 17:00–19:30 | **Submission assets** | Record the demo (2–3 takes), upload as public on YouTube or Vimeo, write the description, product feedback and friction log. |
| 19:30–21:30 | **Submit** | Repo public and license visible (or reviewers invited), form complete, verify the links logged out. |
| 21:30–00:30 | Buffer | Do not build here. |

**Cut order if behind:** P1 items → CSV → multi-item selector → read-aloud → fewer evidence-card types. Never cut: evidence verification, the MCP client/server, persistence, the mock mode.

## 13. Demo script (target 2:40)

Use fictional data and no music. Record at the live-provider setting.

| Time | Beat |
|---|---|
| 0:00–0:15 | The problem in one sentence, then the pitch. |
| 0:15–0:50 | Paste a sample order email. Extract. Show the evidence quote under the return deadline. Show an ambiguous date left empty and flagged. Confirm and save. |
| 0:50–1:10 | The dashboard: overdue, due soon and closed states. |
| 1:10–2:05 | Assistant: the briefing; "What needs my attention this week?" with the tool-activity pane showing `list_deadlines`; "Can I still return my headphones?"; "Help me return them" → DRAFT; "Mark the headphones as resolved". |
| 2:05–2:25 | Restart the server and the app. The state persists. |
| 2:25–2:40 | Optional 5-second shot of an MCP inspector listing the tools. Close with "evidence-backed, never invented". |

## 14. Submission checklist (from the official rules and FAQ)

- [ ] Registered; **Alexa+** selected as the primary track; mini-challenges selected deliberately.
- [ ] Code on **GitHub** (non-GitHub hosts are rejected).
- [ ] Public repo: an open-source license file (MIT recommended) visible at the top of the repo page.
- [ ] Or a private repo shared with `knmeiss`, `giolaq`, `anishamalde`, `mosesroth`, `emersonsklar` and the Devpost address listed on the Rules page. Invites expire after 7 days, so invite on submission day.
- [ ] The repo uses MCP at runtime (imported and called, not only named in the README), with setup and run instructions that work from a clean clone.
- [ ] `.env.example` present. No secrets, local DB or real purchase data committed.
- [ ] Demo video: under 3 minutes, English, public on YouTube or Vimeo, shows the project working, no third-party trademarks or copyrighted music.
- [ ] Text description of features and functionality.
- [ ] Product feedback for each tool, API or SDK used: what you used it for, what worked, what needs work, onboarding experience, and "would you build with it again? Yes/No and why".
- [ ] Optional: friction log entries (real only) and feature requests.
- [ ] Open Source and AWS Builder fields filled only if you actually qualify.
- [ ] Submitted before the deadline, with a target of 21:30 IST on 23 Oct.

## 15. Risks

| Risk | Mitigation |
|---|---|
| Time overrun | Cut line and block plan (§12). P1 untouched until P0 is green. |
| MCP SDK v2 API surprises | One-hour spike gate. Documented v1.28 fallback. |
| Wrong date extracted | Code computes dates. Evidence must be a verbatim quote. Ambiguity detection. User review. Eval set. |
| Prompt injection via pasted or stored text | Tool-less extraction. Restricted agent tools. Data delimiting. Injection tests. |
| API quota or key fails mid-demo | Mock mode (labelled). Clear provider errors. Preserve form state. |
| Demo breaks as time passes | Date-relative seed data. `APP_FAKE_TODAY` for recording. |
| Name or trademark conflict | Renamed. Fictional brands. No logos. Check the final name before submission. |
| Local data exposure | Loopback binding. Gitignored DB. Synthetic demo data. |

## 16. Assumptions to confirm on day 0

1. Solo build, one machine, Python 3.12.
2. One AI provider key is available (Gemini, Bedrock or similar). Pick it in hour 0. Provider is configured by env.
3. Streamlit is acceptable as the simulated assistant front end (the FAQ allows any web front end).
4. The final product name is checked before submission.

## 17. References

- Hackathon overview: https://amazonappdev2026.devpost.com/
- Official rules: https://amazonappdev2026.devpost.com/rules
- FAQ (gated Alexa+ tools, web-page-as-MCP-client): https://amazonappdev2026.devpost.com/details/faqs
- MCP specification: https://modelcontextprotocol.io/specification/latest
- MCP Python SDK (v2): https://github.com/modelcontextprotocol/python-sdk and https://py.sdk.modelcontextprotocol.io/
- v1 to v2 migration guide: https://py.sdk.modelcontextprotocol.io/migration/
