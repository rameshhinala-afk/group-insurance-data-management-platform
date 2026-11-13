# Group Insurance Data Management Platform

A simple base platform for managing group (employer) insurance data: groups,
members, plans, policies, premiums and claims, with validation, an audit trail,
reports and data-quality checks. Pure Python 3.10+ standard library (SQLite).

## Structure
| File | Purpose |
|---|---|
| `db.py` | SQLite schema (with constraints) and connection helper |
| `services.py` | Business rules: validation, claims workflow, policies, CSV import, audit log |
| `reports.py` | Group summary, loss ratio, claims by status, expiring policies, data-quality checks |
| `seed.py` | Sample data |
| `main.py` | Command-line interface |
| `test_platform.py` | Unit tests |
| `sample_members.csv` | Example bulk-import file (includes bad rows on purpose) |

## Quick start
```bash
python main.py demo                 # builds insurance.db with sample data + reports
python -m unittest -v               # run tests
```

## Typical workflow
```bash
python main.py init
python main.py add-plan Silver 400000 600
python main.py add-group "Acme Ltd" --industry Retail --email hr@acme.example
python main.py import-members 1 sample_members.csv
python main.py create-policy 1 1 2026-11-01 --months 12
python main.py pay-premium 1 20000
python main.py file-claim 1 1 25000 --desc "Dental surgery"
python main.py decide-claim 1 approve --note "Verified"
python main.py report
python main.py audit
```

## Business rules enforced
- Valid email, date format, relation, and age (0-80); no duplicate members per group
- Premium = plan rate x active members in the group
- Claims only for active members of the policy's group, inside the policy period
- A member's pending + approved claims cannot exceed the plan's sum insured
- A claim can be decided only once; every change is written to the audit log

## Ideas to extend
Swap SQLite for PostgreSQL, add a REST API (FastAPI/Flask) or web dashboard,
add role-based access, dependants-per-employee limits, and renewal workflows.
