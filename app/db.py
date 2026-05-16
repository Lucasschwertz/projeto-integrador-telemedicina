import sqlite3

from flask import current_app, g


def get_db():
    if "db" not in g:
        db_path = current_app.config["DB_PATH"]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            perfil TEXT NOT NULL,
            cpf_cnpj TEXT NOT NULL,
            crm TEXT,
            company_id INTEGER,
            telefone TEXT,
            sexo TEXT,
            data_nascimento TEXT,
            rua TEXT,
            numero TEXT,
            complemento TEXT,
            cidade TEXT,
            estado TEXT,
            cep TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cnpj TEXT NOT NULL,
            plano TEXT NOT NULL,
            status TEXT NOT NULL,
            subdomain TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            doctor_name TEXT NOT NULL,
            category TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            filename TEXT NOT NULL,
            company_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            author_name TEXT NOT NULL,
            author_role TEXT NOT NULL,
            body TEXT NOT NULL,
            company_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS contact_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            message TEXT NOT NULL,
            company_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            company_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _ensure_column(db, "comments", "is_read", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(db, "comments", "recipient_role", "TEXT")
    _ensure_column(db, "comments", "company_id", "INTEGER")
    _ensure_column(db, "notifications", "type", "TEXT")
    _ensure_column(db, "notifications", "document_id", "INTEGER")
    _ensure_column(db, "notifications", "company_id", "INTEGER")
    _ensure_column(db, "documents", "status", "TEXT NOT NULL DEFAULT 'pendente'")
    _ensure_column(db, "documents", "patient_seen", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(db, "users", "crm", "TEXT")
    _ensure_column(db, "users", "company_id", "INTEGER")
    _ensure_column(db, "documents", "company_id", "INTEGER")
    _ensure_column(db, "contact_requests", "company_id", "INTEGER")
    _ensure_column(db, "availability", "company_id", "INTEGER")
    _ensure_column(db, "appointments", "company_id", "INTEGER")
    _ensure_column(db, "appointments", "pago", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(db, "appointments", "payment_status", "TEXT")
    _ensure_column(db, "appointments", "payment_link", "TEXT")
    _ensure_column(db, "appointments", "payment_provider", "TEXT")
    _ensure_column(db, "appointments", "payment_external_id", "TEXT")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS availability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_name TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            tipo TEXT NOT NULL,
            company_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_name TEXT NOT NULL,
            patient_name TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            tipo TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'agendado',
            pago INTEGER NOT NULL DEFAULT 0,
            payment_status TEXT,
            payment_link TEXT,
            payment_provider TEXT,
            payment_external_id TEXT,
            company_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Procurement prototype tables (SQLite) to support Inbox MVP.
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            external_id TEXT,
            tax_id TEXT,
            risk_flags TEXT NOT NULL DEFAULT '{"no_supplier_response": false, "late_delivery": false, "sla_breach": false}',
            company_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT,
            status TEXT NOT NULL DEFAULT 'pending_rfq' CHECK (
                status IN ('pending_rfq','in_rfq','awarded','ordered','partially_received','received','cancelled')
            ),
            priority TEXT NOT NULL DEFAULT 'medium' CHECK (
                priority IN ('low','medium','high','urgent')
            ),
            requested_by TEXT,
            department TEXT,
            needed_at TEXT,
            external_id TEXT,
            company_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS rfqs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft','open','collecting_quotes','closed','awarded','cancelled')
            ),
            cancel_reason TEXT,
            company_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft','approved','sent_to_erp','erp_accepted','partially_received','received','cancelled','erp_error')
            ),
            erp_last_error TEXT,
            external_id TEXT,
            company_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS integration_watermarks (
            company_id INTEGER,
            system TEXT NOT NULL DEFAULT 'senior',
            entity TEXT NOT NULL CHECK (
                entity IN ('purchase_requests','rfqs','purchase_orders','receipts','suppliers','categories')
            ),
            last_success_at TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (company_id, system, entity)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            system TEXT NOT NULL DEFAULT 'senior',
            scope TEXT NOT NULL CHECK (
                scope IN ('purchase_requests','rfqs','purchase_orders','receipts','suppliers','categories')
            ),
            status TEXT NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 1,
            parent_sync_run_id INTEGER,
            payload_ref TEXT,
            payload_hash TEXT,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            duration_ms INTEGER,
            records_in INTEGER NOT NULL DEFAULT 0,
            records_upserted INTEGER NOT NULL DEFAULT 0,
            records_failed INTEGER NOT NULL DEFAULT 0,
            error_summary TEXT,
            error_details TEXT,
            company_id INTEGER
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS status_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT NOT NULL CHECK (
                entity IN ('purchase_request','rfq','award','purchase_order','receipt')
            ),
            entity_id INTEGER NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            reason TEXT,
            actor_user_id INTEGER,
            occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            company_id INTEGER
        )
        """
    )

    # Automatic updated_at maintenance for procurement prototype tables.
    db.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS trg_suppliers_updated_at
        AFTER UPDATE ON suppliers
        FOR EACH ROW
        BEGIN
            UPDATE suppliers SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_purchase_requests_updated_at
        AFTER UPDATE ON purchase_requests
        FOR EACH ROW
        BEGIN
            UPDATE purchase_requests SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_rfqs_updated_at
        AFTER UPDATE ON rfqs
        FOR EACH ROW
        BEGIN
            UPDATE rfqs SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_purchase_orders_updated_at
        AFTER UPDATE ON purchase_orders
        FOR EACH ROW
        BEGIN
            UPDATE purchase_orders SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_integration_watermarks_updated_at
        AFTER UPDATE ON integration_watermarks
        FOR EACH ROW
        BEGIN
            UPDATE integration_watermarks
            SET updated_at = CURRENT_TIMESTAMP
            WHERE company_id IS NEW.company_id AND system = NEW.system AND entity = NEW.entity;
        END;
        """
    )

    db.commit()


def _ensure_column(db, table, column, definition):
    try:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError:
        return
