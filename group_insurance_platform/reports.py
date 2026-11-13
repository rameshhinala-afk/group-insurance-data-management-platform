"""Read-only reporting queries. Each returns a list of dict rows."""
from datetime import date, timedelta


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def group_summary(conn):
    return _rows(conn, """
        SELECT g.group_id, g.name, g.industry,
               (SELECT COUNT(*) FROM members m WHERE m.group_id=g.group_id AND m.status='active') AS active_members,
               (SELECT COUNT(*) FROM policies p WHERE p.group_id=g.group_id AND p.status='active') AS active_policies
        FROM groups g ORDER BY g.group_id""")


def loss_ratio(conn):
    """Approved claims / premiums collected, per group."""
    return _rows(conn, """
        SELECT g.name AS group_name,
               ROUND(COALESCE((SELECT SUM(pr.amount) FROM premiums pr JOIN policies p USING(policy_id)
                               WHERE p.group_id=g.group_id),0),2) AS premiums_paid,
               ROUND(COALESCE((SELECT SUM(c.amount) FROM claims c JOIN policies p USING(policy_id)
                               WHERE p.group_id=g.group_id AND c.status='approved'),0),2) AS claims_approved,
               CASE WHEN COALESCE((SELECT SUM(pr.amount) FROM premiums pr JOIN policies p USING(policy_id)
                                   WHERE p.group_id=g.group_id),0) = 0 THEN NULL
                    ELSE ROUND(100.0 * COALESCE((SELECT SUM(c.amount) FROM claims c JOIN policies p USING(policy_id)
                               WHERE p.group_id=g.group_id AND c.status='approved'),0)
                         / (SELECT SUM(pr.amount) FROM premiums pr JOIN policies p USING(policy_id)
                            WHERE p.group_id=g.group_id), 1) END AS loss_ratio_pct
        FROM groups g ORDER BY g.group_id""")


def claims_by_status(conn):
    return _rows(conn, """
        SELECT status, COUNT(*) AS claims, ROUND(SUM(amount),2) AS total_amount
        FROM claims GROUP BY status ORDER BY status""")


def expiring_policies(conn, days=60):
    today = date.today()
    return _rows(conn, """
        SELECT p.policy_id, g.name AS group_name, p.end_date
        FROM policies p JOIN groups g USING(group_id)
        WHERE p.status='active' AND p.end_date BETWEEN ? AND ?
        ORDER BY p.end_date""", (today.isoformat(), (today + timedelta(days=days)).isoformat()))


def data_quality_issues(conn):
    """Simple data-quality checks a data-management team would run regularly."""
    issues = []
    for r in _rows(conn, "SELECT member_id, name FROM members WHERE email IS NULL AND status='active'"):
        issues.append(f"Member {r['member_id']} ({r['name']}) has no email")
    for r in _rows(conn, """SELECT g.name FROM groups g
                            WHERE NOT EXISTS (SELECT 1 FROM policies p WHERE p.group_id=g.group_id)"""):
        issues.append(f"Group '{r['name']}' has no policy")
    for r in _rows(conn, """SELECT p.policy_id FROM policies p
                            WHERE p.status='active' AND NOT EXISTS
                                  (SELECT 1 FROM premiums pr WHERE pr.policy_id=p.policy_id)"""):
        issues.append(f"Policy {r['policy_id']} has no premium payments")
    return issues


def format_table(rows, title=""):
    if not rows:
        return f"{title}\n  (no data)\n" if title else "  (no data)\n"
    cols = list(rows[0].keys())
    widths = [max(len(c), *(len(str(r[c])) for r in rows)) for c in cols]
    line = "  " + " | ".join(c.ljust(w) for c, w in zip(cols, widths))
    sep = "  " + "-+-".join("-" * w for w in widths)
    body = "\n".join("  " + " | ".join(str(r[c]).ljust(w) for c, w in zip(cols, widths)) for r in rows)
    head = f"{title}\n" if title else ""
    return f"{head}{line}\n{sep}\n{body}\n"
