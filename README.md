# Escalation Lifecycle Guard

[![CI](https://github.com/jjoseph456/escalation-lifecycle-guard/actions/workflows/test.yml/badge.svg)](https://github.com/jjoseph456/escalation-lifecycle-guard/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A dependency-free Python CLI that checks whether a support escalation still has
a clear path to a customer outcome.

`escalation-lifecycle-guard` complements an intake-quality checker. Intake
quality asks whether engineering received enough evidence. This tool asks what
happens next: Is there a technical owner? Does the customer still have an
active case? Has somebody provided a meaningful update? Does a close state
actually describe an outcome?

All examples are synthetic. This project contains no employer source code,
customer information, ticket data, or internal operational documentation.

![Terminal preview of escalation lifecycle findings](assets/terminal-preview.svg)

## What It Checks

| Rule | Severity | Why it matters |
| --- | --- | --- |
| `OPEN_ENGINEERING_NO_CUSTOMER_PATH` | High | Engineering work remains open after the customer case is closed. |
| `MISSING_TECHNICAL_OWNER` | High | No one is accountable for the next technical action. |
| `OVERDUE_COVERAGE_UPDATE` | High | An OOO handoff has passed its promised customer-update date. |
| `STALE_HUMAN_UPDATE` | Medium | An active escalation has exceeded its update cadence. |
| `CLOSED_ENGINEERING_ACTIVE_CUSTOMER` | Medium | Engineering closed while the customer case is still active. |
| `UNCLEAR_CLOSE_OUTCOME` | Medium | Closure does not identify recovery, accepted workaround, informed limitation, or an explicitly unconfirmed result. |

## Quick Start

Requires Python 3.10 or later and has no runtime dependencies.

```bash
git clone https://github.com/jjoseph456/escalation-lifecycle-guard.git
cd escalation-lifecycle-guard
python -m pip install -e .
python -m escalation_lifecycle_guard examples/cases.json
```

Use JSON output in automation:

```bash
python -m escalation_lifecycle_guard examples/cases.json --format json
```

Set a different cadence threshold:

```bash
python -m escalation_lifecycle_guard examples/cases.json \
  --max-update-age-days 5
```

The command exits with:

| Exit code | Meaning |
| --- | --- |
| `0` | No high-severity lifecycle risks found. |
| `1` | Invalid input or command usage. |
| `2` | One or more high-severity lifecycle risks found. |

## Input Format

The input is a JSON object with a `cases` array. Each case needs a stable ID,
engineering and customer status, owners, timestamps, and a close outcome when
engineering is closed.

```json
{
  "cases": [
    {
      "id": "CASE-100",
      "engineering_status": "open",
      "customer_status": "hold",
      "technical_owner": "runtime-oncall",
      "customer_owner": "support-engineer",
      "opened_at": "2026-09-01T09:00:00Z",
      "last_human_update": "2026-09-10T14:00:00Z",
      "closed_outcome": null
    }
  ]
}
```

Allowed status values are `open` and `closed` for engineering, and `open`,
`pending`, `hold`, and `closed` for a customer case. Allowed close outcomes
are `customer_verified`, `shipped_monitoring`, `workaround_accepted`,
`no_product_change`, and `unconfirmed`.

## OOO Coverage

When an escalation is handed to a coverage owner, add `handoff_at`,
`coverage_owner`, and `next_customer_update`. The guard requires all three
handoff fields together and raises a high-severity finding when the promised
customer update is overdue.

```json
{
  "id": "CASE-103",
  "engineering_status": "open",
  "customer_status": "hold",
  "technical_owner": "platform-oncall",
  "customer_owner": "support-engineer",
  "handoff_at": "2026-09-12T17:00:00Z",
  "coverage_owner": "coverage-engineer",
  "next_customer_update": "2026-09-15T17:00:00Z",
  "opened_at": "2026-09-01T09:00:00Z",
  "last_human_update": "2026-09-12T17:00:00Z",
  "closed_outcome": null
}
```

## Example Output

```text
HIGH    CASE-101  OPEN_ENGINEERING_NO_CUSTOMER_PATH
        Engineering remains open but the customer case is closed.
MEDIUM  CASE-102  UNCLEAR_CLOSE_OUTCOME
        Engineering is closed without a documented customer outcome.

Checked 3 case(s): 1 high, 1 medium, 0 low.
```

## Why It Exists

Support incidents often fail after a good escalation is filed. The technical
investigation continues, but the customer case quietly closes, ownership
becomes unclear, or an engineering close is mistaken for recovery. Those are
workflow risks that can be represented as structured data and checked
consistently.

The project demonstrates:

- Python data validation and command-line design
- Clear operational invariants and actionable failures
- Human-readable and JSON output for automation
- Synthetic examples that separate process design from private case data
- Unit tests for lifecycle and timestamp edge cases

## Development

```bash
python -m unittest discover -s tests -v
```
