import os
from datetime import datetime

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_from_directory,
    send_file,
    flash,
    current_app,
    abort,
)
from werkzeug.utils import secure_filename

from app.db import get_db
from app.utils import normalize_role
from app.tenant import current_company_id

try:
    from reportlab.pdfgen import canvas
except Exception:
    canvas = None

documentos_bp = Blueprint("documentos", __name__)


def _upload_folder():
    return current_app.config["UPLOAD_FOLDER"]


def _documents_folder():
    return current_app.config["DOCUMENTS_FOLDER"]


@documentos_bp.route("/upload_exame", methods=["GET", "POST"])
def upload_exame():
    if normalize_role(session.get("user_role", "")) != "medico":
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        paciente = request.form["paciente"].strip()
        file = request.files.get("arquivo")

        if not paciente or not file or not file.filename:
            flash("Arquivo invalido.")
            return redirect(url_for("documentos.upload_exame"))

        filename = secure_filename(f"{paciente}_{file.filename}")
        filepath = os.path.join(_upload_folder(), filename)
        file.save(filepath)
        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO documents (patient_name, doctor_name, category, doc_type, filename, status, company_id)
            VALUES (?, ?, ?, ?, ?, 'pendente', ?)
            """,
            (
                paciente,
                session.get("user_name"),
                "exame",
                "Exame",
                filename,
                current_company_id(),
            ),
        )
        db.commit()
        _notify_patient(
            db, paciente, "Novo exame disponivel para download.", "exame", cursor.lastrowid
        )
        flash("Exame enviado com sucesso!")
        return redirect(url_for("documentos.upload_exame"))

    return render_template("upload_exame.html")


@documentos_bp.route("/visualizar_documentos")
def visualizar_documentos():
    if "user_name" not in session:
        return redirect(url_for("auth.login"))

    db = get_db()
    role = normalize_role(session.get("user_role", ""))
    params = []
    query = """
        SELECT id, patient_name, doctor_name, category, doc_type, filename, created_at, status
        FROM documents
    """
    filtros = {
        "categoria": request.args.get("categoria", "").strip(),
        "tipo": request.args.get("tipo", "").strip(),
        "paciente": request.args.get("paciente", "").strip(),
        "inicio": request.args.get("inicio", "").strip(),
        "fim": request.args.get("fim", "").strip(),
    }
    if role == "medico":
        query += " WHERE doctor_name = ?"
        params.append(session.get("user_name"))
    elif role == "paciente":
        query += " WHERE patient_name = ?"
        params.append(session.get("user_name"))
    else:
        query += " WHERE 1=1"

    company_id = current_company_id()
    if company_id:
        query += " AND company_id = ?"
        params.append(company_id)

    if filtros["categoria"]:
        query += " AND category = ?"
        params.append(filtros["categoria"])
    if filtros["tipo"]:
        query += " AND doc_type LIKE ?"
        params.append(f"%{filtros['tipo']}%")
    if filtros["paciente"] and role != "paciente":
        query += " AND patient_name LIKE ?"
        params.append(f"%{filtros['paciente']}%")
    if filtros["inicio"]:
        query += " AND date(created_at) >= date(?)"
        params.append(filtros["inicio"])
    if filtros["fim"]:
        query += " AND date(created_at) <= date(?)"
        params.append(filtros["fim"])

    query += " ORDER BY created_at DESC"
    documentos = db.execute(query, params).fetchall()

    return render_template(
        "visualizar_documentos.html", documentos=documentos, filtros=filtros
    )


@documentos_bp.route("/documentos_emitidos")
def documentos_emitidos():
    return visualizar_documentos()


@documentos_bp.route("/download/<nome_arquivo>")
def download_arquivo(nome_arquivo):
    if "user_name" not in session:
        return redirect(url_for("auth.login"))
    db = get_db()
    documento = db.execute(
        "SELECT patient_name, doctor_name, company_id FROM documents WHERE filename = ?",
        (nome_arquivo,),
    ).fetchone()
    if not documento:
        abort(404)

    role = normalize_role(session.get("user_role", ""))
    if current_company_id() and documento["company_id"] != current_company_id():
        abort(403)
    if role == "clinica":
        return _send_document(nome_arquivo)
    if role == "medico" and documento["doctor_name"] == session.get("user_name"):
        return _send_document(nome_arquivo)
    if role == "paciente" and documento["patient_name"] == session.get("user_name"):
        db.execute(
            "UPDATE documents SET patient_seen = 1 WHERE filename = ?",
            (nome_arquivo,),
        )
        db.commit()
        return _send_document(nome_arquivo)
    abort(403)


@documentos_bp.route("/emitir_documento", methods=["GET", "POST"])
def emitir_documento():
    if normalize_role(session.get("user_role", "")) != "medico":
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        paciente = request.form["paciente"]
        tipo = request.form["tipo"]
        conteudo = request.form["conteudo"]

        nome_arquivo = f"{paciente}_{tipo.replace(' ', '_')}.txt"
        caminho = os.path.join(_upload_folder(), nome_arquivo)

        with open(caminho, "w", encoding="utf-8") as arquivo:
            arquivo.write(f"Tipo: {tipo}\n")
            arquivo.write(f"Paciente: {paciente}\n")
            arquivo.write(f"Medico: {session.get('user_name')}\n\n")
            arquivo.write(conteudo)

        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO documents (patient_name, doctor_name, category, doc_type, filename, status, company_id)
            VALUES (?, ?, ?, ?, ?, 'pendente', ?)
            """,
            (
                paciente,
                session.get("user_name"),
                "documento",
                tipo,
                nome_arquivo,
                current_company_id(),
            ),
        )
        db.commit()
        _notify_patient(
            db,
            paciente,
            f"Novo documento emitido: {tipo}.",
            "documento",
            cursor.lastrowid,
        )
        flash("Documento emitido com sucesso!")
        return redirect(url_for("documentos.emitir_documento"))

    return render_template("emitir_documento.html")


