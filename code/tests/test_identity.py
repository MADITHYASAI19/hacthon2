"""Unit tests for code/identity.py."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest
from code.identity import normalize_phone, resolve_identity
from code.loader import load_dataset


class TestIdentity(unittest.TestCase):
    def setUp(self):
        self.ds = load_dataset()

    def test_all_518_requests_resolve(self):
        """Every single one of the 518 evaluation request emails resolves to a user_id."""
        unresolved = []
        for req in self.ds.requests:
            cid = req["case_id"]
            email = req["email"]
            ident = resolve_identity(email, self.ds)
            if not ident or not ident.user_id:
                unresolved.append((cid, email))

        self.assertEqual(unresolved, [], f"Requests failed to resolve identity: {unresolved}")

    def test_historical_email_resolution(self):
        """A user with an email change in audit log resolves both old and new emails."""
        # Find a user with email change
        target_uid = None
        for ar in self.ds.user_audit_log:
            if ar.get("field_name") == "email":
                target_uid = ar["user_id"]
                break

        self.assertIsNotNone(target_uid)
        ident_row = self.ds.user_id_to_identity[target_uid]
        ident = resolve_identity(ident_row["email"], self.ds)
        self.assertIsNotNone(ident)
        self.assertGreaterEqual(len(ident.emails), 2, "Should resolve at least 2 emails for user with audit change")

    def test_no_name_alone_match(self):
        """Similar names alone must not produce a match in matches()."""
        ident = resolve_identity("mateo.rios@gmail.com", self.ds)
        if ident:
            # Different person with similar name
            diff_person = {"name": "Mateo Rios Gil", "email": "other@domain.com"}
            matched = ident.matches(diff_person)
            self.assertEqual(matched, [], "Should not match on name alone")

    def test_case_insensitive_matching(self):
        """Matches finds uppercase/mixed case email variants."""
        req = self.ds.requests[0]
        ident = resolve_identity(req["email"], self.ds)
        self.assertIsNotNone(ident)
        res = ident.matches({"email": req["email"].upper()})
        self.assertTrue(any(t == "email" for t, v in res), "Should match uppercase email")


if __name__ == "__main__":
    unittest.main()
