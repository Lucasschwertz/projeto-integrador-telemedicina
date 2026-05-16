from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app

from app.db import get_db
from app.utils import is_master_admin


empresas_bp = Blueprint("empresas", __name__)


@empresas_bp.route("/empresas", methods=["GET", "POST"])
def empresas():
    if not is_master_admin(session, current_app.config["MASTER_ADMIN_EMAIL"]):
        return redirect(url_for("auth.login"))

    db = get_db()
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        cnpj = request.form.get("cnpj", "").strip()
        plano = request.form.get("plano", "").strip()
        status = request.form.get("status", "").strip()
        subdomain = request.form.get("subdomain", "").strip().lower()

        if not nome or not cnpj or not plano or not status or not subdomain:
            flash("Preencha todos os campos.")
        else:
            db.execute(
                """
                INSERT INTO empresas (nome, cnpj, plano, status, subdomain)
                VALUES (?, ?, ?, ?, ?)
                """,
                (nome, cnpj, plano, status, subdomain),
            )
            db.commit()
            flash("Empresa cadastrada.")
            return redirect(url_for("empresas.empresas"))

    empresas_lista = db.execute(
        "SELECT id, nome, cnpj, plano, status, subdomain FROM empresas ORDER BY nome"
    ).fetchall()

    return render_template("empresas.html", empresas=empresas_lista)
