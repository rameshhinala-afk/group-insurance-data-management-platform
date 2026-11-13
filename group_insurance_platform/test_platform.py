"""Run with: python -m unittest -v"""
import unittest
from datetime import date, timedelta

from db import get_conn, init_db
from services import InsuranceService, ValidationError


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_conn(":memory:")
        init_db(self.conn)
        self.svc = InsuranceService(self.conn)
        self.plan = self.svc.add_plan("Test", 100000, 500)
        self.group = self.svc.add_group("Acme")
        self.member = self.svc.add_member(self.group, "Jane", "1990-01-01")
        start = (date.today() - timedelta(days=10)).isoformat()
        self.policy = self.svc.create_policy(self.group, self.plan, start)

    def test_duplicate_group_rejected(self):
        with self.assertRaises(ValidationError):
            self.svc.add_group("Acme")

    def test_invalid_member_data(self):
        with self.assertRaises(ValidationError):
            self.svc.add_member(self.group, "X", "2999-01-01")
        with self.assertRaises(ValidationError):
            self.svc.add_member(self.group, "X", "1990-01-01", email="bad")
        with self.assertRaises(ValidationError):
            self.svc.add_member(self.group, "Jane", "1990-01-01")  # duplicate

    def test_premium_due_scales_with_members(self):
        self.assertEqual(self.svc.monthly_premium_due(self.policy), 500)
        self.svc.add_member(self.group, "John", "1989-05-05")
        self.assertEqual(self.svc.monthly_premium_due(self.policy), 1000)

    def test_claim_cannot_exceed_cover(self):
        self.svc.file_claim(self.policy, self.member, 80000)
        with self.assertRaises(ValidationError):
            self.svc.file_claim(self.policy, self.member, 30000)

    def test_rejected_claim_frees_cover(self):
        c = self.svc.file_claim(self.policy, self.member, 80000)
        self.svc.decide_claim(c, False, "invalid")
        self.svc.file_claim(self.policy, self.member, 90000)

    def test_claim_decision_only_once(self):
        c = self.svc.file_claim(self.policy, self.member, 1000)
        self.svc.decide_claim(c, True)
        with self.assertRaises(ValidationError):
            self.svc.decide_claim(c, False)

    def test_member_from_other_group_cannot_claim(self):
        other = self.svc.add_group("Other")
        outsider = self.svc.add_member(other, "Sam", "1991-01-01")
        with self.assertRaises(ValidationError):
            self.svc.file_claim(self.policy, outsider, 1000)

    def test_claim_outside_policy_period(self):
        with self.assertRaises(ValidationError):
            self.svc.file_claim(self.policy, self.member, 1000,
                                claim_date=(date.today() - timedelta(days=400)).isoformat())


if __name__ == "__main__":
    unittest.main()
