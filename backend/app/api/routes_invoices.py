# app/api/routes_invoices.py
from fastapi import APIRouter, Depends, HTTPException, status
from app.db.supabase_client import supabase
from app.api.deps import get_current_user_id
from app.schemas.invoices import (
    InvoiceCreate,
    InvoiceDetailRead,
    InvoiceRead,
    InvoiceSummaryRead,
    InvoiceWithDetailsRead,
)
from fastapi.responses import Response
from app.services.invoice_service import (
    create_invoice_for_user,
    get_next_serie_for_user,
    generate_invoice_pdf,
)
from datetime import date

router = APIRouter(prefix="/invoices", tags=["invoices"])


def build_invoice_read(data: dict) -> InvoiceRead:
    return InvoiceRead(
        i_id=data["i_id"],
        i_name=data["i_name"],
        i_inscription=data["i_inscription"],
        i_email=data["i_email"],
        i_address=data["i_address"],
        i_serie=data["i_serie"],
        i_date=data["i_date"],
        i_billto=data["i_billto"],
        i_total=float(data["i_total"]),
        i_is_pay=bool(data.get("i_is_pay", False)),
        i_is_deleted=bool(data.get("i_is_deleted", False)),
        i_u_id=data["i_u_id"],
        i_create_at=data["i_create_at"],
    )


def build_detail_read(data: dict) -> InvoiceDetailRead:
    return InvoiceDetailRead(
        id_number=data["id_number"],
        id_description=data["id_description"],
        id_qty=float(data["id_qty"]),
        id_rate=float(data["id_rate"]),
        id_sale_tax=float(data["id_sale_tax"] or 0),
        id_adress=data["id_adress"],
        id_adress2=data["id_adress2"],
        id_id=data["id_id"],
        id_create_at=data["id_create_at"],
    )


def build_invoice_summary(data: dict | None) -> InvoiceSummaryRead:
    data = data or {}
    return InvoiceSummaryRead(
        total=float(data.get("total") or 0),
        total_year=float(data.get("total_year") or 0),
        total_month=float(data.get("total_month") or 0),
        total_last_month=float(data.get("total_last_month") or 0),
    )


@router.post("/", response_model=InvoiceRead)
async def create_invoice(
    invoice: InvoiceCreate,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        data = create_invoice_for_user(current_user_id, invoice)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating invoice: {exc}",
        ) from exc

    return build_invoice_read(data)


@router.get("/", response_model=list[InvoiceRead])
async def list_invoices(
    current_user_id: str = Depends(get_current_user_id),
):
    # App de un solo negocio: se listan TODOS los invoices (sin filtrar por
    # usuario), sin importar si los creó la web o el bot. p_u_id=None => todos.
    try:
        resp = supabase.rpc(
            "fn_invoices_list",
            {"p_u_id": None},
        ).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing invoices: {exc}",
        ) from exc

    invoices = []
    for item in resp.data:
        invoices.append(build_invoice_read(item))

    return invoices


@router.get("/summary", response_model=InvoiceSummaryRead)
async def get_invoices_summary(
    current_user_id: str = Depends(get_current_user_id),
):
    # Totales sobre TODOS los invoices (p_u_id=None), igual que el listado.
    try:
        resp = supabase.rpc(
            "fn_invoices_summary",
            {"p_u_id": None},
        ).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching invoice summary: {exc}",
        ) from exc

    data = resp.data
    if isinstance(data, list):
        data = data[0] if data else None

    return build_invoice_summary(data)


@router.get("/next-serie")
async def get_next_invoice_serie(
    serie_date: date | None = None,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        serie = get_next_serie_for_user(current_user_id, serie_date or date.today())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching next invoice serie: {exc}",
        ) from exc

    return {"i_serie": serie}


@router.get("/{invoice_id}", response_model=InvoiceWithDetailsRead)
async def get_invoice(
    invoice_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
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

    # Sin chequeo de dueño: un solo negocio, todos ven/usan todos los invoices.

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

    return InvoiceWithDetailsRead(
        **build_invoice_read(invoice).dict(),
        details=[build_detail_read(item) for item in details_resp.data or []],
    )


@router.put("/{invoice_id}", response_model=InvoiceRead)
async def update_invoice(
    invoice_id: str,
    invoice: InvoiceCreate,
    current_user_id: str = Depends(get_current_user_id),
):
    current = await get_invoice(invoice_id, current_user_id)

    try:
        invoice_resp = supabase.rpc(
            "fn_invoices_update",
            {
                "p_i_id": invoice_id,
                "p_name": invoice.i_name,
                "p_inscription": invoice.i_inscription,
                "p_email": invoice.i_email,
                "p_address": invoice.i_address,
                "p_serie": invoice.i_serie,
                "p_date": str(invoice.i_date),
                "p_billto": invoice.i_billto,
                "p_total": invoice.i_total,
                "p_is_pay": invoice.i_is_pay,
            },
        ).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating invoice: {exc}",
        ) from exc

    for detail in invoice.details:
        rpc_name = "fn_invoice_details_update"
        params = {
            "p_id_number": detail.id_number,
            "p_id_id": invoice_id,
            "p_id_description": detail.id_description,
            "p_id_qty": detail.id_qty,
            "p_id_rate": detail.id_rate,
            "p_id_sale_tax": detail.id_sale_tax,
            "p_id_adress": detail.id_adress,
            "p_id_adress2": detail.id_adress2,
        }

        if not any(item.id_number == detail.id_number for item in current.details):
            rpc_name = "fn_invoice_details_create"
            params = {
                **params,
                "p_id_id": invoice_id,
            }

        try:
            supabase.rpc(rpc_name, params).execute()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error updating invoice detail: {exc}",
            ) from exc

    return build_invoice_read(invoice_resp.data)


@router.delete("/{invoice_id}")
async def delete_invoice(
    invoice_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    invoice = await get_invoice(invoice_id, current_user_id)

    if invoice.i_is_deleted:
        return {"ok": True}

    try:
        supabase.table("invoices").update({"i_is_deleted": True}).eq(
            "i_id", invoice_id
        ).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting invoice: {exc}",
        ) from exc

    return {"ok": True}

@router.get("/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
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

    # Sin chequeo de dueño: un solo negocio, todos pueden ver el PDF de cualquiera.

    # 2-5. Fetch details, render y convertir a PDF (lógica compartida con el bot)
    pdf_bytes, _invoice = generate_invoice_pdf(invoice_id)

    # 6. Devolver el PDF como respuesta HTTP
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="invoice_{invoice_id}.pdf"'
        },
    )
