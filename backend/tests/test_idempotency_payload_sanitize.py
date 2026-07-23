import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.services.idempotency_s import sanitize_failure_payload


class SanitizeFailurePayloadTests(unittest.TestCase):
    def test_redacts_secret_bearing_keys(self) -> None:
        payload = {
            "access_token": "APP_USR-123",
            "public_status_token": "tok_abc",
            "client_secret": "s3cr3t",
            "password": "hunter2",
            "card_number": "4509953566233704",
            "cvv": "123",
        }
        self.assertEqual(
            sanitize_failure_payload(payload),
            {
                "access_token": "<redacted>",
                "public_status_token": "<redacted>",
                "client_secret": "<redacted>",
                "password": "<redacted>",
                "card_number": "<redacted>",
                "cvv": "<redacted>",
            },
        )

    def test_matches_key_names_case_insensitively(self) -> None:
        self.assertEqual(
            sanitize_failure_payload({"Access-Token": "x", "SECRET": "y"}),
            {"Access-Token": "<redacted>", "SECRET": "<redacted>"},
        )

    def test_preserves_the_fields_the_recovery_path_reads_back(self) -> None:
        # These three are what a 'failed' record must carry for the guest
        # checkout replay to recover; redacting any of them would break it.
        payload = {"detail": "checkout unavailable", "order_id": 7, "payment_id": 11}
        self.assertEqual(sanitize_failure_payload(payload), payload)

    def test_redacts_nested_dicts_and_lists(self) -> None:
        payload = {
            "order": {"id": 1, "public_status_token": "tok"},
            "payments": [
                {"id": 2, "preference_id": "pref-1", "access_token": "leak"},
            ],
        }
        self.assertEqual(
            sanitize_failure_payload(payload),
            {
                "order": {"id": 1, "public_status_token": "<redacted>"},
                "payments": [
                    {"id": 2, "preference_id": "pref-1", "access_token": "<redacted>"},
                ],
            },
        )

    def test_passes_through_scalars_and_empty_containers(self) -> None:
        self.assertEqual(sanitize_failure_payload("plain"), "plain")
        self.assertEqual(sanitize_failure_payload(42), 42)
        self.assertIsNone(sanitize_failure_payload(None))
        self.assertEqual(sanitize_failure_payload({}), {})
        self.assertEqual(sanitize_failure_payload([]), [])

    def test_does_not_mutate_the_input(self) -> None:
        payload = {"access_token": "APP_USR-123", "nested": {"secret": "s"}}
        sanitize_failure_payload(payload)
        self.assertEqual(payload["access_token"], "APP_USR-123")
        self.assertEqual(payload["nested"]["secret"], "s")

    def test_substring_match_is_broad_by_design(self) -> None:
        # 'number' catches phone_number too. That is deliberate over-redaction:
        # failure payloads are diagnostic, so a false positive costs nothing
        # while a miss leaks. Documented here so the behaviour is not a surprise.
        self.assertEqual(
            sanitize_failure_payload({"phone_number": "1122334455"}),
            {"phone_number": "<redacted>"},
        )


if __name__ == "__main__":
    unittest.main()
