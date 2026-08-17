# app/services/bot_invoice.py
"""Creación del invoice desde el bot — COMPARTIDA por el flujo estático y el
modo AI, para que el resultado sea idéntico venga de donde venga.

Datos de entrada (dict `data`, ya validados):
    name, address, amount (float), catastro?, email?, is_pay (bool),
    qty? (default 1), sale_tax? (default 0), date? (YYYY-MM-DD, default hoy)

Mapeo al invoice (alineado con InvoiceModal.tsx del frontend):
    name      → i_billto
    address   → id_adress   (lo que el PDF imprime en "Located at:")
    amount    → id_rate ; id_qty = 1 ; i_total calculado en Python
    catastro  → id_description = "Appraisal Report - Catastro <catastro>"
                (sin catastro → "Appraisal Report"). Además se guarda en
                i_inscription NO: i_inscription es la licencia del EMISOR.
    email     → i_email si lo dieron; si no, el del emisor (no se imprime)
    is_pay    → i_is_pay (sello PAID)
    emisor    → i_name / i_inscription / i_address hardcodeados = frontend
"""
from datetime import date

from app.schemas.invoices import InvoiceCreate
from app.services import telegram_client
from app.services.bot_parser import build_description, parse_amount
from app.services.invoice_service import (
    create_invoice_for_user,
    generate_invoice_pdf,
    get_next_serie_for_user,
)

# --- Constantes del emisor (idénticas a InvoiceModal.tsx::handleSubmit) -----
ISSUER_NAME = "Raimundo Marrero - TASADOR"
ISSUER_INSCRIPTION = "EPA 780 -CGA 195"
ISSUER_EMAIL = "raimundo.marrero2@gmail.com"
ISSUER_ADDRESS = "Cond. El Centro | 500 Muñoz Rivera Ste 301 San Juan, PR 00918"


def build_invoice_fields(data: dict, today: str | None = None) -> dict:
    """Función PURA: dict del bot → kwargs de InvoiceCreate (sin i_serie)."""
    today = today or date.today().isoformat()

    qty = float(data.get("qty") or 1)
    amount = data.get("amount")
    if not isinstance(amount, (int, float)):
        amount = parse_amount(str(amount)) or 0.0
    rate = float(amount)
    sale_tax = float(data.get("sale_tax") or 0)

    description = build_description(data.get("catastro"))
    i_date = (data.get("date") or "").strip() or today
    total = round(qty * rate + sale_tax, 2)

    client_email = (data.get("email") or "").strip() or ISSUER_EMAIL

    return {
        "i_name": ISSUER_NAME,
        "i_inscription": ISSUER_INSCRIPTION,
        "i_email": client_email,
        "i_address": ISSUER_ADDRESS,
        "i_billto": (data.get("name") or "").strip(),
        "i_date": i_date,
        "i_total": total,
        "i_is_pay": bool(data.get("is_pay", False)),
        "details": [
            {
                "id_number": 1,
                "id_description": description,
                "id_qty": qty,
                "id_rate": rate,
                "id_sale_tax": sale_tax,
                "id_adress": (data.get("address") or "").strip(),
                "id_adress2": "",
            }
        ],
    }


def create_from_bot_data(u_id: str, data: dict) -> tuple[dict, bytes, str]:
    """Crea el invoice real y genera su PDF.

    Devuelve (fields, pdf_bytes, serie). Deja propagar excepciones (Supabase,
    validación Pydantic, PDF) para que el caller avise al chat sin perder la
    sesión.
    """
    today = date.today()
    serie = get_next_serie_for_user(u_id, today)
    fields = build_invoice_fields(data, today.isoformat())
    fields["i_serie"] = serie
    invoice = InvoiceCreate(**fields)
    created = create_invoice_for_user(u_id, invoice)  # dict con i_id
    pdf_bytes, _row = generate_invoice_pdf(created["i_id"])
    return fields, pdf_bytes, serie


def format_caption(serie: str, total: float, is_pay: bool) -> str:
    estado = "Pagado" if is_pay else "Pendiente"
    return f"✅ Invoice {serie} creado — Total ${total:,.2f} — {estado}"


async def create_and_send(chat_id: int, u_id: str, data: dict) -> bool:
    """Crea el invoice y manda el PDF al chat. Devuelve True si el invoice se
    creó (aunque falle el envío del PDF), False si NO se creó."""
    try:
        fields, pdf_bytes, serie = create_from_bot_data(u_id, data)
    except Exception as exc:
        print(f"[bot] error creando invoice: {exc}")
        await telegram_client.send_message(
            chat_id,
            f"⚠️ Hubo un error creando el invoice: {exc}\n"
            "Tus datos siguen guardados: responde \"sí\" para reintentar o /cancelar.",
        )
        return False

    total = fields["i_total"]
    caption = format_caption(serie, total, fields["i_is_pay"])
    try:
        await telegram_client.send_document(
            chat_id, pdf_bytes, f"invoice_{serie}.pdf", caption=caption
        )
    except Exception as exc:
        # El invoice YA existe; solo falló el envío del archivo.
        print(f"[bot] invoice {serie} creado pero falló enviar el PDF: {exc}")
        await telegram_client.send_message(
            chat_id,
            f"✅ Invoice {serie} creado (Total ${total:,.2f}), pero no pude enviar "
            "el PDF. Está disponible en el dashboard.",
        )
    return True
