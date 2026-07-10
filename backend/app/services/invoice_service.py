# app/services/invoice_service.py
"""Shared invoice logic used by the HTTP routes and (later) the Telegram bot.

Extracted verbatim from ``routes_invoices.py`` (Fase A). Behavior must stay
identical: same RPC calls, same params, same fallbacks, same PDF context. The
functions here are transport-agnostic except ``generate_invoice_pdf``, which
preserves the exact ``HTTPException`` messages/status codes the endpoint used
to raise so the API contract does not change; the bot catches errors broadly.
"""
from datetime import date

from fastapi import HTTPException, status

from app.db.supabase_client import supabase
from app.core.templates import render_template
from app.core.pdf import html_to_pdf_bytes
from app.schemas.invoices import InvoiceCreate


def build_next_serie(last_serie: str | None, serie_date: date) -> str:
    date_prefix = serie_date.isoformat()
    fallback = f"{date_prefix}-001"

    if not last_serie:
        return fallback

    parts = last_serie.rsplit("-", 1)
    if len(parts) != 2:
        return fallback

    prefix, number = parts
    if prefix != date_prefix or not number.isdigit():
        return fallback

    next_number = int(number) + 1
    width = max(3, len(number))
    return f"{prefix}-{str(next_number).zfill(width)}"


def create_invoice_for_user(u_id: str, invoice: InvoiceCreate) -> dict:
    """Create an invoice + its details for ``u_id`` and return the raw RPC row.

    Mirrors the old ``create_invoice`` body. The RPC call is left un-wrapped so
    the caller decides how to surface failures (the HTTP route maps them to a
    500 with ``Error creating invoice: ...``).
    """
    details_json = [
        {
            "id_number": d.id_number,
            "id_description": d.id_description,
            "id_qty": d.id_qty,
            "id_rate": d.id_rate,
            "id_sale_tax": d.id_sale_tax,
            "id_adress": d.id_adress,
            "id_adress2": d.id_adress2,
        }
        for d in invoice.details
    ]

    resp = supabase.rpc(
        "fn_invoice_create_with_details",
        {
            "p_name": invoice.i_name,
            "p_inscription": invoice.i_inscription,
            "p_email": invoice.i_email,
            "p_address": invoice.i_address,
            "p_serie": invoice.i_serie,
            "p_date": str(invoice.i_date),
            "p_billto": invoice.i_billto,
            "p_total": invoice.i_total,
            "p_is_pay": invoice.i_is_pay,
            "p_u_id": u_id,
            "p_details": details_json,
        },
    ).execute()

    return resp.data


def get_next_serie_for_user(u_id: str, serie_date: date) -> str:
    """Compute the next invoice serie for ``u_id`` on ``serie_date``.

    Mirrors the old ``get_next_invoice_serie`` logic including the
    ``fn_invoices_list_for_serie`` -> ``fn_invoices_list`` fallback. If both
    RPCs fail the (second) exception propagates for the caller to map to a 500.
    """
    try:
        resp = supabase.rpc(
            "fn_invoices_list_for_serie",
            {"p_u_id": u_id},
        ).execute()
    except Exception:
        resp = supabase.rpc(
            "fn_invoices_list",
            {"p_u_id": u_id},
        ).execute()

    latest_invoice = (resp.data or [None])[0]
    latest_serie = latest_invoice.get("i_serie") if latest_invoice else None

    return build_next_serie(latest_serie, serie_date)


def generate_invoice_pdf(invoice_id: str) -> tuple[bytes, dict]:
    """Render the invoice PDF and return ``(pdf_bytes, invoice_row)``.

    Steps 1-5 of the old ``get_invoice_pdf`` (fetch invoice + details, build the
    template context, render ``_invoice.html``, convert to PDF). It does **not**
    enforce ownership — that stays in the HTTP route, which knows the caller.
    Error handling matches the original endpoint exactly (same status codes and
    detail strings) so the API contract is unchanged.
    """
    # 1. Obtener la invoice (header) desde Supabase
    try:
        invoice_resp = supabase.rpc(
            "fn_invoices_get_by_id",
            {"p_i_id": invoice_id},
        ).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching invoice: {exc}",
        ) from exc

    invoice = invoice_resp.data
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    # 2. Obtener los detalles de la invoice
    try:
        details_resp = supabase.rpc(
            "fn_invoice_details_list_by_invoice",
            {"p_id_id": invoice_id},
        ).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching invoice details: {exc}",
        ) from exc

    details = details_resp.data or []

    # 3. Preparar contexto para el template (usa _invoice.html)
    context = {
        "invoice": invoice,
        "details": details,
        "i_total": invoice.get("i_total", 0),
        "i_serie": invoice.get("i_serie", ""),
        "i_date": invoice.get("i_date", ""),
        "i_billto": invoice.get("i_billto", ""),
        "i_name": invoice.get("i_name", ""),
        "i_inscription": invoice.get("i_inscription", ""),
        "i_email": invoice.get("i_email", ""),
        "i_address": invoice.get("i_address", ""),
    }

    # 4. Renderizar HTML desde el template
    html = render_template("_invoice.html", context)

    # 5. Convertir HTML a PDF
    try:
        pdf_bytes = html_to_pdf_bytes(html)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    return pdf_bytes, invoice
