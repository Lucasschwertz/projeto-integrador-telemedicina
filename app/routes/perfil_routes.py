from flask import Blueprint, render_template, request, session, redirect, url_for, flash

from app.db import get_db


perfil_bp = Blueprint("perfil", __name__)


@perfil_bp.route("/perfil", methods=["GET", "POST"])
def perfil():
    if "user_email" not in session:
        return redirect(url_for("auth.login"))

    email_logado = session["user_email"]
    db = get_db()

    if request.method == "POST":
        crm = request.form.get("crm", "").strip()
        campos = {
            "nome": request.form["nome"],
            "telefone": request.form["telefone"],
            "senha": request.form["senha"],
            "sexo": request.form["sexo"],
            "data_nascimento": request.form["data_nascimento"],
            "rua": request.form["rua"],
            "numero": request.form["numero"],
            "complemento": request.form["complemento"],
            "cidade": request.form["cidade"],
            "estado": request.form["estado"],
            "cep": request.form["cep"],
            "crm": crm or None,
            "email": email_logado,
        }

        db.execute(
            """
            UPDATE users SET
                nome = :nome,
                telefone = :telefone,
                senha = :senha,
                sexo = :sexo,
                data_nascimento = :data_nascimento,
                rua = :rua,
                numero = :numero,
                complemento = :complemento,
                cidade = :cidade,
                estado = :estado,
                cep = :cep,
                crm = :crm
            WHERE email = :email
            """,
            campos,
        )
        db.commit()
        flash("Dados atualizados com sucesso!")
        session["user_name"] = campos["nome"]

    dados = db.execute("SELECT * FROM users WHERE email = ?", (email_logado,)).fetchone()

    return render_template("perfil.html", dados=dados)
