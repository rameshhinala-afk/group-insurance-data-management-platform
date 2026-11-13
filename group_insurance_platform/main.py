"""Command-line interface for the Group Insurance Data Management Platform.

Examples:
  python main.py demo                       # create DB with sample data and show reports
  python main.py init
  python main.py add-group "Acme Ltd" --industry Retail --email hr@acme.example
  python main.py add-member 1 "Jane Doe" 1991-05-20 --relation self --email jane@acme.example
  python main.py import-members 1 sample_members.csv
  python main.py create-policy 1 1 2026-11-01 --months 12
  python main.py pay-premium 1 5000
  python main.py file-claim 1 1 25000 --desc "Dental surgery"
  python main.py decide-claim 1 approve --note "Verified"
  python main.py report
"""
import argparse
import os
import sys

import reports
from db import DB_PATH, get_conn, init_db
from seed import seed
from services import InsuranceService, ValidationError


def show_reports(conn):
    print(reports.format_table(reports.group_summary(conn), "GROUP SUMMARY"))
    print(reports.format_table(reports.loss_ratio(conn), "LOSS RATIO (approved claims / premiums paid)"))
    print(reports.format_table(reports.claims_by_status(conn), "CLAIMS BY STATUS"))
    print(reports.format_table(reports.expiring_policies(conn, 60), "POLICIES EXPIRING IN 60 DAYS"))
    issues = reports.data_quality_issues(conn)
    print("DATA QUALITY ISSUES")
    print("\n".join(f"  - {i}" for i in issues) if issues else "  none")


def build_parser():
    p = argparse.ArgumentParser(description="Group Insurance Data Management Platform")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create empty database")
    sub.add_parser("demo", help="reset database, load sample data, show reports")
    sub.add_parser("report", help="show all reports")
    sub.add_parser("expire-policies", help="mark overdue policies as expired")

    g = sub.add_parser("add-group")
    g.add_argument("name"); g.add_argument("--industry"); g.add_argument("--email")

    pl = sub.add_parser("add-plan")
    pl.add_argument("name"); pl.add_argument("sum_insured", type=float)
    pl.add_argument("monthly_premium", type=float)

    m = sub.add_parser("add-member")
    m.add_argument("group_id", type=int); m.add_argument("name"); m.add_argument("dob")
    m.add_argument("--relation", default="self"); m.add_argument("--email")

    im = sub.add_parser("import-members", help="bulk import from CSV (name,dob,relation,email)")
    im.add_argument("group_id", type=int); im.add_argument("csv_path")

    lm = sub.add_parser("list-members")
    lm.add_argument("group_id", type=int)

    cp = sub.add_parser("create-policy")
    cp.add_argument("group_id", type=int); cp.add_argument("plan_id", type=int)
    cp.add_argument("start_date"); cp.add_argument("--months", type=int, default=12)

    pp = sub.add_parser("pay-premium")
    pp.add_argument("policy_id", type=int); pp.add_argument("amount", type=float)

    fc = sub.add_parser("file-claim")
    fc.add_argument("policy_id", type=int); fc.add_argument("member_id", type=int)
    fc.add_argument("amount", type=float); fc.add_argument("--desc", default="")
    fc.add_argument("--date")

    dc = sub.add_parser("decide-claim")
    dc.add_argument("claim_id", type=int); dc.add_argument("decision", choices=["approve", "reject"])
    dc.add_argument("--note", default="")

    sub.add_parser("audit", help="show the last 20 audit log entries")
    return p


def run(args):
    if args.cmd == "demo" and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = get_conn()
    init_db(conn)
    svc = InsuranceService(conn)

    if args.cmd == "init":
        print(f"Database ready at {DB_PATH}")
    elif args.cmd == "demo":
        seed(conn)
        print(f"Sample data loaded into {DB_PATH}\n")
        show_reports(conn)
    elif args.cmd == "report":
        show_reports(conn)
    elif args.cmd == "expire-policies":
        print(f"{svc.expire_policies()} policies marked expired")
    elif args.cmd == "add-group":
        print("Group created with id", svc.add_group(args.name, args.industry, args.email))
    elif args.cmd == "add-plan":
        print("Plan created with id", svc.add_plan(args.name, args.sum_insured, args.monthly_premium))
    elif args.cmd == "add-member":
        print("Member created with id", svc.add_member(args.group_id, args.name, args.dob,
                                                       args.relation, args.email))
    elif args.cmd == "import-members":
        added, errors = svc.import_members_csv(args.group_id, args.csv_path)
        print(f"Imported {added} members")
        for e in errors:
            print("  skipped ->", e)
    elif args.cmd == "list-members":
        rows = [dict(r) for r in conn.execute(
            "SELECT member_id, name, dob, relation, email, status FROM members WHERE group_id=?",
            (args.group_id,))]
        print(reports.format_table(rows, f"MEMBERS OF GROUP {args.group_id}"))
    elif args.cmd == "create-policy":
        print("Policy created with id", svc.create_policy(args.group_id, args.plan_id,
                                                          args.start_date, args.months))
    elif args.cmd == "pay-premium":
        print("Payment recorded with id", svc.record_premium(args.policy_id, args.amount))
    elif args.cmd == "file-claim":
        print("Claim filed with id", svc.file_claim(args.policy_id, args.member_id, args.amount,
                                                    args.desc, args.date))
    elif args.cmd == "decide-claim":
        svc.decide_claim(args.claim_id, args.decision == "approve", args.note)
        print(f"Claim {args.claim_id} {args.decision}d")
    elif args.cmd == "audit":
        rows = [dict(r) for r in conn.execute(
            "SELECT created_at, action, entity, entity_id, details FROM audit_log "
            "ORDER BY log_id DESC LIMIT 20")]
        print(reports.format_table(rows, "AUDIT LOG (latest 20)"))
    conn.close()


def main():
    args = build_parser().parse_args()
    try:
        run(args)
    except ValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
