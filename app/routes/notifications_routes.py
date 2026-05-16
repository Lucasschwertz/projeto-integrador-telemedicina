from flask import Blueprint, render_template, session, redirect, url_for, request

from app.db import get_db


notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/notificacoes")
def listar_notificacoes():
    if "user_email" not in session:
        return redirect(url_for("auth.login"))

    db = get_db()
    params = [session["user_email"]]
    query_scope = ""
    if session.get("company_id"):
        query_scope = " AND (company_id IS NULL OR company_id = ?)"
        params.append(session.get("company_id"))

    if request.args.get("marcar") == "1":
        db.execute(
            f"UPDATE notifications SET is_read = 1 WHERE user_email = ?{query_scope}",
            params,
        )
        db.commit()

    notificacoes = db.execute(
        f"""
        SELECT id, message, is_read, created_at, type, document_id
        FROM notifications
        WHERE user_email = ?{query_scope}
        ORDER BY created_at DESC
        """,
        params,
    ).fetchall()

    return render_template("notificacoes.html", notificacoes=notificacoes)
