# app/api/routes_auth.py
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.db.supabase_client import supabase
from app.core.security import verify_password, get_password_hash, create_access_token
from app.schemas.users import UserCreate, Token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(user: UserCreate):
    existing = supabase.table("users").select("u_id").eq("u_email", user.u_email).execute()
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    hashed_pw = get_password_hash(user.password)

    resp = supabase.rpc(
        "fn_users_create",
        {
            "p_firstname": user.u_firstname,
            "p_lastname": user.u_lastname,
            "p_email": user.u_email,
            "p_password": hashed_pw,
            "p_role": user.u_role,
            "p_is_active": user.u_is_active,
        },
    ).execute()

    if resp.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating user: {resp.error.message}",
        )

    return {"message": "User created successfully"}


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    email = form_data.username
    password = form_data.password

    resp = supabase.table("users").select("*").eq("u_email", email).single().execute()
    user = resp.data

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not verify_password(password, user["u_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = create_access_token(subject=user["u_id"])
    return Token(access_token=access_token)
