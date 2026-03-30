# app/api/routes_invoices.py
from fastapi import APIRouter, Depends, HTTPException, status
from app.db.supabase_client import supabase
from app.api.deps import get_current_user_id
from app.schemas.invoices import InvoiceCreate, InvoiceRead
from fastapi.responses import Response
from app.core.templates import render_template
from app.core.pdf import html_to_pdf_bytes

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("/", response_model=InvoiceRead)
async def create_invoice(
    invoice: InvoiceCreate,
    current_user_id: str = Depends(get_current_user_id),
):
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

    try:
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
                "p_u_id": current_user_id,
                "p_details": details_json,
            },
        ).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating invoice: {exc}",
        ) from exc

    data = resp.data
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
        i_u_id=data["i_u_id"],
        i_create_at=data["i_create_at"],
    )


@router.get("/", response_model=list[InvoiceRead])
async def list_invoices(
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        resp = supabase.rpc(
            "fn_invoices_list",
            {"p_u_id": current_user_id},
        ).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing invoices: {exc}",
        ) from exc

    invoices = []
    for item in resp.data:
        invoices.append(
            InvoiceRead(
                i_id=item["i_id"],
                i_name=item["i_name"],
                i_inscription=item["i_inscription"],
                i_email=item["i_email"],
                i_address=item["i_address"],
                i_serie=item["i_serie"],
                i_date=item["i_date"],
                i_billto=item["i_billto"],
                i_total=float(item["i_total"]),
                i_u_id=item["i_u_id"],
                i_create_at=item["i_create_at"],
            )
        )

    return invoices

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

    # Verificar que la invoice pertenezca al usuario actual
    if invoice["i_u_id"] != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this invoice",
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

    # 3. Preparar contexto para el template (usa invoice.html)
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

    # 6. Devolver el PDF como respuesta HTTP
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="invoice_{invoice_id}.pdf"'
        },
    )
