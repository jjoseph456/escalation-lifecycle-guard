import unittest
from datetime import datetime, timezone

from escalation_lifecycle_guard.cli import main
from escalation_lifecycle_guard.guard import validate_cases


NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


def case(**overrides):
    value = {
        "id": "CASE-1",
        "engineering_status": "open",
        "customer_status": "hold",
        "technical_owner": "runtime",
        "customer_owner": "support",
        "opened_at": "2026-09-01T09:00:00Z",
        "last_human_update": "2026-09-12T09:00:00Z",
        "closed_outcome": None,
    }
    value.update(overrides)
    return value


class LifecycleGuardTests(unittest.TestCase):
    def test_open_engineering_with_closed_customer_is_high_risk(self):
        findings = validate_cases(
            [case(customer_status="closed")], now=NOW
        )
        self.assertEqual(
            ["OPEN_ENGINEERING_NO_CUSTOMER_PATH"],
            [finding.rule for finding in findings],
        )
        self.assertEqual("high", findings[0].severity)

    def test_missing_technical_owner_is_high_risk(self):
        findings = validate_cases([case(technical_owner="")], now=NOW)
        self.assertEqual("MISSING_TECHNICAL_OWNER", findings[0].rule)

    def test_stale_update_is_reported_at_configured_cadence(self):
        findings = validate_cases(
            [case(last_human_update="2026-09-06T09:00:00Z")],
            now=NOW,
            max_update_age_days=7,
        )
        self.assertEqual(["STALE_HUMAN_UPDATE"], [finding.rule for finding in findings])

    def test_closed_engineering_with_active_customer_is_reported(self):
        findings = validate_cases(
            [
                case(
                    engineering_status="closed",
                    customer_status="open",
                    closed_outcome="unconfirmed",
                )
            ],
            now=NOW,
        )
        self.assertEqual(
            ["CLOSED_ENGINEERING_ACTIVE_CUSTOMER", "UNCLEAR_CLOSE_OUTCOME"],
            [finding.rule for finding in findings],
        )

    def test_timezone_is_required(self):
        with self.assertRaisesRegex(ValueError, "must include a timezone"):
            validate_cases(
                [case(last_human_update="2026-09-12T09:00:00")],
                now=NOW,
            )

    def test_handoff_requires_a_coverage_owner(self):
        with self.assertRaisesRegex(ValueError, "coverage_owner is required"):
            validate_cases(
                [
                    case(
                        handoff_at="2026-09-12T09:00:00Z",
                        next_customer_update="2026-09-15T09:00:00Z",
                    )
                ],
                now=NOW,
            )

    def test_overdue_handoff_update_is_high_risk(self):
        findings = validate_cases(
            [
                case(
                    handoff_at="2026-09-01T09:00:00Z",
                    coverage_owner="coverage",
                    next_customer_update="2026-09-13T09:00:00Z",
                )
            ],
            now=NOW,
        )
        self.assertEqual(["OVERDUE_COVERAGE_UPDATE"], [finding.rule for finding in findings])
        self.assertEqual("high", findings[0].severity)

    def test_cli_returns_two_for_high_findings(self):
        self.assertEqual(2, main(["examples/cases.json"]))


class OutcomeControlTests(unittest.TestCase):
    # NOW is Monday 2026-09-14 12:00 UTC.
    def test_sev2_without_response_after_one_business_day_is_high_risk(self):
        findings = validate_cases(
            [case(severity="sev2", opened_at="2026-09-10T09:00:00Z")], now=NOW
        )
        self.assertEqual(["MISSED_ENGINEERING_RESPONSE"], [f.rule for f in findings])
        self.assertEqual("high", findings[0].severity)

    def test_weekend_does_not_count_toward_response_target(self):
        findings = validate_cases(
            [case(severity="sev2", opened_at="2026-09-11T15:00:00Z")], now=NOW
        )
        self.assertEqual([], findings)

    def test_sev2_with_engineering_response_passes(self):
        findings = validate_cases(
            [
                case(
                    severity="sev2",
                    opened_at="2026-09-10T09:00:00Z",
                    first_engineering_response="2026-09-10T15:00:00Z",
                )
            ],
            now=NOW,
        )
        self.assertEqual([], findings)

    def test_sev3_missed_response_is_medium(self):
        findings = validate_cases(
            [case(severity="sev3", opened_at="2026-09-01T09:00:00Z")], now=NOW
        )
        self.assertEqual(["MISSED_ENGINEERING_RESPONSE"], [f.rule for f in findings])
        self.assertEqual("medium", findings[0].severity)

    def test_inactivity_close_recorded_as_recovery_is_high_risk(self):
        findings = validate_cases(
            [
                case(
                    engineering_status="closed",
                    customer_status="closed",
                    closed_outcome="customer_verified",
                    closure_trigger="inactivity_auto_close",
                )
            ],
            now=NOW,
        )
        self.assertEqual(["SILENCE_COUNTED_AS_RECOVERY"], [f.rule for f in findings])

    def test_inactivity_close_recorded_as_unconfirmed_is_not_silence_as_recovery(self):
        findings = validate_cases(
            [
                case(
                    engineering_status="closed",
                    customer_status="closed",
                    closed_outcome="unconfirmed",
                    closure_trigger="inactivity_auto_close",
                )
            ],
            now=NOW,
        )
        self.assertEqual(["UNCLEAR_CLOSE_OUTCOME"], [f.rule for f in findings])

    def test_closed_without_assignment_is_reported(self):
        findings = validate_cases(
            [
                case(
                    engineering_status="closed",
                    customer_status="closed",
                    closed_outcome="customer_verified",
                    closure_trigger="customer_confirmed",
                    assigned_before_close=False,
                )
            ],
            now=NOW,
        )
        self.assertEqual(["CLOSED_WITHOUT_ASSIGNMENT"], [f.rule for f in findings])

    def test_reopen_without_new_disposition_is_high_risk(self):
        findings = validate_cases(
            [
                case(
                    reopened_at="2026-09-10T09:00:00Z",
                    last_disposition_at="2026-09-05T09:00:00Z",
                )
            ],
            now=NOW,
        )
        self.assertEqual(["REOPEN_WITHOUT_REDISPOSITION"], [f.rule for f in findings])

    def test_reopen_with_new_disposition_passes(self):
        findings = validate_cases(
            [
                case(
                    reopened_at="2026-09-10T09:00:00Z",
                    last_disposition_at="2026-09-11T09:00:00Z",
                )
            ],
            now=NOW,
        )
        self.assertEqual([], findings)

    def test_invalid_closure_trigger_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "closure_trigger must be"):
            validate_cases([case(closure_trigger="silence")], now=NOW)
