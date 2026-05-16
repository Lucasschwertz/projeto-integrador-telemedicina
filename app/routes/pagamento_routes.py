import json
import urllib.request

from flask import Blueprint, redirect, url_for, session, flash, current_app, request, jsonify, render_template

from app.db import get_db
from app.utils import normalize_role
from app.tenant import current_company_id


pagamento_bp = Blueprint("pagamento", __name__)


@pagamento_bp.route("/pagar_consulta/<int:appointment_id>")
def pagar_consulta(appointment_id):
    if normalize_role(session.get("user_role", "")) != "paciente":
        return redirect(url_for("auth.login"))

    db = get_db()
    consulta = db.execute(
        """
        SELECT id, doctor_name, patient_name, date, time, tipo, pago, payment_link, company_id
        FROM appointments
        WHERE id = ? AND patient_name = ?
        """,
        (appointment_id, session.get("user_name")),
    ).fetchone()
    if not consulta:
        flash("Consulta nao encontrada.")
        return redirect(url_for("dashboard.dashboard_paciente"))

    if current_company_id() and consulta["company_id"] != current_company_id():
        flash("Consulta nao encontrada.")
        return redirect(url_for("dashboard.dashboard_paciente"))

    if consulta["pago"]:
        return redirect(url_for("pagamento.pagamento_confirmado"))

    if current_app.config.get("PAYMENT_TEST_MODE"):
        db.execute(
            """
            UPDATE appointments
            SET pago = 1, payment_status = 'approved', payment_provider = 'test'
            WHERE id = ?
            """,
            (appointment_id,),
        )
        db.commit()
        return redirect(url_for("pagamento.pagamento_confirmado"))

    payment_link, external_id = _create_mp_preference(consulta)
    if not payment_link:
        flash("Pagamento indisponivel. Configure o MP_ACCESS_TOKEN.")
        return redirect(url_for("dashboard.dashboard_paciente"))

    db.execute(
        """
        UPDATE appointments
        SET payment_link = ?, payment_provider = 'mercadopago', payment_external_id = ?, payment_status = 'aguardando'
        WHERE id = ?
        """,
        (payment_link, external_id, appointment_id),
    )
    db.commit()
    return redirect(payment_link)


@pagamento_bp.route("/pagamento/pendente")
def pagamento_pendente():
    return render_template("pagamento_pendente.html")


@pagamento_bp.route("/pagamento/confirmado")
def pagamento_confirmado():
    return render_template("pagamento_confirmado.html")


@pagamento_bp.route("/pagamento/webhook", methods=["POST"])
def pagamento_webhook():
    token = request.args.get("token", "")
    if token != current_app.config["PAYMENT_WEBHOOK_TOKEN"]:
        return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    payment_id = payload.get("data", {}).get("id")
    status = payload.get("status") or payload.get("action") or ""

    if not payment_id:
        return jsonify({"ok": True})

    db = get_db()
    consulta = db.execute(
        """
        SELECT id FROM appointments
        WHERE payment_external_id = ?
        """,
        (str(payment_id),),
    ).fetchone()
    if not consulta:
        return jsonify({"ok": True})

    pago = 1 if status == "approved" else 0
    db.execute(
        """
        UPDATE appointments
        SET pago = ?, payment_status = ?
        WHERE id = ?
        """,
        (pago, status, consulta["id"]),
    )
    db.commit()
    return jsonify({"ok": True})


def _create_mp_preference(consulta):
    env = current_app.config.get("MP_ENV", "test").lower()
    access_token = (
        current_app.config.get("MP_ACCESS_TOKEN_TEST")
        if env == "test"
        else current_app.config.get("MP_ACCESS_TOKEN")
    )
    if not access_token:
        return None, None

    base_url = current_app.config["PUBLIC_BASE_URL"]
    notification_url = f"{base_url}/pagamento/webhook?token={current_app.config['PAYMENT_WEBHOOK_TOKEN']}"

    body = {
        "items": [
            {
                "title": f"Consulta {consulta['tipo']}",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 100.0,
            }
        ],
        "payer": {"name": consulta["patient_name"]},
        "back_urls": {
            "success": f"{base_url}/pagamento/confirmado",
            "pending": f"{base_url}/pagamento/pendente",
            "failure": f"{base_url}/pagamento/pendente",
        },
        "notification_url": notification_url,
    }

    req = urllib.request.Request(
        "https://api.mercadopago.com/checkout/preferences",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            init_point = payload.get("sandbox_init_point") if env == "test" else payload.get("init_point")
            return init_point, str(payload.get("id"))
    except Exception:
        return None, None
