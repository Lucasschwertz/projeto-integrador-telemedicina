from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from app.db import get_db
from app.utils import normalize_role
from app.tenant import current_company_id


agenda_bp = Blueprint("agenda", __name__)


@agenda_bp.route("/agenda/medico", methods=["GET", "POST"])
def agenda_medico():
    if normalize_role(session.get("user_role", "")) != "medico":
        return redirect(url_for("auth.login"))

    db = get_db()
    if request.method == "POST":
        data = request.form.get("data", "").strip()
        hora = request.form.get("hora", "").strip()
        tipo = request.form.get("tipo", "").strip()

        if not data or not hora or not tipo:
            flash("Preencha data, hora e tipo.")
        else:
            db.execute(
                """
                INSERT INTO availability (doctor_name, date, time, tipo, company_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session.get("user_name"), data, hora, tipo, current_company_id()),
            )
            db.commit()
            flash("Horario cadastrado com sucesso!")

    horarios = db.execute(
        """
        SELECT id, date, time, tipo
        FROM availability
        WHERE doctor_name = ? AND (company_id IS NULL OR company_id = ?)
        ORDER BY date, time
        """,
        (session.get("user_name"), current_company_id()),
    ).fetchall()

    agendamentos = db.execute(
        """
        SELECT id, patient_name, date, time, tipo, status, pago, payment_status
        FROM appointments
        WHERE doctor_name = ? AND (company_id IS NULL OR company_id = ?)
        ORDER BY date DESC, time DESC
        """,
        (session.get("user_name"), current_company_id()),
    ).fetchall()

    return render_template(
        "agenda_medico.html",
        horarios=horarios,
        agendamentos=agendamentos,
    )


@agenda_bp.route("/agenda/paciente", methods=["GET", "POST"])
def agenda_paciente():
    if normalize_role(session.get("user_role", "")) != "paciente":
        return redirect(url_for("auth.login"))

    db = get_db()
    if request.method == "POST":
        slot_id = request.form.get("slot_id", "").strip()
        if not slot_id:
            flash("Selecione um horario.")
        else:
            slot = db.execute(
                """
                SELECT id, doctor_name, date, time, tipo
                FROM availability
                WHERE id = ? AND (company_id IS NULL OR company_id = ?)
                """,
                (slot_id, current_company_id()),
            ).fetchone()
            if slot:
                db.execute(
                    """
                    INSERT INTO appointments (
                        doctor_name, patient_name, date, time, tipo, status, pago, payment_status, company_id
                    )
                    VALUES (?, ?, ?, ?, ?, 'agendado', 0, 'aguardando', ?)
                    """,
                    (
                        slot["doctor_name"],
                        session.get("user_name"),
                        slot["date"],
                        slot["time"],
                        slot["tipo"],
                        current_company_id(),
                    ),
                )
                db.execute(
                    "DELETE FROM availability WHERE id = ? AND (company_id IS NULL OR company_id = ?)",
                    (slot_id, current_company_id()),
                )
                db.commit()
                flash("Consulta agendada com sucesso!")
            else:
                flash("Horario indisponivel.")

    horarios = db.execute(
        """
        SELECT id, doctor_name, date, time, tipo
        FROM availability
        WHERE (company_id IS NULL OR company_id = ?)
        ORDER BY date, time
        """,
        (current_company_id(),),
    ).fetchall()

    agendamentos = db.execute(
        """
        SELECT id, doctor_name, date, time, tipo, status, pago, payment_status
        FROM appointments
        WHERE patient_name = ? AND (company_id IS NULL OR company_id = ?)
        ORDER BY date DESC, time DESC
        """,
        (session.get("user_name"), current_company_id()),
    ).fetchall()

    return render_template(
        "agenda_paciente.html",
        horarios=horarios,
        agendamentos=agendamentos,
    )


@agenda_bp.route("/agenda/status/<int:appointment_id>", methods=["POST"])
def atualizar_status_agenda(appointment_id):
    if normalize_role(session.get("user_role", "")) != "medico":
        return redirect(url_for("auth.login"))

    status = request.form.get("status", "").strip().lower()
    if status not in {"confirmado", "cancelado"}:
        return redirect(url_for("agenda.agenda_medico"))

    db = get_db()
    agendamento = db.execute(
        """
        SELECT id, doctor_name, patient_name, company_id
        FROM appointments
        WHERE id = ?
        """,
        (appointment_id,),
    ).fetchone()
    if not agendamento or agendamento["doctor_name"] != session.get("user_name"):
        return redirect(url_for("agenda.agenda_medico"))
    if current_company_id() and agendamento["company_id"] != current_company_id():
        return redirect(url_for("agenda.agenda_medico"))

    db.execute(
        "UPDATE appointments SET status = ? WHERE id = ?",
        (status, appointment_id),
    )
    db.commit()
    flash("Status atualizado.")
    return redirect(url_for("agenda.agenda_medico"))
