# backend/tests/test_bot_parser.py
from app.services.bot_parser import (
    build_description,
    has_numbered_lines,
    merge_data,
    normalize_catastro,
    parse_amount,
    parse_message,
    parse_yes_no,
    validate,
)

EXAMPLE = """Saludos:
1. Francisco J Olivencia Torres
2.Catastro: 023–035-213-08
3.246 Calle Andalucía Aguadilla PR 00603
4. Email: folivencia.torres"""


def test_parse_example_message():
    data = parse_message(EXAMPLE)
    assert data["name"] == "Francisco J Olivencia Torres"
    assert data["catastro"] == "023-035-213-08"  # guion tipográfico normalizado, label quitado
    assert data["address"] == "246 Calle Andalucía Aguadilla PR 00603"
    assert data["email"] == "folivencia.torres"
    assert "amount" not in data


def test_prefix_variants_and_order():
    text = "5) $250\n1- Juan Pérez\n3: Calle 1 Ponce PR"
    data = parse_message(text)
    assert data == {"amount": "$250", "name": "Juan Pérez", "address": "Calle 1 Ponce PR"}


def test_last_duplicate_wins():
    data = parse_message("5. 100\n5. 200")
    assert data["amount"] == "200"


def test_no_numbered_lines():
    assert parse_message("hola que tal") == {}
    assert not has_numbered_lines("hola")
    assert has_numbered_lines("2. algo")


def test_sin_email_explicit():
    data = parse_message("4. sin email")
    assert data["email"] == ""


def test_parse_amount_variants():
    assert parse_amount("$250") == 250.0
    assert parse_amount("250.00") == 250.0
    assert parse_amount("1,250") == 1250.0
    assert parse_amount("1,250.50") == 1250.5
    assert parse_amount("250,50") == 250.5
    assert parse_amount("300 usd") == 300.0
    assert parse_amount("abc") is None
    assert parse_amount("0") is None
    assert parse_amount("-5") is None


def test_validate_missing_and_invalid_email():
    data = parse_message(EXAMPLE)
    missing, errors = validate(data)
    assert missing == ["5. monto"]
    assert len(errors) == 1 and "folivencia.torres" in errors[0]


def test_validate_complete_and_amount_normalized():
    data = merge_data(parse_message(EXAMPLE), parse_message("5. $250\n4. folivencia.torres@gmail.com"))
    missing, errors = validate(data)
    assert missing == [] and errors == []
    assert data["amount"] == 250.0
    assert data["email"] == "folivencia.torres@gmail.com"


def test_validate_only_required():
    data = parse_message("1. Ana\n3. Calle X\n5. 100")
    missing, errors = validate(data)
    assert missing == [] and errors == []


def test_validate_bad_amount():
    data = parse_message("1. Ana\n3. Calle X\n5. gratis")
    missing, errors = validate(data)
    assert missing == []
    assert errors and "gratis" in errors[0]


def test_merge_keeps_old_and_overrides():
    merged = merge_data({"name": "A", "address": "X"}, {"address": "Y", "email": ""})
    assert merged["name"] == "A" and merged["address"] == "Y" and merged["email"] == ""


def test_description():
    assert build_description("023–035-213-08") == "Appraisal Report - Catastro 023-035-213-08"
    assert build_description("") == "Appraisal Report"
    assert build_description(None) == "Appraisal Report"


def test_normalize_catastro():
    assert normalize_catastro("023 – 035 - 213-08") == "023-035-213-08"


def test_yes_no():
    assert parse_yes_no("sí") is True
    assert parse_yes_no("Si.") is True
    assert parse_yes_no("no") is False
    assert parse_yes_no("pendiente") is False
    assert parse_yes_no("tal vez") is None
