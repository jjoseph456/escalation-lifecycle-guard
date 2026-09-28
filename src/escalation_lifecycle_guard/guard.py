"""Validation rules for a support escalation's customer-outcome lifecycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

ENGINEERING_STATUSES = {"open", "closed"}
CUSTOMER_STATUSES = {"open", "pending", "hold", "closed"}
CLOSE_OUTCOMES = {
    "customer_verified",
    "shipped_monitoring",
    "workaround_accepted",
    "no_product_change",
    "unconfirmed",
}
ACTIVE_CUSTOMER_STATUSES = {"open", "pending", "hold"}
SEVERITIES = {"sev1", "sev2", "sev3"}
RESPONSE_TARGET_BUSINESS_DAYS = {"sev1": 1, "sev2": 1, "sev3": 5}
CLOSURE_TRIGGERS = {
    "customer_confirmed",
    "engineering_decision",
    "inactivity_auto_close",
}
RECOVERY_OUTCOMES = {"customer_verified", "workaround_accepted"}


@dataclass(frozen=True)
class Finding:
    case_id: str
    severity: str
    rule: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def parse_timestamp(value: Any, field: str, case_id: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{case_id}: {field} must be an ISO 8601 timestamp.")

    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"{case_id}: {field} must be an ISO 8601 timestamp."
        ) from error

    if timestamp.tzinfo is None:
        raise ValueError(f"{case_id}: {field} must include a timezone.")

    return timestamp.astimezone(timezone.utc)


def business_days_between(start: datetime, end: datetime) -> int:
    """Count whole Monday-Friday days elapsed after ``start`` up to ``end``."""
    if end <= start:
        return 0
    days = 0
    cursor = start
    while True:
        cursor += timedelta(days=1)
        if cursor > end:
            return days
        if cursor.weekday() < 5:
            days += 1


def require_string(case: dict[str, Any], field: str, case_id: str) -> str:
    value = case.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{case_id}: {field} is required.")
    return value.strip()


def validate_case_shape(case: Any) -> dict[str, Any]:
    if not isinstance(case, dict):
        raise ValueError("Each case must be a JSON object.")

    case_id = require_string(case, "id", "case")
    engineering_status = require_string(case, "engineering_status", case_id)
    customer_status = require_string(case, "customer_status", case_id)

    if engineering_status not in ENGINEERING_STATUSES:
        raise ValueError(
            f"{case_id}: engineering_status must be one of "
            f"{sorted(ENGINEERING_STATUSES)}."
        )
    if customer_status not in CUSTOMER_STATUSES:
        raise ValueError(
            f"{case_id}: customer_status must be one of "
            f"{sorted(CUSTOMER_STATUSES)}."
        )

    parse_timestamp(case.get("opened_at"), "opened_at", case_id)
    parse_timestamp(case.get("last_human_update"), "last_human_update", case_id)

    handoff_at = case.get("handoff_at")
    next_customer_update = case.get("next_customer_update")
    if handoff_at is not None:
        parse_timestamp(handoff_at, "handoff_at", case_id)
        require_string(case, "coverage_owner", case_id)
        parse_timestamp(
            next_customer_update, "next_customer_update", case_id
        )
    elif next_customer_update is not None:
        raise ValueError(
            f"{case_id}: next_customer_update requires handoff_at."
        )

    closed_outcome = case.get("closed_outcome")
    if closed_outcome is not None and closed_outcome not in CLOSE_OUTCOMES:
        raise ValueError(
            f"{case_id}: closed_outcome must be null or one of "
            f"{sorted(CLOSE_OUTCOMES)}."
        )

    severity = case.get("severity")
    if severity is not None and severity not in SEVERITIES:
        raise ValueError(
            f"{case_id}: severity must be null or one of {sorted(SEVERITIES)}."
        )

    for field in ("first_engineering_response", "reopened_at", "last_disposition_at"):
        if case.get(field) is not None:
            parse_timestamp(case[field], field, case_id)

    closure_trigger = case.get("closure_trigger")
    if closure_trigger is not None and closure_trigger not in CLOSURE_TRIGGERS:
        raise ValueError(
            f"{case_id}: closure_trigger must be null or one of "
            f"{sorted(CLOSURE_TRIGGERS)}."
        )

    assigned = case.get("assigned_before_close")
    if assigned is not None and not isinstance(assigned, bool):
        raise ValueError(f"{case_id}: assigned_before_close must be a boolean.")

    return case


def validate_cases(
    cases: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    max_update_age_days: int = 7,
) -> list[Finding]:
    if max_update_age_days < 1:
        raise ValueError("max_update_age_days must be at least 1.")

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    findings: list[Finding] = []

    for raw_case in cases:
        case = validate_case_shape(raw_case)
        case_id = case["id"].strip()
        engineering_status = case["engineering_status"].strip()
        customer_status = case["customer_status"].strip()
        last_update = parse_timestamp(
            case["last_human_update"], "last_human_update", case_id
        )
        technical_owner = str(case.get("technical_owner") or "").strip()
        customer_owner = str(case.get("customer_owner") or "").strip()
        handoff_at = case.get("handoff_at")
        closed_outcome = case.get("closed_outcome")

        if engineering_status == "open" and customer_status == "closed":
            findings.append(
                Finding(
                    case_id,
                    "high",
                    "OPEN_ENGINEERING_NO_CUSTOMER_PATH",
                    "Engineering remains open but the customer case is closed.",
                )
            )

        if engineering_status == "open" and not technical_owner:
            findings.append(
                Finding(
                    case_id,
                    "high",
                    "MISSING_TECHNICAL_OWNER",
                    "An open escalation has no technical owner.",
                )
            )

        if engineering_status == "open" and not customer_owner:
            findings.append(
                Finding(
                    case_id,
                    "medium",
                    "MISSING_CUSTOMER_OWNER",
                    "An open escalation has no customer-impact owner.",
                )
            )

        if handoff_at is not None:
            next_customer_update = parse_timestamp(
                case["next_customer_update"], "next_customer_update", case_id
            )
            if next_customer_update < current_time:
                findings.append(
                    Finding(
                        case_id,
                        "high",
                        "OVERDUE_COVERAGE_UPDATE",
                        "The handoff coverage update is overdue.",
                    )
                )

        if engineering_status == "open":
            update_age = current_time - last_update
            if update_age.days >= max_update_age_days:
                findings.append(
                    Finding(
                        case_id,
                        "medium",
                        "STALE_HUMAN_UPDATE",
                        "The latest human update exceeds the configured cadence.",
                    )
                )

        if (
            engineering_status == "closed"
            and customer_status in ACTIVE_CUSTOMER_STATUSES
        ):
            findings.append(
                Finding(
                    case_id,
                    "medium",
                    "CLOSED_ENGINEERING_ACTIVE_CUSTOMER",
                    "Engineering is closed while the customer case remains active.",
                )
            )

        if engineering_status == "closed" and (
            closed_outcome is None or closed_outcome == "unconfirmed"
        ):
            findings.append(
                Finding(
                    case_id,
                    "medium",
                    "UNCLEAR_CLOSE_OUTCOME",
                    "Engineering is closed without a confirmed customer outcome.",
                )
            )

        opened_at = parse_timestamp(case["opened_at"], "opened_at", case_id)
        severity = case.get("severity")
        if (
            engineering_status == "open"
            and severity in RESPONSE_TARGET_BUSINESS_DAYS
            and case.get("first_engineering_response") is None
            and business_days_between(opened_at, current_time)
            > RESPONSE_TARGET_BUSINESS_DAYS[severity]
        ):
            findings.append(
                Finding(
                    case_id,
                    "high" if severity in {"sev1", "sev2"} else "medium",
                    "MISSED_ENGINEERING_RESPONSE",
                    f"No engineering response within the {severity} target of "
                    f"{RESPONSE_TARGET_BUSINESS_DAYS[severity]} business day(s).",
                )
            )

        if (
            engineering_status == "closed"
            and case.get("closure_trigger") == "inactivity_auto_close"
            and closed_outcome in RECOVERY_OUTCOMES
        ):
            findings.append(
                Finding(
                    case_id,
                    "high",
                    "SILENCE_COUNTED_AS_RECOVERY",
                    "An inactivity auto-close is recorded as a customer recovery outcome.",
                )
            )

        if engineering_status == "closed" and case.get("assigned_before_close") is False:
            findings.append(
                Finding(
                    case_id,
                    "medium",
                    "CLOSED_WITHOUT_ASSIGNMENT",
                    "The escalation closed without ever having an assigned engineer.",
                )
            )

        reopened_raw = case.get("reopened_at")
        if engineering_status == "open" and reopened_raw is not None:
            reopened_at = parse_timestamp(reopened_raw, "reopened_at", case_id)
            disposition_raw = case.get("last_disposition_at")
            disposition_at = (
                parse_timestamp(disposition_raw, "last_disposition_at", case_id)
                if disposition_raw is not None
                else None
            )
            if (
                (disposition_at is None or disposition_at < reopened_at)
                and business_days_between(reopened_at, current_time) >= 1
            ):
                findings.append(
                    Finding(
                        case_id,
                        "high",
                        "REOPEN_WITHOUT_REDISPOSITION",
                        "A reopened escalation has no new technical disposition "
                        "after one business day.",
                    )
                )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(findings, key=lambda finding: (severity_order[finding.severity], finding.case_id))
