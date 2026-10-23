# GraceDays

## Inspiration

After making a purchase, people often have several important dates to remember: return windows, subscription-trial cancellation dates, renewals, and warranty expirations. These details are usually buried in order confirmations and policy emails, making it easy to overlook a deadline and lose money.

GraceDays was inspired by the idea of turning those scattered details into a clear, evidence-backed timeline. The goal is to help people understand what needs attention without requiring access to their inbox or retailer accounts—and without pretending that an action has been completed when it has not.

## What it does

GraceDays is a purchase-deadline assistant that helps users capture and manage the obligations that follow a purchase.

- **Capture purchase details:** Users paste an order confirmation, subscription email, or policy text into the app.
- **Extract and review deadlines:** GraceDays proposes relevant purchase information and dates, then shows the exact source excerpt supporting each deadline.
- **Handle uncertainty transparently:** Ambiguous dates, missing information, and unverified evidence are flagged for review instead of being silently guessed.
- **Track what needs attention:** A dashboard organizes deadlines by urgency, including overdue, due-today, and upcoming items.
- **Ask questions conversationally:** Users can ask what needs attention this week or check details about a saved purchase. Answers about records are grounded in saved data through MCP tool calls.
- **Prepare next steps:** GraceDays can draft a return or subscription-cancellation message using saved information. Drafts are clearly labelled as drafts and are not sent automatically.
- **Keep records persistent:** Confirmed purchase details and deadline statuses are stored locally in SQLite and remain available after a restart.

GraceDays does not connect to inboxes or retailer accounts, and it does not automatically return, refund, cancel, or contact a merchant.

## How we built it

GraceDays uses a Python-first architecture with a Streamlit interface, a separate Model Context Protocol (MCP) server, and a local SQLite database.

- **Frontend:** Streamlit provides the Dashboard, Add Purchase, and Assistant experiences, including review forms, deadline cards, evidence excerpts, and tool-activity details.
- **MCP server and client:** The app communicates with a separate MCP server over Streamable HTTP using the official Python MCP SDK. The client discovers tools and calls them through the MCP interface.
- **Storage:** SQLite stores confirmed purchases and deadlines. Database constraints, transactions, foreign keys, and indexes help keep records consistent.
- **Extraction pipeline:** An AI provider extracts structured fields and returns date text as written in the source, along with any relative rule. Python code validates the output, verifies that evidence excerpts appear in the source, and parses or calculates dates.
- **Date handling:** The date engine handles explicit dates, relative rules, missing anchors, ambiguous numeric dates, and month-end calculations. Unsupported or uncertain dates are sent for user review rather than guessed.
- **Conversational assistant:** An orchestrator exposes an allowlist of MCP tools to the chat model. A grounding guard checks date claims against tool results, and the interface displays evidence cards and tool activity.
- **Offline testing and demos:** A mock provider and date-relative synthetic demo records support repeatable tests and demonstrations without relying on live data.
- **Privacy and safety:** Card-like numbers are redacted before provider calls, only structured fields and short evidence excerpts are retained, and the local MCP server is configured to bind to loopback.

## Challenges we ran into

One of the main challenges was making deadline extraction useful without sacrificing trust. AI can misread dates, infer missing years, or produce an excerpt that does not exactly match the source. GraceDays addresses this by separating extraction from date computation and by verifying evidence in code before a deadline can be treated as supported.

Another challenge was handling relative and ambiguous dates. A rule such as “within 14 days of delivery” requires a known anchor date and a consistent calculation convention. Numeric dates such as `03/04/2026` can also mean different things in different date formats. The date engine flags uncertainty and sends unresolved cases to the review flow.

Integrating the conversational assistant with MCP introduced a separate set of design challenges: keeping the server and client communication reliable, restricting the tools available to the model, and ensuring that answers about saved records actually come from tool results. We also had to distinguish purchase status from deadline status so that completing a deadline would not alter its original date or supporting evidence.

Finally, a time-boxed hackathon required prioritizing a dependable end-to-end flow over features such as inbox integrations, automatic reminders, and external actions.

## Accomplishments that we're proud of

- Designed an end-to-end **Capture → Review → Save → Ask → Act** workflow.
- Made deadline evidence visible so users can understand where each date came from.
- Established a rule that unknown or ambiguous dates remain unknown until reviewed, rather than being fabricated.
- Designed a genuine MCP client/server integration over Streamable HTTP instead of relying only on a simulated tool wrapper.
- Added a grounding approach that checks assistant date claims against retrieved tool results.
- Separated conversational tools from UI-only save/delete actions and admin-only demo-data controls.
- Included persistent local storage, duplicate detection, synthetic demo data, and an offline/mock mode for repeatable testing.
- Kept external actions under the user's control: GraceDays prepares drafts but does not claim to send or submit them.

## What we learned

We learned that a trustworthy AI assistant needs more than a capable language model. Deterministic code, validation, source evidence, clear uncertainty states, and well-defined tool permissions are essential when the result affects a user's decisions.

We also learned to assign the right responsibilities to the right components: the model identifies relevant text and rules, Python resolves dates, SQLite persists confirmed information, and MCP provides a clear interface for retrieving or updating records. Keeping these responsibilities separate makes the system easier to test and reason about.

Another lesson was that transparency is part of the user experience. Showing evidence, explaining missing information, exposing tool activity, and labelling a message as a draft help users understand what the assistant knows and what it has—and has not—done.

## What's next for GraceDays

Future improvements could include:

- Optional browser read-aloud for assistant responses.
- CSV export of purchases and deadlines.
- A one-command launcher for the MCP server and Streamlit app.
- Additional provider support, including an optional Amazon Bedrock adapter.
- Better support for selecting multiple purchases from a single order email.
- Further security hardening, including stronger server-enforced separation between agent, UI, and admin tools.
- Carefully designed reminders or notification integrations, with clear consent and truthful delivery status.
- Broader extraction evaluations and usability testing with more real-world-style synthetic examples.

The priority is to preserve GraceDays' core principle as it grows: **make purchase deadlines easier to manage while keeping every date explainable, every uncertainty visible, and every external action under the user's control.**
