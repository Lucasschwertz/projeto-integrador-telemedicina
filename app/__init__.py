import os

from flask import Flask, session, request, g, current_app

from app.config import Config
from app.db import close_db, get_db
from app.tenant import current_company_name


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    _ensure_uploads(app)
    _register_blueprints(app)
    _register_context(app)
    _register_tenant(app)
    app.teardown_appcontext(close_db)

    return app


def _register_blueprints(app):
    from app.routes.auth_routes import auth_bp
    from app.routes.agenda_routes import agenda_bp
    from app.routes.consulta_routes import consulta_bp
    from app.routes.pagamento_routes import pagamento_bp
    from app.routes.relatorios_routes import relatorios_bp
    from app.routes.empresas_routes import empresas_bp
    from app.routes.dashboard_routes import dashboard_bp
    from app.routes.documentos_routes import documentos_bp
    from app.routes.especialidades_routes import especialidade_bp
    from app.routes.home_routes import home_bp
    from app.routes.notifications_routes import notifications_bp
    from app.routes.perfil_routes import perfil_bp
    from app.routes.usuarios_routes import usuarios_bp
    from app.routes.procurement_routes import procurement_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(agenda_bp)
    app.register_blueprint(consulta_bp)
    app.register_blueprint(pagamento_bp)
    app.register_blueprint(relatorios_bp)
    app.register_blueprint(empresas_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(documentos_bp)
    app.register_blueprint(perfil_bp)
    app.register_blueprint(usuarios_bp)
    app.register_blueprint(especialidade_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(procurement_bp)


def _ensure_uploads(app):
    upload_folder = app.config.get("UPLOAD_FOLDER")
    documents_folder = app.config.get("DOCUMENTS_FOLDER")
    reports_folder = app.config.get("REPORTS_FOLDER")
    if upload_folder:
        os.makedirs(upload_folder, exist_ok=True)
    if documents_folder:
        os.makedirs(documents_folder, exist_ok=True)
    if reports_folder:
        os.makedirs(reports_folder, exist_ok=True)


def _register_context(app):
    @app.context_processor
    def inject_notifications():
        if "user_email" not in session:
            return {}
        db = get_db()
        try:
            unread = db.execute(
                "SELECT COUNT(*) FROM notifications WHERE user_email = ? AND is_read = 0",
                (session["user_email"],),
            ).fetchone()[0]
        except Exception:
            unread = 0
        master_email = current_app.config.get("MASTER_ADMIN_EMAIL", "")
        return {
            "notifications_unread": unread,
            "company_name": current_company_name(),
            "is_master_admin": session.get("user_email") == master_email if master_email else False,
        }


def _register_tenant(app):
    @app.before_request
    def load_company():
        host = request.host.split(":")[0]
        parts = host.split(".")
        subdomain = None
        if len(parts) >= 3 and host.endswith("luminacare.local"):
            subdomain = parts[0]
        if not subdomain:
            g.company_id = None
            g.company_name = None
            return

        db = get_db()
        empresa = db.execute(
            "SELECT id, nome FROM empresas WHERE subdomain = ?",
            (subdomain,),
        ).fetchone()
        if empresa:
            g.company_id = empresa["id"]
            g.company_name = empresa["nome"]
        else:
            g.company_id = None
            g.company_name = None
