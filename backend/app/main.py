# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_invoices import router as invoices_router
from app.api.routes_telegram import router as telegram_router

app = FastAPI(title="Invoice Backend")

origins = [
    "https://invoices.octagonpr.co",
    "http://34.174.207.207",    ""
    "http://34.174.207.207:80",
    "*"
    #"http://localhost:3000",
    #"http://localhost:5173",
    # "http://localhost:3000",
    # "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(invoices_router)
app.include_router(telegram_router)
