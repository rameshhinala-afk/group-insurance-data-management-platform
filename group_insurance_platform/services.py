"""Business logic: validation, member/policy/claim management, audit trail."""
import csv
import re
import sqlite3
from datetime import date, datetime

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RELATIONS = {"self", "spouse", "child", "parent"}
MAX_AGE = 80


class ValidationError(Exception):
    """Raised when input data or a business rule is violated."""


def parse_date(value: str, field: str = "date") -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be in YYYY-MM-DD format, got {value!r}")


def add_months(d: date, months: int) -> date:
    """Return d + months, minus one day (so a 12-month policy ends the day before its anniversary)."""
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day).fromordinal(date(year, month, day).toordinal() - 1)


class InsuranceService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ------------------------------------------------------------- helpers
    def _audit(self, action, entity, entity_id, details=""):
        self.conn.execute(
            "INSERT INTO audit_log(action, entity, entity_id, details, created_at) VALUES (?,?,?,?,?)",
            (action, entity, entity_id, details, datetime.now().isoformat(timespec="seconds")))

    def _one(self, sql, params, what):
        row = self.conn.execute(sql, params).fetchone()
        if row is None:
            raise ValidationError(f"{what} not found")
        return row

    # --------------------------------------------------------------- groups
    def add_group(self, name, industry=None, contact_email=None) -> int:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Group name is required")
        if contact_email and not EMAIL_RE.match(contact_email):
            raise ValidationError(f"Invalid contact email: {contact_email}")
        try:
            cur = self.conn.execute(
                "INSERT INTO groups(name, industry, contact_email, created_at) VALUES (?,?,?,?)",
                (name, industry, contact_email, date.today().isoformat()))
        except sqlite3.IntegrityError:
            raise ValidationError(f"Group '{name}' already exists")
        self._audit("create", "group", cur.lastrowid, name)
        self.conn.commit()
        return cur.lastrowid

    def add_plan(self, name, sum_insured, monthly_premium_per_member) -> int:
        if sum_insured <= 0 or monthly_premium_per_member <= 0:
            raise ValidationError("Sum insured and premium must be positive")
        try:
            cur = self.conn.execute(
                "INSERT INTO plans(name, sum_insured, monthly_premium_per_member) VALUES (?,?,?)",
                (name, sum_insured, monthly_premium_per_member))
        except sqlite3.IntegrityError:
            raise ValidationError(f"Plan '{name}' already exists")
        self._audit("create", "plan", cur.lastrowid, name)
        self.conn.commit()
        return cur.lastrowid

    # -------------------------------------------------------------- members
    def add_member(self, group_id, name, dob, relation="self", email=None) -> int:
        self._one("SELECT 1 FROM groups WHERE group_id=?", (group_id,), f"Group {group_id}")
        name = (name or "").strip()
        if not name:
            raise ValidationError("Member name is required")
        born = parse_date(dob, "dob")
        age = (date.today() - born).days // 365
        if born > date.today() or age > MAX_AGE:
            raise ValidationError(f"Date of birth {dob} gives an invalid age ({age})")
        relation = (relation or "self").lower()
        if relation not in RELATIONS:
            raise ValidationError(f"Relation must be one of {sorted(RELATIONS)}")
        if email and not EMAIL_RE.match(email):
            raise ValidationError(f"Invalid email: {email}")
        try:
            cur = self.conn.execute(
                "INSERT INTO members(group_id, name, dob, relation, email) VALUES (?,?,?,?,?)",
                (group_id, name, dob, relation, email))
        except sqlite3.IntegrityError:
            raise ValidationError(f"Duplicate member: {name} ({dob}) already in group {group_id}")
        self._audit("create", "member", cur.lastrowid, name)
        self.conn.commit()
        return cur.lastrowid

    def deactivate_member(self, member_id):
        self._one("SELECT 1 FROM members WHERE member_id=?", (member_id,), f"Member {member_id}")
        self.conn.execute("UPDATE members SET status='inactive' WHERE member_id=?", (member_id,))
        self._audit("deactivate", "member", member_id)
        self.conn.commit()

    def import_members_csv(self, group_id, path):
        """CSV columns: name,dob,relation,email. Returns (added_count, [error messages])."""
        added, errors = 0, []
        with open(path, newline="", encoding="utf-8") as f:
            for line_no, row in enumerate(csv.DictReader(f), start=2):
                try:
                    self.add_member(group_id, row.get("name"), row.get("dob"),
                                    row.get("relation") or "self", row.get("email") or None)
                    added += 1
                except ValidationError as e:
                    errors.append(f"line {line_no}: {e}")
        return added, errors

    # ------------------------------------------------------------- policies
    def create_policy(self, group_id, plan_id, start_date, months=12) -> int:
        self._one("SELECT 1 FROM groups WHERE group_id=?", (group_id,), f"Group {group_id}")
        self._one("SELECT 1 FROM plans WHERE plan_id=?", (plan_id,), f"Plan {plan_id}")
        if months <= 0:
            raise ValidationError("Policy term must be at least 1 month")
        start = parse_date(start_date, "start_date")
        end = add_months(start, months)
        cur = self.conn.execute(
            "INSERT INTO policies(group_id, plan_id, start_date, end_date) VALUES (?,?,?,?)",
            (group_id, plan_id, start.isoformat(), end.isoformat()))
        self._audit("create", "policy", cur.lastrowid, f"{start} to {end}")
        self.conn.commit()
        return cur.lastrowid

    def monthly_premium_due(self, policy_id) -> float:
        row = self._one(
            """SELECT pl.monthly_premium_per_member AS rate,
                      (SELECT COUNT(*) FROM members m WHERE m.group_id = p.group_id AND m.status='active') AS n
               FROM policies p JOIN plans pl USING(plan_id) WHERE p.policy_id=?""",
            (policy_id,), f"Policy {policy_id}")
        return round(row["rate"] * row["n"], 2)

    def record_premium(self, policy_id, amount, paid_date=None) -> int:
        self._one("SELECT 1 FROM policies WHERE policy_id=?", (policy_id,), f"Policy {policy_id}")
        if amount <= 0:
            raise ValidationError("Premium amount must be positive")
        paid = parse_date(paid_date, "paid_date") if paid_date else date.today()
        cur = self.conn.execute(
            "INSERT INTO premiums(policy_id, amount, paid_date) VALUES (?,?,?)",
            (policy_id, amount, paid.isoformat()))
        self._audit("payment", "premium", cur.lastrowid, f"policy {policy_id}: {amount}")
        self.conn.commit()
        return cur.lastrowid

    # --------------------------------------------------------------- claims
    def remaining_cover(self, policy_id, member_id) -> float:
        row = self._one(
            """SELECT pl.sum_insured AS si FROM policies p JOIN plans pl USING(plan_id)
               WHERE p.policy_id=?""", (policy_id,), f"Policy {policy_id}")
        used = self.conn.execute(
            """SELECT COALESCE(SUM(amount),0) FROM claims
               WHERE policy_id=? AND member_id=? AND status IN ('approved','pending')""",
            (policy_id, member_id)).fetchone()[0]
        return row["si"] - used

    def file_claim(self, policy_id, member_id, amount, description="", claim_date=None) -> int:
        policy = self._one("SELECT * FROM policies WHERE policy_id=?", (policy_id,), f"Policy {policy_id}")
        member = self._one("SELECT * FROM members WHERE member_id=?", (member_id,), f"Member {member_id}")
        if policy["status"] != "active":
            raise ValidationError(f"Policy {policy_id} is {policy['status']}")
        if member["group_id"] != policy["group_id"]:
            raise ValidationError("Member does not belong to the policy's group")
        if member["status"] != "active":
            raise ValidationError("Member is inactive")
        if amount <= 0:
            raise ValidationError("Claim amount must be positive")
        cdate = parse_date(claim_date, "claim_date") if claim_date else date.today()
        if not (parse_date(policy["start_date"]) <= cdate <= parse_date(policy["end_date"])):
            raise ValidationError("Claim date is outside the policy period")
        remaining = self.remaining_cover(policy_id, member_id)
        if amount > remaining:
            raise ValidationError(f"Claim {amount:,.2f} exceeds remaining cover {remaining:,.2f}")
        cur = self.conn.execute(
            "INSERT INTO claims(policy_id, member_id, amount, claim_date, description) VALUES (?,?,?,?,?)",
            (policy_id, member_id, amount, cdate.isoformat(), description))
        self._audit("create", "claim", cur.lastrowid, f"{amount}")
        self.conn.commit()
        return cur.lastrowid

    def decide_claim(self, claim_id, approve: bool, note=""):
        claim = self._one("SELECT * FROM claims WHERE claim_id=?", (claim_id,), f"Claim {claim_id}")
        if claim["status"] != "pending":
            raise ValidationError(f"Claim {claim_id} is already {claim['status']}")
        status = "approved" if approve else "rejected"
        self.conn.execute("UPDATE claims SET status=?, decision_note=? WHERE claim_id=?",
                          (status, note, claim_id))
        self._audit(status, "claim", claim_id, note)
        self.conn.commit()

    def expire_policies(self) -> int:
        """Mark policies past their end date as expired. Returns number updated."""
        cur = self.conn.execute(
            "UPDATE policies SET status='expired' WHERE status='active' AND end_date < ?",
            (date.today().isoformat(),))
        if cur.rowcount:
            self._audit("expire", "policy", None, f"{cur.rowcount} policies")
        self.conn.commit()
        return cur.rowcount
