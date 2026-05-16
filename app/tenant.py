from flask import session, g


def current_company_id():
    return session.get("company_id") or getattr(g, "company_id", None)


def current_company_name():
    return session.get("company_name") or getattr(g, "company_name", None)
