"""Loads sample data so the platform can be demonstrated immediately."""
from datetime import date, timedelta

from services import InsuranceService, ValidationError


def seed(conn):
    svc = InsuranceService(conn)
    today = date.today()

    basic = svc.add_plan("Basic", 300000, 450)
    gold = svc.add_plan("Gold", 500000, 800)

    tech = svc.add_group("Nova Tech Pvt Ltd", "IT", "hr@novatech.example")
    mills = svc.add_group("Sunrise Textile Mills", "Manufacturing", "admin@sunrise.example")
    clinic = svc.add_group("CarePlus Clinics", "Healthcare", None)

    people = [
        (tech, "Asha Rao", "1990-04-12", "self", "asha@novatech.example"),
        (tech, "Vikram Rao", "1988-09-30", "spouse", "vikram@example.com"),
        (tech, "Meera Iyer", "1995-01-22", "self", "meera@novatech.example"),
        (tech, "Rahul Shah", "1992-07-05", "self", None),
        (mills, "Suresh Patel", "1980-03-15", "self", "suresh@sunrise.example"),
        (mills, "Lakshmi Patel", "1983-11-02", "spouse", "lakshmi@example.com"),
        (mills, "Imran Khan", "1985-06-18", "self", "imran@sunrise.example"),
        (clinic, "Dr. Neha Gupta", "1986-12-09", "self", "neha@careplus.example"),
    ]
    member_ids = [svc.add_member(*p) for p in people]

    # Policy for Nova Tech starts 6 months ago; Sunrise policy ends soon.
    p_tech = svc.create_policy(tech, gold, (today - timedelta(days=180)).isoformat(), 12)
    p_mills = svc.create_policy(mills, basic, (today - timedelta(days=320)).isoformat(), 12)

    svc.record_premium(p_tech, svc.monthly_premium_due(p_tech) * 6,
                       (today - timedelta(days=30)).isoformat())
    svc.record_premium(p_mills, svc.monthly_premium_due(p_mills) * 10,
                       (today - timedelta(days=20)).isoformat())

    c1 = svc.file_claim(p_tech, member_ids[0], 120000, "Hospitalisation - surgery",
                        (today - timedelta(days=60)).isoformat())
    c2 = svc.file_claim(p_tech, member_ids[2], 15000, "Outpatient treatment",
                        (today - timedelta(days=15)).isoformat())
    c3 = svc.file_claim(p_mills, member_ids[4], 90000, "Accident care",
                        (today - timedelta(days=40)).isoformat())
    svc.decide_claim(c1, True, "Documents verified")
    svc.decide_claim(c3, False, "Pre-existing condition not covered")
    # c2 intentionally left pending
    return {"groups": [tech, mills, clinic], "policies": [p_tech, p_mills], "claims": [c1, c2, c3]}
