# app/schemas/invoices.py
from pydantic import BaseModel, EmailStr
from datetime import date, datetime
from typing import List, Optional


class InvoiceDetailCreate(BaseModel):
    id_number: int
    id_description: str
    id_qty: float
    id_rate: float
    id_sale_tax: Optional[float] = None
    id_adress: Optional[str] = None
    id_adress2: Optional[str] = None


class InvoiceCreate(BaseModel):
    i_name: str
    i_inscription: Optional[str] = None
    i_email: Optional[EmailStr] = None
    i_address: Optional[str] = None
    i_serie: Optional[str] = None
    i_date: date
    i_billto: Optional[str] = None
    i_total: float
    i_is_pay: bool = False
    details: List[InvoiceDetailCreate]


class InvoiceRead(BaseModel):
    i_id: str
    i_name: str
    i_inscription: Optional[str]
    i_email: Optional[EmailStr]
    i_address: Optional[str]
    i_serie: Optional[str]
    i_date: date
    i_billto: Optional[str]
    i_total: float
    i_is_pay: bool
    i_u_id: str
    i_create_at: datetime


class InvoiceSummaryRead(BaseModel):
    total: float
    total_year: float
    total_month: float
    total_last_month: float


class InvoiceDetailRead(InvoiceDetailCreate):
    id_id: str
    id_create_at: datetime


class InvoiceWithDetailsRead(InvoiceRead):
    details: List[InvoiceDetailRead]