@documentos_bp.route("/emitir_atestado", methods=["GET", "POST"])
def emitir_atestado():
    if normalize_role(session.get("user_role", "")) != "medico":
        return redirect(url_for("auth.login"))

    arquivo_gerado = None
    if request.method == "POST":
        paciente = request.form["paciente"].strip()
        dias = request.form["dias"].strip()
        observacoes = request.form["observacoes"].strip()

        if not paciente or not dias:
            flash("Preencha paciente e dias.")
            return render_template("emitir_atestado.html")

        db = get_db()
        medico = db.execute(
            "SELECT nome, crm FROM users WHERE email = ?",
            (session.get("user_email"),),
        ).fetchone()
        crm = medico["crm"] if medico else ""

        nome_arquivo = f"{paciente}_atestado.txt"
        caminho = os.path.join(_upload_folder(), nome_arquivo)
        hoje = datetime.now().strftime("%d/%m/%Y")

        with open(caminho, "w", encoding="utf-8") as arquivo:
            arquivo.write("ATESTADO MEDICO\n")
            arquivo.write(f"Paciente: {paciente}\n")
            arquivo.write(f"Medico: {session.get('user_name')}\n")
            arquivo.write(f"CRM: {crm}\n")
            arquivo.write(f"Data: {hoje}\n")
            arquivo.write(f"Dias de afastamento: {dias}\n\n")
            arquivo.write("Observacoes:\n")
            arquivo.write(observacoes or "-")

        cursor = db.execute(
            """
            INSERT INTO documents (patient_name, doctor_name, category, doc_type, filename, status, company_id)
            VALUES (?, ?, ?, ?, ?, 'pendente', ?)
            """,
            (
                paciente,
                session.get("user_name"),
                "documento",
                "Atestado",
                nome_arquivo,
                current_company_id(),
            ),
        )
        db.commit()
        _notify_patient(
            db,
            paciente,
            "Novo atestado medico disponivel para download.",
            "documento",
            cursor.lastrowid,
        )

        arquivo_gerado = nome_arquivo
        flash("Atestado emitido com sucesso!")

    return render_template("emitir_atestado.html", arquivo_gerado=arquivo_gerado)


