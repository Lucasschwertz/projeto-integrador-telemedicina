from __future__ import annotations

from typing import List, Tuple

from flask import Blueprint, jsonify, request

from app.db import get_db
from app.tenant import current_company_id


procurement_bp = Blueprint("procurement", __name__)


@procurement_bp.route("/api/procurement/inbox", methods=["GET"])
def procurement_inbox():
    """Operational inbox prototype for procurement flows.

    This endpoint is intentionally simple and SQLite-friendly. It mirrors the
    enterprise inbox logic but uses `company_id` as the tenant boundary.
    """
    db = get_db()
    company_id = current_company_id()

    limit = _parse_int(request.args.get("limit"), default=50, min_value=1, max_value=200)
    offset = _parse_int(request.args.get("offset"), default=0, min_value=0, max_value=10_000)

    cards = _load_inbox_cards(db, company_id)
    items = _load_inbox_items(db, company_id, limit, offset)

    has_more = len(items) == limit
    return jsonify(
        {
            "items": items,
            "kpis": cards,
            "paging": {
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
            },
        }
    )


def _load_inbox_cards(db, company_id: int | None) -> dict:
    company_filter, company_params = _company_filter(company_id, occurrences=4)
    sql = f"""
        SELECT
            (
                SELECT COUNT(*)
                FROM purchase_requests
                WHERE status = 'pending_rfq' AND {company_filter}
            ) AS pending_rfq,
            (
                SELECT COUNT(*)
                FROM rfqs
                WHERE status IN ('open','collecting_quotes') AND {company_filter}
            ) AS awaiting_quotes,
            (
                SELECT COUNT(*)
                FROM rfqs
                WHERE status = 'awarded' AND {company_filter}
            ) AS awarded_waiting_po,
            (
                SELECT COUNT(*)
                FROM purchase_orders
                WHERE status IN ('draft','approved','erp_error') AND {company_filter}
            ) AS awaiting_erp_push
    """
    row = db.execute(sql, tuple(company_params)).fetchone()
    return {
        "pending_rfq": row["pending_rfq"] if row else 0,
        "awaiting_quotes": row["awaiting_quotes"] if row else 0,
        "awarded_waiting_po": row["awarded_waiting_po"] if row else 0,
        "awaiting_erp_push": row["awaiting_erp_push"] if row else 0,
    }


def _load_inbox_items(db, company_id: int | None, limit: int, offset: int) -> List[dict]:
    company_filter, company_params = _company_filter(company_id, occurrences=3)
    sql = f"""
        WITH pr_pending AS (
            SELECT
                id,
                'purchase_request' AS type,
                number AS ref,
                status,
                priority,
                needed_at,
                updated_at,
                CAST(MAX(0, julianday('now') - julianday(created_at)) AS INTEGER) AS age_days
            FROM purchase_requests
            WHERE status IN ('pending_rfq','in_rfq') AND {company_filter}
        ),
        rfq_open AS (
            SELECT
                id,
                'rfq' AS type,
                COALESCE(title, CAST(id AS TEXT)) AS ref,
                status,
                NULL AS priority,
                NULL AS needed_at,
                updated_at,
                CAST(MAX(0, julianday('now') - julianday(created_at)) AS INTEGER) AS age_days
            FROM rfqs
            WHERE status IN ('open','collecting_quotes','awarded') AND {company_filter}
        ),
        po_pending_push AS (
            SELECT
                id,
                'purchase_order' AS type,
                COALESCE(number, CAST(id AS TEXT)) AS ref,
                status,
                NULL AS priority,
                NULL AS needed_at,
                updated_at,
                CAST(MAX(0, julianday('now') - julianday(created_at)) AS INTEGER) AS age_days
            FROM purchase_orders
            WHERE status IN ('draft','approved','erp_error') AND {company_filter}
        )
        SELECT *
        FROM (
            SELECT * FROM pr_pending
            UNION ALL
            SELECT * FROM rfq_open
            UNION ALL
            SELECT * FROM po_pending_push
        ) inbox
        ORDER BY
            CASE priority
                WHEN 'urgent' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
                ELSE 5
            END,
            needed_at IS NULL,
            needed_at,
            updated_at DESC
        LIMIT ? OFFSET ?
    """

    params: List[object] = [*company_params, limit, offset]
    rows = db.execute(sql, tuple(params)).fetchall()

    items: List[dict] = []
    for row in rows:
        items.append(
            {
                "type": row["type"],
                "id": row["id"],
                "ref": row["ref"],
                "status": row["status"],
                "priority": row["priority"],
                "needed_at": row["needed_at"],
                "age_days": row["age_days"],
                "updated_at": row["updated_at"],
            }
        )
    return items


def _company_filter(company_id: int | None, occurrences: int) -> Tuple[str, List[int]]:
    if not company_id:
        return "1=1", []
    return "(company_id IS NULL OR company_id = ?)", [company_id] * occurrences


def _parse_int(value: str | None, default: int, min_value: int, max_value: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(min_value, min(parsed, max_value))