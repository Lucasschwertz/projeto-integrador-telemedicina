from datetime import datetime

from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify, abort

from app.db import get_db
from app.utils import normalize_role
from app.tenant import current_company_id


consulta_bp = Blueprint("consulta", __name__)

CHAT_STORE = {}


@consulta_bp.route("/consulta/<int:appointment_id>")
def consulta(appointment_id):
    if "user_name" not in session:
        return redirect(url_for("auth.login"))

    db = get_db()
    agendamento = db.execute(
        """
        SELECT id, doctor_name, patient_name, date, time, tipo, status, pago, company_id
        FROM appointments
        WHERE id = ?
        """,
        (appointment_id,),
    ).fetchone()
    if not agendamento:
        abort(404)

    if current_company_id() and agendamento["company_id"] != current_company_id():
        abort(403)

    if not _can_access_appointment(session, agendamento):
        abort(403)

    if agendamento["status"] not in {"confirmado", "realizada"}:
        if normalize_role(session.get("user_role", "")) == "medico":
            return redirect(url_for("dashboard.dashboard_medico"))
        return redirect(url_for("agenda.agenda_paciente"))

    if not agendamento["pago"]:
        if normalize_role(session.get("user_role", "")) == "medico":
            from flask import flash

            flash("Consulta ainda nao paga pelo paciente.")
            return redirect(url_for("dashboard.dashboard_medico"))
        return redirect(url_for("dashboard.dashboard_paciente"))

    room_name = f"luminacare-{appointment_id}"
    return render_template(
        "consulta.html",
        agendamento=agendamento,
        room_name=room_name,
    )


@consulta_bp.route("/consulta/<int:appointment_id>/chat", methods=["GET", "POST"])
def consulta_chat(appointment_id):
    if "user_name" not in session:
        return jsonify({"error": "unauthorized"}), 401

    db = get_db()
    agendamento = db.execute(
        """
        SELECT id, doctor_name, patient_name, status, company_id
        FROM appointments
        WHERE id = ?
        """,
        (appointment_id,),
    ).fetchone()
    if not agendamento or (current_company_id() and agendamento["company_id"] != current_company_id()):
        return jsonify({"error": "forbidden"}), 403
    if not _can_access_appointment(session, agendamento):
        return jsonify({"error": "forbidden"}), 403

    if request.method == "POST":
        message = request.json.get("message", "").strip()
        if message:
            CHAT_STORE.setdefault(appointment_id, []).append(
                {
                    "author": session.get("user_name"),
                    "role": session.get("user_role", ""),
                    "message": message,
                    "created_at": datetime.now().strftime("%H:%M"),
                }
            )
        return jsonify({"ok": True})

    return jsonify(CHAT_STORE.get(appointment_id, []))


@consulta_bp.route("/consulta/<int:appointment_id>/encerrar", methods=["POST"])
def encerrar_consulta(appointment_id):
    if normalize_role(session.get("user_role", "")) != "medico":
        return redirect(url_for("auth.login"))

    db = get_db()
    agendamento = db.execute(
        """
        SELECT id, doctor_name, status, company_id
        FROM appointments
        WHERE id = ?
        """,
        (appointment_id,),
    ).fetchone()
    if not agendamento:
        abort(404)
    if current_company_id() and agendamento["company_id"] != current_company_id():
        abort(403)
    if agendamento["doctor_name"] != session.get("user_name"):
        abort(403)

    db.execute(
        "UPDATE appointments SET status = 'realizada' WHERE id = ?",
        (appointment_id,),
    )
    db.commit()
    return redirect(url_for("dashboard.dashboard_medico"))


def _can_access_appointment(session_data, agendamento):
    role = normalize_role(session_data.get("user_role", ""))
    if role == "medico" and agendamento["doctor_name"] == session_data.get("user_name"):
        return True
    if role == "paciente" and agendamento["patient_name"] == session_data.get("user_name"):
        return True
    return False
