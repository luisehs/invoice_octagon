# app/schemas/users.py
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class UserBase(BaseModel):
    u_firstname: str
    u_lastname: str
    u_email: EmailStr
    u_role: str = "user"
    u_is_active: bool = True


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    u_id: str
    u_create_at: datetime


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
