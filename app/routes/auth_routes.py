import sqlite3

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g

from app.db import get_db
from app.tenant import current_company_id


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        if g.get("company_id") is None and request.host.endswith("luminacare.local"):
            flash("Empresa nao encontrada para este subdominio.")
            return render_template("cadastro.html")

        perfil = request.form["perfil"]
        crm = request.form.get("crm", "").strip()
        if perfil == "Medico" and not crm:
            flash("CRM obrigatorio para medico.")
            return render_template("cadastro.html")
        if perfil == "Medico" and not _valid_crm(crm):
            flash("CRM invalido. Use formato 12345-UF.")
            return render_template("cadastro.html")

        dados = {
            "nome": request.form["nome"],
            "email": request.form["email"],
            "senha": request.form["senha"],
            "perfil": perfil,
            "cpf_cnpj": request.form["cpf_cnpj"],
            "crm": crm or None,
            "company_id": current_company_id(),
            "telefone": request.form["telefone"],
            "sexo": request.form["sexo"],
            "data_nascimento": request.form["data_nascimento"],
            "rua": request.form["rua"],
            "numero": request.form["numero"],
            "complemento": request.form["complemento"],
            "cidade": request.form["cidade"],
            "estado": request.form["estado"],
            "cep": request.form["cep"],
        }

        try:
            db = get_db()
            db.execute(
                """
                INSERT INTO users (
                    nome, email, senha, perfil, cpf_cnpj, crm, company_id, telefone, sexo, data_nascimento,
                    rua, numero, complemento, cidade, estado, cep
                )
                VALUES (
                    :nome, :email, :senha, :perfil, :cpf_cnpj, :crm, :company_id, :telefone, :sexo,
                    :data_nascimento, :rua, :numero, :complemento, :cidade, :estado, :cep
                )
                """,
                dados,
            )
            db.commit()
            return redirect(url_for("auth.login"))
        except sqlite3.IntegrityError:
            flash("E-mail ja cadastrado!")
            return render_template("cadastro.html")

    return render_template("cadastro.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        senha = request.form["senha"]

        db = get_db()
        usuario = db.execute(
            "SELECT * FROM users WHERE email = ? AND senha = ?", (email, senha)
        ).fetchone()

        if usuario:
            if g.get("company_id") is not None and usuario["company_id"] != g.get("company_id"):
                flash("Usuario nao pertence a esta empresa.")
                return render_template("login.html")
            session["user_id"] = usuario["id"]
            session["user_name"] = usuario["nome"]
            session["user_email"] = usuario["email"]
            session["user_role"] = usuario["perfil"]
            session["company_id"] = usuario["company_id"]
            return redirect(url_for("dashboard.dashboard"))
        flash("Login invalido.")

    return render_template("login.html")


def _valid_crm(value):
    if not value:
        return False
    if "-" not in value:
        return False
    numero, uf = value.split("-", 1)
    return numero.isdigit() and len(uf) == 2 and uf.isalpha()


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
