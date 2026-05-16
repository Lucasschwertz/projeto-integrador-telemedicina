import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
    DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "database", "plataforma.db"))
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(BASE_DIR, "database", "uploads")
    )
    DOCUMENTS_FOLDER = os.environ.get(
        "DOCUMENTS_FOLDER", os.path.join(BASE_DIR, "database", "documentos")
    )
    REPORTS_FOLDER = os.environ.get(
        "REPORTS_FOLDER", os.path.join(BASE_DIR, "database", "relatorios")
    )
    MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "")
    MP_ACCESS_TOKEN_TEST = os.environ.get("MP_ACCESS_TOKEN_TEST", "")
    MP_ENV = os.environ.get("MP_ENV", "test")
    PAYMENT_WEBHOOK_TOKEN = os.environ.get("PAYMENT_WEBHOOK_TOKEN", "change-me")
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://luminacare.local:5000")
    PAYMENT_TEST_MODE = os.environ.get("PAYMENT_TEST_MODE", "0") == "1"
    MASTER_ADMIN_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "")
