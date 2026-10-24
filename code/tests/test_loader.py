"""Unit tests for code/loader.py."""
import sys
from pathlib import Path

# Add project root to sys.path so 'code' package can be imported
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest
from code.loader import load_dataset, normalize_email, parse_ts


class TestLoader(unittest.TestCase):
    def setUp(self):
        self.ds = load_dataset()

    def test_row_counts(self):
        self.assertEqual(len(self.ds.requests), 518, "Should have 518 evaluation requests")
        self.assertEqual(len(self.ds.sample_requests), 32, "Should have 32 sample requests")
        self.assertEqual(len(self.ds.user_identities), 850, "Should have 850 user identities")
        self.assertEqual(len(self.ds.user_audit_log), 306, "Should have 306 audit rows")
        self.assertEqual(len(self.ds.system_activity), 4011, "Should have 4011 activity rows")
        self.assertEqual(len(self.ds.deletion_rules), 15, "Should have 15 deletion rules")
        self.assertEqual(len(self.ds.evidence_files), 94, "Should have 94 evidence files")

    def test_email_resolution(self):
        """Every request email should be resolved either in user_identities or user_audit_log."""
        audit_emails = set()
        for r in self.ds.user_audit_log:
            if r.get("field_name") == "email":
                old_val = normalize_email(r.get("old_value"))
                new_val = normalize_email(r.get("new_value"))
                if old_val:
                    audit_emails.add(old_val)
                if new_val:
                    audit_emails.add(new_val)

        missing = []
        for req in self.ds.requests:
            case_id = req.get("case_id")
            email = normalize_email(req.get("email"))
            if email not in self.ds.email_to_user and email not in audit_emails:
                missing.append((case_id, email))

        self.assertEqual(missing, [], f"Requests with unresolvable emails: {missing}")

    def test_normalize_email(self):
        self.assertEqual(normalize_email("  Alice@Example.COM "), "alice@example.com")
        self.assertEqual(normalize_email(""), "")
        self.assertEqual(normalize_email(None), "")

    def test_parse_ts(self):
        ts = parse_ts("2026-08-15T12:30:00Z")
        self.assertIsNotNone(ts)
        self.assertEqual(ts.year, 2026)
        self.assertEqual(ts.month, 8)
        self.assertEqual(ts.day, 15)
        self.assertEqual(ts.hour, 12)
        self.assertIsNone(parse_ts(""))
        self.assertIsNone(parse_ts(None))


if __name__ == "__main__":
    unittest.main()
