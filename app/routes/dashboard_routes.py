from datetime import datetime, timedelta

from flask import Blueprint, render_template, session, redirect, url_for

from app.db import get_db
from app.tenant import current_company_id
from app.utils import normalize_role


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
def dashboard():
    role = normalize_role(session.get("user_role", ""))

    if role == "paciente":
        return redirect(url_for("dashboard.dashboard_paciente"))
    if role == "medico":
        return redirect(url_for("dashboard.dashboard_medico"))
    if role == "clinica":
        return redirect(url_for("dashboard.dashboard_clinica"))
    return redirect(url_for("auth.login"))


@dashboard_bp.route("/dashboard_paciente")
def dashboard_paciente():
    db = get_db()
    company_id = current_company_id()
    documentos = db.execute(
        "SELECT COUNT(*) FROM documents WHERE patient_name = ? AND (company_id IS NULL OR company_id = ?)",
        (session.get("user_name"), company_id),
    ).fetchone()[0]
    exames = db.execute(
        """
        SELECT COUNT(*) FROM documents
        WHERE patient_name = ? AND category = 'exame' AND (company_id IS NULL OR company_id = ?)
        """,
        (session.get("user_name"), company_id),
    ).fetchone()[0]
    notificacoes = db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_email = ? AND is_read = 0",
        (session.get("user_email"),),
    ).fetchone()[0]
    laudados = db.execute(
        """
        SELECT COUNT(*) FROM documents
        WHERE patient_name = ? AND status = 'laudado' AND (company_id IS NULL OR company_id = ?)
        """,
        (session.get("user_name"), company_id),
    ).fetchone()[0]
    labels, valores = _monthly_document_stats(
        db, "WHERE patient_name = ?", (session.get("user_name"),), company_id
    )
    percentual_laudado = _percent(laudados, documentos)
    consultas = db.execute(
        """
        SELECT id, doctor_name, date, time, tipo, status, pago, payment_status, payment_link
        FROM appointments
        WHERE patient_name = ? AND status = 'confirmado' AND (company_id IS NULL OR company_id = ?)
        ORDER BY date, time
        LIMIT 3
        """,
        (session.get("user_name"), company_id),
    ).fetchall()
    return render_template(
        "dashboard_paciente.html",
        documentos=documentos,
        exames=exames,
        notificacoes=notificacoes,
        chart_labels=labels,
        chart_values=valores,
        percentual_laudado=percentual_laudado,
        consultas=consultas,
    )


@dashboard_bp.route("/dashboard_medico")
def dashboard_medico():
    db = get_db()
    company_id = current_company_id()
    documentos = db.execute(
        "SELECT COUNT(*) FROM documents WHERE doctor_name = ? AND (company_id IS NULL OR company_id = ?)",
        (session.get("user_name"), company_id),
    ).fetchone()[0]
    exames = db.execute(
        """
        SELECT COUNT(*) FROM documents
        WHERE doctor_name = ? AND category = 'exame' AND (company_id IS NULL OR company_id = ?)
        """,
        (session.get("user_name"), company_id),
    ).fetchone()[0]
    pendentes = db.execute(
        """
        SELECT COUNT(*) FROM documents
        WHERE doctor_name = ? AND status = 'pendente' AND (company_id IS NULL OR company_id = ?)
        """,
        (session.get("user_name"), company_id),
    ).fetchone()[0]
    laudados = db.execute(
        """
        SELECT COUNT(*) FROM documents
        WHERE doctor_name = ? AND status = 'laudado' AND (company_id IS NULL OR company_id = ?)
        """,
        (session.get("user_name"), company_id),
    ).fetchone()[0]
    pacientes = db.execute(
        """
        SELECT COUNT(DISTINCT patient_name) FROM documents
        WHERE doctor_name = ? AND (company_id IS NULL OR company_id = ?)
        """,
        (session.get("user_name"), company_id),
    ).fetchone()[0]
    pendentes_lista = db.execute(
        """
        SELECT id, patient_name, doc_type, created_at
        FROM documents
        WHERE doctor_name = ? AND status = 'pendente' AND (company_id IS NULL OR company_id = ?)
        ORDER BY created_at DESC
        LIMIT 5
        """,
        (session.get("user_name"), company_id),
    ).fetchall()
    consultas = db.execute(
        """
        SELECT id, patient_name, date, time, tipo, status, pago, payment_status
        FROM appointments
        WHERE doctor_name = ? AND status = 'confirmado' AND (company_id IS NULL OR company_id = ?)
        ORDER BY date, time
        LIMIT 3
        """,
        (session.get("user_name"), company_id),
    ).fetchall()

    labels, valores = _monthly_document_stats(
        db, "WHERE doctor_name = ?", (session.get("user_name"),), company_id
    )
    percentual_laudado = _percent(laudados, documentos)
    return render_template(
        "dashboard_medico.html",
        documentos=documentos,
        exames=exames,
        pendentes=pendentes,
        pacientes=pacientes,
        pendentes_lista=pendentes_lista,
        chart_labels=labels,
        chart_values=valores,
        percentual_laudado=percentual_laudado,
        consultas=consultas,
    )


@dashboard_bp.route("/dashboard_clinica")
def dashboard_clinica():
    db = get_db()
    company_id = current_company_id()
    if company_id:
        usuarios = db.execute(
            "SELECT COUNT(*) FROM users WHERE company_id = ?",
            (company_id,),
        ).fetchone()[0]
        documentos = db.execute(
            "SELECT COUNT(*) FROM documents WHERE company_id = ?",
            (company_id,),
        ).fetchone()[0]
    else:
        usuarios = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        documentos = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    laudados = db.execute(
        "SELECT COUNT(*) FROM documents WHERE status = 'laudado'" + (" AND company_id = ?" if company_id else ""),
        (company_id,) if company_id else (),
    ).fetchone()[0]
    contatos = db.execute(
        "SELECT COUNT(*) FROM contact_requests" + (" WHERE company_id = ?" if company_id else ""),
        (company_id,) if company_id else (),
    ).fetchone()[0]
    labels, valores = _monthly_document_stats(db, "", (), company_id)
    percentual_laudado = _percent(laudados, documentos)
    return render_template(
        "dashboard_clinica.html",
        usuarios=usuarios,
        documentos=documentos,
        contatos=contatos,
        chart_labels=labels,
        chart_values=valores,
        percentual_laudado=percentual_laudado,
    )


def _monthly_document_stats(db, where_clause, params, company_id):
    hoje = datetime.now().replace(day=1)
    meses = []
    for i in range(5, -1, -1):
        mes = hoje - timedelta(days=30 * i)
        meses.append(mes.strftime("%Y-%m"))

    if company_id:
        if "WHERE" in where_clause:
            where_clause += " AND company_id = ?"
        else:
            where_clause = "WHERE company_id = ?"
        params = (*params, company_id)

    rows = db.execute(
        f"""
        SELECT strftime('%Y-%m', created_at) AS mes, COUNT(*) as total
        FROM documents
        {where_clause}
        GROUP BY mes
        """,
        params,
    ).fetchall()
    totals = {row["mes"]: row["total"] for row in rows}
    labels = [m for m in meses]
    values = [totals.get(m, 0) for m in meses]
    return labels, values


def _percent(part, total):
    if not total:
        return 0
    return int((part / total) * 100)