@documentos_bp.route("/emitir_receita_assinada", methods=["GET", "POST"])
def emitir_receita_assinada():
    if normalize_role(session.get("user_role", "")) != "medico":
        return redirect(url_for("auth.login"))

    if canvas is None:
        flash("Biblioteca PDF nao instalada. Instale reportlab.")
        return render_template("emitir_receita_assinada.html")

    arquivo_gerado = None
    if request.method == "POST":
        paciente = request.form["paciente"].strip()
        conteudo = request.form["conteudo"].strip()

        if not paciente or not conteudo:
            flash("Preencha paciente e conteudo.")
            return render_template("emitir_receita_assinada.html")

        db = get_db()
        medico = db.execute(
            "SELECT nome, crm FROM users WHERE email = ?",
            (session.get("user_email"),),
        ).fetchone()
        crm = medico["crm"] if medico else ""
        hoje = datetime.now().strftime("%d/%m/%Y %H:%M")

        filename = secure_filename(
            f"{paciente}_receita_assinada_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )
        caminho = os.path.join(_documents_folder(), filename)

        pdf = canvas.Canvas(caminho)
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(72, 780, "Receita Medica - LuminaCare")
        pdf.setFont("Helvetica", 11)
        pdf.drawString(72, 750, f"Paciente: {paciente}")
        pdf.drawString(72, 735, f"Medico: {session.get('user_name')}")
        pdf.drawString(72, 720, f"CRM: {crm}")
        pdf.drawString(72, 705, f"Data: {hoje}")
        pdf.line(72, 695, 540, 695)

        y = 675
        for line in conteudo.splitlines():
            pdf.drawString(72, y, line)
            y -= 16
            if y < 100:
                pdf.showPage()
                y = 780
        pdf.line(72, 120, 360, 120)
        pdf.drawString(72, 100, "Assinatura eletronica")
        pdf.drawString(72, 85, f"{session.get('user_name')} - CRM {crm}")
        pdf.save()

        cursor = db.execute(
            """
            INSERT INTO documents (patient_name, doctor_name, category, doc_type, filename, status, company_id)
            VALUES (?, ?, ?, ?, ?, 'pendente', ?)
            """,
            (
                paciente,
                session.get("user_name"),
                "documento",
                "Receita Assinada",
                filename,
                current_company_id(),
            ),
        )
        db.commit()
        _notify_patient(
            db,
            paciente,
            "Nova receita assinada disponivel para download.",
            "documento",
            cursor.lastrowid,
        )

        arquivo_gerado = filename
        flash("Receita assinada emitida com sucesso!")

    return render_template(
        "emitir_receita_assinada.html", arquivo_gerado=arquivo_gerado
    )


@documentos_bp.route("/solicitar-contato", methods=["GET", "POST"])
def solicitar_contato():
    if request.method == "POST":
        nome = request.form.get("nome")
        email = request.form.get("email")
        mensagem = request.form.get("mensagem")

        db = get_db()
        db.execute(
            """
            INSERT INTO contact_requests (name, email, message, company_id)
            VALUES (?, ?, ?, ?)
            """,
            (nome, email, mensagem, current_company_id()),
        )
        db.commit()
        _notify_clinic(db, "Nova solicitacao de contato recebida.")

        flash("Solicitacao de contato enviada com sucesso!", "success")
        return redirect(url_for("documentos.solicitar_contato"))

    return render_template("solicitar_contato.html")


@documentos_bp.route("/documentos/<int:doc_id>", methods=["GET", "POST"])
def detalhe_documento(doc_id):
    if "user_name" not in session:
        return redirect(url_for("auth.login"))

    db = get_db()
    documento = db.execute(
        """
        SELECT id, patient_name, doctor_name, category, doc_type, filename, created_at, status, company_id
        FROM documents
        WHERE id = ?
        """,
        (doc_id,),
    ).fetchone()
    if not documento:
        abort(404)

    if current_company_id() and documento["company_id"] != current_company_id():
        abort(403)

    if not _can_access_document(session, documento):
        abort(403)

    if request.method == "POST":
        body = request.form.get("comentario", "").strip()
        if body:
            recipient_role = (
                "medico"
                if normalize_role(session.get("user_role", "")) == "paciente"
                else "paciente"
            )
            db.execute(
                """
                INSERT INTO comments (
                    document_id, author_name, author_role, body, recipient_role, company_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    session.get("user_name"),
                    session.get("user_role", ""),
                    body,
                    recipient_role,
                    current_company_id(),
                ),
            )
            db.commit()
            _notify_document_owner(db, documento, session)
        return redirect(url_for("documentos.detalhe_documento", doc_id=doc_id))

    try:
        db.execute(
            """
            UPDATE comments
            SET is_read = 1
            WHERE document_id = ? AND author_name != ?
            """,
            (doc_id, session.get("user_name")),
        )
        db.commit()
    except Exception:
        pass

    if normalize_role(session.get("user_role", "")) == "paciente":
        db.execute(
            "UPDATE documents SET patient_seen = 1 WHERE id = ?",
            (doc_id,),
        )
        db.commit()

    params = [doc_id]
    query = """
        SELECT author_name, author_role, body, created_at, is_read
        FROM comments
        WHERE document_id = ?
    """
    if current_company_id():
        query += " AND (company_id IS NULL OR company_id = ?)"
        params.append(current_company_id())
    query += " ORDER BY created_at DESC"
    comentarios = db.execute(query, params).fetchall()

    return render_template(
        "documento_detalhe.html", documento=documento, comentarios=comentarios
    )


@documentos_bp.route("/historico_medico")
def historico_medico():
    if normalize_role(session.get("user_role", "")) != "medico":
        return redirect(url_for("auth.login"))

    db = get_db()
    filtros = {
        "categoria": request.args.get("categoria", "").strip(),
        "tipo": request.args.get("tipo", "").strip(),
        "paciente": request.args.get("paciente", "").strip(),
        "inicio": request.args.get("inicio", "").strip(),
        "fim": request.args.get("fim", "").strip(),
    }
    params = [session.get("user_name")]
    query = """
        SELECT id, patient_name, category, doc_type, filename, created_at, status
        FROM documents
        WHERE doctor_name = ?
    """
    company_id = current_company_id()
    if company_id:
        query += " AND company_id = ?"
        params.append(company_id)
    if filtros["categoria"]:
        query += " AND category = ?"
        params.append(filtros["categoria"])
    if filtros["tipo"]:
        query += " AND doc_type LIKE ?"
        params.append(f"%{filtros['tipo']}%")
    if filtros["paciente"]:
        query += " AND patient_name LIKE ?"
        params.append(f"%{filtros['paciente']}%")
    if filtros["inicio"]:
        query += " AND date(created_at) >= date(?)"
        params.append(filtros["inicio"])
    if filtros["fim"]:
        query += " AND date(created_at) <= date(?)"
        params.append(filtros["fim"])
    query += " ORDER BY created_at DESC"

    documentos = db.execute(query, params).fetchall()

    return render_template(
        "medico_historico.html", documentos=documentos, filtros=filtros
    )


def _notify_patient(db, patient_name, message, notif_type, document_id):
    params = [patient_name]
    query = "SELECT email FROM users WHERE nome = ?"
    if current_company_id():
        query += " AND company_id = ?"
        params.append(current_company_id())
    query += " ORDER BY id LIMIT 1"
    row = db.execute(query, params).fetchone()
    if row:
        db.execute(
            """
            INSERT INTO notifications (user_email, message, type, document_id, company_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (row["email"], message, notif_type, document_id, current_company_id()),
        )
        db.commit()


def _notify_document_owner(db, documento, session_data):
    role = normalize_role(session_data.get("user_role", ""))
    if role == "medico":
        target_name = documento["patient_name"]
    else:
        target_name = documento["doctor_name"]

    params = [target_name]
    query = "SELECT email FROM users WHERE nome = ?"
    if current_company_id():
        query += " AND company_id = ?"
        params.append(current_company_id())
    query += " ORDER BY id LIMIT 1"
    row = db.execute(query, params).fetchone()
    if row:
        db.execute(
            """
            INSERT INTO notifications (user_email, message, type, document_id, company_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                row["email"],
                "Novo comentario em um documento.",
                "comentario",
                documento["id"],
                current_company_id(),
            ),
        )
        db.commit()


def _can_access_document(session_data, documento):
    role = normalize_role(session_data.get("user_role", ""))
    if role == "clinica":
        return True
    if role == "medico" and documento["doctor_name"] == session_data.get("user_name"):
        return True
    if role == "paciente" and documento["patient_name"] == session_data.get("user_name"):
        return True
    return False


@documentos_bp.route("/documentos/status/<int:doc_id>", methods=["POST"])
def atualizar_status(doc_id):
    if normalize_role(session.get("user_role", "")) != "medico":
        return redirect(url_for("auth.login"))

    novo_status = request.form.get("status", "").strip().lower()
    if novo_status not in {"pendente", "laudado", "entregue"}:
        return redirect(url_for("documentos.historico_medico"))

    db = get_db()
    documento = db.execute(
        "SELECT id, patient_name, doctor_name, company_id FROM documents WHERE id = ?",
        (doc_id,),
    ).fetchone()
    if not documento or documento["doctor_name"] != session.get("user_name"):
        abort(403)
    if current_company_id() and documento["company_id"] != current_company_id():
        abort(403)

    db.execute(
        "UPDATE documents SET status = ?, patient_seen = 0 WHERE id = ?",
        (novo_status, doc_id),
    )
    db.commit()
    _notify_patient(
        db,
        documento["patient_name"],
        f"Status atualizado: {novo_status}.",
        "status",
        doc_id,
    )
    return redirect(url_for("documentos.historico_medico"))


@documentos_bp.route("/paciente/timeline")
def timeline_paciente():
    if normalize_role(session.get("user_role", "")) != "paciente":
        return redirect(url_for("auth.login"))

    db = get_db()
    documentos = db.execute(
        """
        SELECT id, doctor_name, category, doc_type, filename, created_at, status
        FROM documents
        WHERE patient_name = ? AND (company_id IS NULL OR company_id = ?)
        ORDER BY created_at DESC
        """,
        (session.get("user_name"), current_company_id()),
    ).fetchall()

    consultas = db.execute(
        """
        SELECT id, doctor_name, date, time, tipo, status
        FROM appointments
        WHERE patient_name = ? AND (company_id IS NULL OR company_id = ?)
        ORDER BY date DESC, time DESC
        """,
        (session.get("user_name"), current_company_id()),
    ).fetchall()

    return render_template(
        "paciente_timeline.html", documentos=documentos, consultas=consultas
    )


@documentos_bp.route("/solicitacoes_contato")
def solicitacoes_contato():
    if normalize_role(session.get("user_role", "")) != "clinica":
        return redirect(url_for("auth.login"))

    db = get_db()
    params = []
    query = """
        SELECT id, name, email, message, created_at
        FROM contact_requests
        WHERE 1=1
    """
    if current_company_id():
        query += " AND company_id = ?"
        params.append(current_company_id())
    query += " ORDER BY created_at DESC"
    solicitacoes = db.execute(query, params).fetchall()

    return render_template("solicitacoes_contato.html", solicitacoes=solicitacoes)


def _notify_clinic(db, message):
    params = ["Clinica/Admin", "Cl\u00c3\u00adnica/Admin"]
    query = """
        SELECT email FROM users
        WHERE perfil IN (?, ?)
    """
    if current_company_id():
        query += " AND company_id = ?"
        params.append(current_company_id())
    admins = db.execute(query, params).fetchall()
    for admin in admins:
        db.execute(
            """
            INSERT INTO notifications (user_email, message, type, company_id)
            VALUES (?, ?, ?, ?)
            """,
            (admin["email"], message, "contato", current_company_id()),
        )
    db.commit()


def _send_document(nome_arquivo):
    upload_path = os.path.join(_upload_folder(), nome_arquivo)
    documents_path = os.path.join(_documents_folder(), nome_arquivo)
    if os.path.exists(upload_path):
        return send_file(upload_path, as_attachment=True)
    if os.path.exists(documents_path):
        return send_file(documents_path, as_attachment=True)
    abort(404)
