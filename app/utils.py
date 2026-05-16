import unicodedata


def _normalize_text(value):
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_role(value):
    normalized = _normalize_text(value).strip().lower()
    if normalized in {
        "clinica/admin",
        "clinica",
        "admin",
        "cl\u00c3\u00adnica/admin",
    }:
        return "clinica"
    if normalized in {"medico", "m\u00c3\u00a9dico"}:
        return "medico"
    if normalized in {"paciente"}:
        return "paciente"
    return normalized


def is_admin(session_data):
    role = normalize_role(session_data.get("user_role", ""))
    return role == "clinica"


def is_master_admin(session_data, master_email):
    if not master_email:
        return False
    return session_data.get("user_email") == master_email
