import os
from datetime import datetime

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    current_app,
    send_file,
    flash,
)

from app.db import get_db
from app.utils import normalize_role
from app.tenant import current_company_id, current_company_name

try:
    from reportlab.pdfgen import canvas
except Exception:
    canvas = None


relatorios_bp = Blueprint("relatorios", __name__)


@relatorios_bp.route("/relatorios", methods=["GET", "POST"])
def relatorios():
    if normalize_role(session.get("user_role", "")) != "clinica":
        return redirect(url_for("auth.login"))

    db = get_db()
    if current_company_id():
        medicos = db.execute(
            """
            SELECT DISTINCT nome FROM users
            WHERE perfil = 'Medico' AND company_id = ?
            ORDER BY nome
            """,
            (current_company_id(),),
        ).fetchall()
    else:
        medicos = db.execute(
            "SELECT DISTINCT nome FROM users WHERE perfil = 'Medico' ORDER BY nome"
        ).fetchall()

    if request.method == "POST":
        if canvas is None:
            flash("Biblioteca PDF nao instalada. Instale reportlab.")
            return render_template("relatorios.html", medicos=medicos)

        filtros = _get_filters(request)
        resultado = _build_report_data(db, filtros)
        filename = _build_pdf(resultado, filtros, current_company_name() or "Clinica")
        return render_template("relatorio_gerado.html", arquivo=filename)

    return render_template("relatorios.html", medicos=medicos)


@relatorios_bp.route("/relatorios/download/<nome_arquivo>")
def relatorios_download(nome_arquivo):
    if normalize_role(session.get("user_role", "")) != "clinica":
        return redirect(url_for("auth.login"))

    caminho = os.path.join(current_app.config["REPORTS_FOLDER"], nome_arquivo)
    return send_file(caminho, as_attachment=True)


def _get_filters(req):
    return {
        "inicio": req.form.get("inicio", "").strip(),
        "fim": req.form.get("fim", "").strip(),
        "medico": req.form.get("medico", "").strip(),
        "tipo": req.form.get("tipo", "").strip(),
        "pagamento": req.form.get("pagamento", "").strip(),
    }


def _build_report_data(db, filtros):
    params = []
    doc_query = """
        SELECT id, doctor_name, patient_name, doc_type, status, created_at
        FROM documents
        WHERE 1=1
    """
    if current_company_id():
        doc_query += " AND company_id = ?"
        params.append(current_company_id())
    if filtros["inicio"]:
        doc_query += " AND date(created_at) >= date(?)"
        params.append(filtros["inicio"])
    if filtros["fim"]:
        doc_query += " AND date(created_at) <= date(?)"
        params.append(filtros["fim"])
    if filtros["medico"]:
        doc_query += " AND doctor_name = ?"
        params.append(filtros["medico"])
    if filtros["tipo"]:
        doc_query += " AND doc_type = ?"
        params.append(filtros["tipo"])

    documentos = db.execute(doc_query, params).fetchall()

    appt_query = """
        SELECT doctor_name, patient_name, status, pago, date, time
        FROM appointments
        WHERE 1=1
    """
    appt_params = []
    if current_company_id():
        appt_query += " AND company_id = ?"
        appt_params.append(current_company_id())
    if filtros["inicio"]:
        appt_query += " AND date(date) >= date(?)"
        appt_params.append(filtros["inicio"])
    if filtros["fim"]:
        appt_query += " AND date(date) <= date(?)"
        appt_params.append(filtros["fim"])
    if filtros["medico"]:
        appt_query += " AND doctor_name = ?"
        appt_params.append(filtros["medico"])

    consultas = db.execute(appt_query, appt_params).fetchall()

    pagos_por_paciente = {}
    for c in consultas:
        pagos_por_paciente[c["patient_name"]] = pagos_por_paciente.get(
            c["patient_name"], 0
        ) or c["pago"]

    if filtros["pagamento"]:
        pago_flag = 1 if filtros["pagamento"] == "pago" else 0
        documentos = [
            d
            for d in documentos
            if pagos_por_paciente.get(d["patient_name"], 0) == pago_flag
        ]

    total_consultas = len([c for c in consultas if c["status"] == "realizada"])
    total_docs = len(documentos)
    total_laudados = len([d for d in documentos if d["status"] == "laudado"])
    perc_laudados = int((total_laudados / total_docs) * 100) if total_docs else 0
    total_pagos = len([c for c in consultas if c["pago"] == 1])
    total_recebido = total_pagos * 100.0

    return {
        "documentos": documentos,
        "total_consultas": total_consultas,
        "total_docs": total_docs,
        "perc_laudados": perc_laudados,
        "total_recebido": total_recebido,
        "pagos_por_paciente": pagos_por_paciente,
    }


def _build_pdf(resultado, filtros, company_name):
    reports_folder = current_app.config["REPORTS_FOLDER"]
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"relatorio_clinica_{now}.pdf"
    path = os.path.join(reports_folder, filename)

    pdf = canvas.Canvas(path)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, 800, "LuminaCare - Relatorio Gerencial")
    pdf.setFont("Helvetica", 10)
    periodo = f"{filtros['inicio'] or 'inicio'} ate {filtros['fim'] or 'hoje'}"
    pdf.drawString(40, 784, f"Clinica: {company_name}")
    pdf.drawString(40, 770, f"Periodo: {periodo}")

    y = 748
    pdf.setFont("Helvetica-Bold", 10)
    headers = ["Data", "Medico", "Paciente", "Tipo", "Status", "Pagamento"]
    positions = [40, 120, 230, 360, 450, 520]
    for text, x in zip(headers, positions):
        pdf.drawString(x, y, text)

    pdf.setFont("Helvetica", 9)
    y -= 16
    for doc in resultado["documentos"]:
        pagamento = (
            "Pago"
            if resultado["pagos_por_paciente"].get(doc["patient_name"], 0)
            else "Nao pago"
        )
        row = [
            doc["created_at"][:10],
            doc["doctor_name"],
            doc["patient_name"],
            doc["doc_type"],
            doc["status"],
            pagamento,
        ]
        for value, x in zip(row, positions):
            pdf.drawString(x, y, str(value))
        y -= 14
        if y < 120:
            pdf.showPage()
            y = 800
            pdf.setFont("Helvetica-Bold", 10)
            for text, x in zip(headers, positions):
                pdf.drawString(x, y, text)
            pdf.setFont("Helvetica", 9)
            y -= 16

    y -= 10
    if y < 140:
        pdf.showPage()
        y = 760
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, f"Total de consultas realizadas: {resultado['total_consultas']}")
    y -= 14
    pdf.drawString(40, y, f"Total de documentos emitidos: {resultado['total_docs']}")
    y -= 14
    pdf.drawString(40, y, f"% de documentos laudados: {resultado['perc_laudados']}%")
    y -= 14
    pdf.drawString(40, y, f"R$ recebido no periodo: {resultado['total_recebido']:.2f}")

    pdf.save()
    return filename
