# app/services/bot_parser.py
"""Parser y validaciones del formato fijo del bot (sin LLM).

Formato esperado:

    1. nombre
    2. catastro
    3. address
    4. email
    5. monto

Reglas:
- Cada línea se identifica por su NÚMERO inicial (1-5), tolerando "1." "1)"
  "1-" "1 -" "1:" y espacios. El orden y las líneas ausentes no importan.
- Texto antes de la lista ("Saludos:", etc.) se ignora.
- Si un número aparece dos veces, gana el último.
- Se toleran etiquetas dentro de la línea: "2. Catastro: 023-..." → "023-...",
  "4. Email: x@y.com" → "x@y.com".
- Obligatorios: nombre, address, monto. Catastro y email opcionales.

Módulo PURO (sin I/O) para poder testearlo sin Supabase/Telegram.
"""
import re

FIELD_BY_NUMBER = {
    1: "name",
    2: "catastro",
    3: "address",
    4: "email",
    5: "amount",
}
FIELD_LABELS = {
    "name": "1. nombre",
    "catastro": "2. catastro",
    "address": "3. address",
    "email": "4. email",
    "amount": "5. monto",
}
REQUIRED_FIELDS = ("name", "address", "amount")

# Sentinel para "sin email": el usuario dice explícitamente que no hay email.
NO_EMAIL_WORDS = {"sin email", "sin correo", "no email", "no tiene", "ninguno", "n/a", "na", "-", "—"}

# "1." "1)" "1-" "1 -" "1:" "1 ." + texto
_LINE_RE = re.compile(r"^\s*([1-5])\s*[.)\-:–]\s*(.*)$")
# Prefijos tipo "Catastro:", "Email:", "Nombre:", "Address:", "Monto:"
_LABEL_RE = re.compile(
    r"^\s*(nombre|name|cliente|catastro|address|direcci[oó]n|dir|email|e-mail|correo|monto|amount|rate|total|precio)\s*[:\-]\s*",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _clean_value(raw: str) -> str:
    value = (raw or "").strip()
    value = _LABEL_RE.sub("", value, count=1).strip()
    return value


def normalize_catastro(value: str) -> str:
    """Normaliza guiones tipográficos (– —) a '-', quita espacios alrededor."""
    value = (value or "").strip()
    value = value.replace("–", "-").replace("—", "-").replace("−", "-")
    value = re.sub(r"\s*-\s*", "-", value)
    return value


def parse_amount(value: str) -> float | None:
    """'$250', '250.00', '1,250', '250 usd' → float. None si no es un número > 0."""
    if value is None:
        return None
    text = str(value).strip().lower()
    text = re.sub(r"(usd|dólares|dolares|\$)", "", text)
    text = text.replace(" ", "")
    # 1,250.50 → 1250.50 ; 1.250,50 (formato europeo) → 1250.50
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        # "1,250" → 1250 ; "250,50" → 250.50
        parts = text.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            text = parts[0] + "." + parts[1]
        else:
            text = text.replace(",", "")
    try:
        amount = float(text)
    except ValueError:
        return None
    if amount <= 0:
        return None
    return round(amount, 2)


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match((value or "").strip()))


def has_numbered_lines(text: str) -> bool:
    return any(_LINE_RE.match(line) for line in (text or "").splitlines())


def parse_message(text: str) -> dict:
    """Devuelve {name, catastro, address, email, amount_raw} SOLO con las claves
    presentes en el mensaje (para poder mergear sobre datos anteriores).
    `amount_raw` conserva el texto tal cual; la conversión la hace validate()."""
    found: dict = {}
    for line in (text or "").splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        number = int(m.group(1))
        field = FIELD_BY_NUMBER[number]
        value = _clean_value(m.group(2))
        if field == "catastro":
            value = normalize_catastro(value)
        if field == "email" and value.lower() in NO_EMAIL_WORDS:
            value = ""  # "sin email" explícito → vacío válido
        found[field] = value
    return found


def merge_data(current: dict, incoming: dict) -> dict:
    """Lo nuevo pisa lo viejo; se ignoran vacíos salvo email (permite 'sin email')."""
    merged = dict(current or {})
    for key, value in (incoming or {}).items():
        if key == "email":
            merged["email"] = value
            merged["email_explicit"] = True
        elif value:
            merged[key] = value
    return merged


def validate(data: dict) -> tuple[list[str], list[str]]:
    """Devuelve (faltantes, errores). Si ambos vacíos, los datos están completos.

    - faltantes: etiquetas '1. nombre', '3. address', '5. monto' que no están.
    - errores: mensajes legibles (monto inválido, email inválido).
    Como efecto lateral normaliza data['amount'] a float cuando es válido.
    """
    missing: list[str] = []
    errors: list[str] = []

    if not (data.get("name") or "").strip():
        missing.append(FIELD_LABELS["name"])
    if not (data.get("address") or "").strip():
        missing.append(FIELD_LABELS["address"])

    amount_raw = data.get("amount")
    if amount_raw is None or str(amount_raw).strip() == "":
        missing.append(FIELD_LABELS["amount"])
    else:
        amount = parse_amount(amount_raw) if not isinstance(amount_raw, (int, float)) else float(amount_raw)
        if amount is None or amount <= 0:
            errors.append(
                f'El monto "{amount_raw}" no es válido. Envíame "5. <monto>" con un número mayor a 0 (ej. 5. 250).'
            )
        else:
            data["amount"] = amount

    email = (data.get("email") or "").strip()
    if email and not is_valid_email(email):
        errors.append(
            f'El email "{email}" no parece válido. Envíame "4. <email correcto>" o escribe "4. sin email".'
        )

    return missing, errors


def build_description(catastro: str | None) -> str:
    catastro = normalize_catastro(catastro or "")
    if catastro:
        return f"Appraisal Report - Catastro {catastro}"
    return "Appraisal Report"


# --- Interpretación de respuestas sí/no ------------------------------------
YES_WORDS = {"si", "sí", "s", "yes", "y", "ok", "dale", "claro", "correcto", "pagado", "pago", "pagó", "confirmo", "confirmar", "registra", "registrar", "crear", "crea"}
NO_WORDS = {"no", "n", "nop", "nope", "pendiente", "cancela", "cancelar", "negativo"}


def parse_yes_no(text: str) -> bool | None:
    word = (text or "").strip().lower().rstrip(".!")
    if word in YES_WORDS:
        return True
    if word in NO_WORDS:
        return False
    return None
