from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from app.db import get_db
from app.utils import is_admin
from app.tenant import current_company_id


usuarios_bp = Blueprint("usuarios", __name__)


@usuarios_bp.route("/usuarios")
def listar_usuarios():
    if not is_admin(session):
        return redirect(url_for("auth.login"))

    termo = request.args.get("busca", "").strip()
    filtro_perfil = request.args.get("perfil", "")
    pagina = int(request.args.get("pagina", 1))
    limite = 5
    offset = (pagina - 1) * limite

    db = get_db()
    query = """
        SELECT id, nome, email, perfil, cpf_cnpj, crm, telefone, sexo, data_nascimento,
               rua, numero, complemento, cidade, estado, cep
        FROM users
        WHERE 1=1
    """
    params = []
    company_id = current_company_id()
    if company_id:
        query += " AND company_id = ?"
        params.append(company_id)

    if termo:
        query += " AND (nome LIKE ? OR email LIKE ?)"
        params.extend([f"%{termo}%", f"%{termo}%"])

    if filtro_perfil:
        if filtro_perfil == "Medico":
            query += " AND perfil IN (?, ?, ?)"
            params.extend(["Medico", "M\u00e9dico", "M\u00c3\u00a9dico"])
        elif filtro_perfil == "Clinica/Admin":
            query += " AND perfil IN (?, ?, ?)"
            params.extend(["Clinica/Admin", "Cl\u00ednica/Admin", "Cl\u00c3\u00adnica/Admin"])
        else:
            query += " AND perfil = ?"
            params.append(filtro_perfil)

    total_query = "SELECT COUNT(*) FROM (" + query + ")"
    total_registros = db.execute(total_query, params).fetchone()[0]
    total_paginas = (total_registros + limite - 1) // limite

    query += " LIMIT ? OFFSET ?"
    params.extend([limite, offset])
    usuarios = db.execute(query, params).fetchall()

    return render_template(
        "usuarios_listar.html",
        usuarios=usuarios,
        busca=termo,
        perfil=filtro_perfil,
        pagina=pagina,
        total_paginas=total_paginas,
    )


@usuarios_bp.route("/usuarios/editar/<int:user_id>", methods=["GET", "POST"])
def editar_usuario(user_id):
    if not is_admin(session):
        return redirect(url_for("auth.login"))

    db = get_db()
    usuario = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not usuario:
        return redirect(url_for("usuarios.listar_usuarios"))
    if current_company_id() and usuario["company_id"] != current_company_id():
        return redirect(url_for("usuarios.listar_usuarios"))

    if request.method == "POST":
        perfil = request.form["perfil"]
        crm = request.form.get("crm", "").strip()
        if perfil == "Medico" and not crm:
            flash("CRM obrigatorio para medico.")
            return render_template("usuarios_editar.html", usuario=usuario)
        if perfil == "Medico" and not _valid_crm(crm):
            flash("CRM invalido. Use formato 12345-UF.")
            return render_template("usuarios_editar.html", usuario=usuario)

        dados = (
            request.form["nome"],
            request.form["email"],
            request.form["senha"],
            perfil,
            crm or None,
            current_company_id(),
            user_id,
        )
        db.execute(
            """
            UPDATE users
            SET nome = ?, email = ?, senha = ?, perfil = ?, crm = ?, company_id = ?
            WHERE id = ?
            """,
            dados,
        )
        db.commit()
        flash("Usuario atualizado com sucesso!")
        return redirect(url_for("usuarios.listar_usuarios"))

    return render_template("usuarios_editar.html", usuario=usuario)


@usuarios_bp.route("/usuarios/excluir/<int:user_id>")
def excluir_usuario(user_id):
    if not is_admin(session):
        return redirect(url_for("auth.login"))

    db = get_db()
    if current_company_id():
        usuario = db.execute(
            "SELECT email FROM users WHERE id = ? AND company_id = ?",
            (user_id, current_company_id()),
        ).fetchone()
    else:
        usuario = db.execute(
            "SELECT email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    if usuario and usuario["email"] == session.get("user_email"):
        flash("Voce nao pode excluir seu proprio usuario.")
        return redirect(url_for("usuarios.listar_usuarios"))

    if current_company_id():
        db.execute(
            "DELETE FROM users WHERE id = ? AND company_id = ?",
            (user_id, current_company_id()),
        )
    else:
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("Usuario excluido com sucesso!")
    return redirect(url_for("usuarios.listar_usuarios"))


@usuarios_bp.route("/usuarios/novo", methods=["GET", "POST"])
def novo_usuario():
    if not is_admin(session):
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        perfil = request.form["perfil"]
        crm = request.form.get("crm", "").strip()
        if perfil == "Medico" and not crm:
            flash("CRM obrigatorio para medico.")
            return render_template("usuarios_novo.html")
        if perfil == "Medico" and not _valid_crm(crm):
            flash("CRM invalido. Use formato 12345-UF.")
            return render_template("usuarios_novo.html")

        company_id = current_company_id()
        if not company_id:
            flash("Empresa nao definida para este usuario.")
            return render_template("usuarios_novo.html")

        campos = (
            request.form["nome"],
            request.form["email"],
            request.form["senha"],
            perfil,
            request.form["cpf_cnpj"],
            crm or None,
            company_id,
            request.form["telefone"],
            request.form["sexo"],
            request.form["data_nascimento"],
            request.form["rua"],
            request.form["numero"],
            request.form["complemento"],
            request.form["cidade"],
            request.form["estado"],
            request.form["cep"],
        )

        db = get_db()
        db.execute(
            """
            INSERT INTO users (
                nome, email, senha, perfil, cpf_cnpj, crm, company_id, telefone,
                sexo, data_nascimento, rua, numero, complemento,
                cidade, estado, cep
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            campos,
        )
        db.commit()
        flash("Usuario cadastrado com sucesso!")
        return redirect(url_for("usuarios.listar_usuarios"))

    return render_template("usuarios_novo.html")


@usuarios_bp.route("/usuarios/<int:user_id>")
def visualizar_usuario(user_id):
    if not is_admin(session):
        return redirect(url_for("auth.login"))

    db = get_db()
    usuario = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if usuario and current_company_id() and usuario["company_id"] != current_company_id():
        return redirect(url_for("usuarios.listar_usuarios"))

    return render_template("usuarios_detalhes.html", usuario=usuario)


def _valid_crm(value):
    if not value:
        return False
    if "-" not in value:
        return False
    numero, uf = value.split("-", 1)
    return numero.isdigit() and len(uf) == 2 and uf.isalpha()
