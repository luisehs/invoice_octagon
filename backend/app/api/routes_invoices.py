# app/api/routes_invoices.py
from fastapi import APIRouter, Depends, HTTPException, status
from app.db.supabase_client import supabase
from app.api.deps import get_current_user_id
from app.schemas.invoices import InvoiceCreate, InvoiceRead

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

    if resp.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating invoice: {resp.error.message}",
        )

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
    resp = supabase.rpc(
        "fn_invoices_list",
        {"p_u_id": current_user_id},
    ).execute()

    if resp.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing invoices: {resp.error.message}",
        )

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
