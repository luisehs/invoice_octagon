# Plan — Fase 2: Bot de Telegram para crear invoices por chat

> **Estado (2026-08-17): IMPLEMENTADO en la rama `fase2-bot-estatico`.**
> Archivos: `services/bot_parser.py`, `bot_flow.py`, `bot_session.py`, `bot_invoice.py`,
> `invoice_agent.py` (modo AI), `supabase_script/telegram_bot_static.sql`, `tests/`.
> Pendiente manual: correr `telegram_bot_static.sql` en Supabase y probar con el bot real.

> Objetivo: enviar al bot de Telegram un mensaje con formato fijo (nombre, catastro,
> address, email, monto), que el bot valide, pida lo que falte, pregunte si está pago,
> muestre un resumen, cree el invoice en Invoices Octagon y devuelva el PDF al chat.
>
> El bot es **estático** (máquina de estados en código, sin LLM). Claude API solo se
> usa en el **modo AI opcional** activado con `/onAI`, que se apaga solo tras un tiempo.
>
> Este plan está pensado para ejecutarse con Claude Code sobre el repo existente.
> El 100% del trabajo nuevo vive en `backend/` — el frontend no se toca.

---

## 0. Decisiones ya tomadas

| Tema | Decisión |
|---|---|
| Canal | Solo Telegram (Bot API). WhatsApp queda para una fase posterior; el adaptador de mensajería queda aislado para poder agregarlo después. |
| Recepción de mensajes | **Webhook** en producción (EC2 + Nginx). **Long polling** en desarrollo local. Mismo handler para ambos. |
| Lógica del bot | **Estática**: parser del formato numerado + validaciones manuales + respuestas fijas por código. Cero llamadas a Anthropic en el flujo normal. |
| Modo AI | Comando `/onAI` activa un modo conversacional con Claude API (extracción libre + preguntas naturales). Es **opcional**, siempre arranca en OFF, y **expira solo** tras `AI_MODE_TTL_MINUTES` (default 30). `/offAI` lo apaga antes. |
| Estado de conversación | Tabla `chat_sessions` en Supabase (sobrevive reinicios). |
| Autorización | Whitelist `telegram_users`: `chat_id → u_id`. Desconocidos reciben "no autorizado". El bot NO usa JWT; llama la lógica interna con el `u_id` mapeado. |
| Creación / PDF | Reutilizar lo existente: `fn_invoice_create_with_details`, `build_next_serie`, y la generación de PDF de `get_invoice_pdf` refactorizada a función compartida. |

---

## 0.1 Regla de oro: la fase 1 NO puede romperse

Todo lo existente (frontend React, endpoints, PDF del dashboard, login) debe seguir
funcionando **idéntico** durante y después de esta fase. Salvaguardas obligatorias:

1. **Rama nueva** (`git checkout -b fase2-telegram`). No se mergea ni se despliega
   hasta completar la Fase D verificada en local.
2. **Cero cambios de contrato**: no se modifica ninguna ruta existente, ningún schema
   Pydantic existente, ni el frontend. El único cambio a código existente es la Fase A
   (mover lógica a `app/services/`, rutas como wrappers idénticos).
3. **Solo se agrega**: tablas y funciones `fn_*` nuevas en Supabase. Prohibido tocar
   `users` / `invoices` / `invoice_details` o funciones existentes.
4. **Dependencias**: solo se agrega `httpx`. NO se instala el SDK `anthropic`
   (conflicto con `pydantic<2`, ver §5). No se actualiza ningún pin existente.
5. **Regresión al final de CADA fase**: login, crear invoice desde el dashboard,
   editarlo, descargar PDF, numeración de serie correcta.
6. El webhook es una ruta aislada: un error ahí nunca propaga fuera de su handler.

---

## 1. Prerequisitos (manuales)

1. Bot creado con **@BotFather** → `TELEGRAM_BOT_TOKEN`.
2. `ANTHROPIC_API_KEY` (solo necesario para `/onAI`; el bot funciona sin él).
3. `chat_id` de Alfred: se obtiene con el comando `/id` del bot (Fase B).
4. Acceso al SQL editor de Supabase para correr los scripts nuevos.

`backend/.env` (y `app/core/config.py::Settings`):

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_SECRET=...     # aleatorio; se pasa a setWebhook y se valida por request
ANTHROPIC_API_KEY=...           # opcional
ANTHROPIC_MODEL=claude-sonnet-4-5
AI_MODE_TTL_MINUTES=30          # cuánto dura /onAI antes de volver a OFF
SESSION_TTL_MINUTES=120         # sesión abandonada → se reinicia sola
```

---

## 2. Base de datos (Supabase)

Archivo nuevo `backend/supabase_script/telegram_bot.sql`:

### 2.1 `telegram_users` — whitelist y mapeo a usuario

```sql
create table telegram_users (
    tu_chat_id    bigint primary key,
    tu_u_id       uuid not null references users(u_id),
    tu_name       text,
    tu_is_active  boolean not null default true,
    tu_create_at  timestamptz not null default now()
);
```

### 2.2 `chat_sessions` — estado de la conversación

```sql
create table chat_sessions (
    cs_chat_id      bigint primary key references telegram_users(tu_chat_id),
    cs_state        text  not null default 'idle',
        -- idle | collecting | awaiting_payment | awaiting_confirm | ai
    cs_data         jsonb not null default '{}'::jsonb,
        -- {name, catastro, address, email, amount, is_pay}
    cs_messages     jsonb not null default '[]'::jsonb,   -- solo modo AI
    cs_ai_until     timestamptz,                          -- null = AI OFF
    cs_update_at    timestamptz not null default now()
);
```

### 2.3 Funciones `fn_*` (patrón del repo)

- `fn_telegram_user_get(p_chat_id)` → fila activa o null.
- `fn_chat_session_get(p_chat_id)` → fila o null.
- `fn_chat_session_upsert(p_chat_id, p_state, p_data, p_messages, p_ai_until)` → upsert + `cs_update_at = now()`.

---

## 3. Backend — estructura nueva

```
backend/app/
├── api/
│   └── routes_telegram.py       # POST /telegram/webhook
├── services/                    # NUEVO paquete
│   ├── __init__.py
│   ├── invoice_service.py       # lógica compartida (extraída de routes_invoices.py)
│   ├── telegram_client.py       # httpx → api.telegram.org
│   ├── bot_parser.py            # parser del formato numerado + validaciones
│   ├── bot_flow.py              # máquina de estados (flujo estático)
│   ├── bot_ai.py                # modo /onAI (Claude API)
│   └── claude_client.py         # httpx → api.anthropic.com (solo modo AI)
├── bot_polling.py               # runner de desarrollo (long polling)
└── scripts/set_webhook.py
```

### 3.1 Refactor previo: `services/invoice_service.py`

Extraer de `routes_invoices.py` **sin cambiar comportamiento**:

- `create_invoice_for_user(u_id, invoice: InvoiceCreate) -> dict`
- `get_next_serie_for_user(u_id, serie_date) -> str` (con el fallback actual)
- `generate_invoice_pdf(invoice_id) -> tuple[bytes, dict]`

Las rutas quedan como wrappers finos. **Verificación: el frontend sigue idéntico.**

### 3.2 `services/telegram_client.py`

`send_message`, `send_document` (multipart), `send_chat_action("typing")`,
`set_webhook`, `delete_webhook`, `get_updates`.

### 3.3 `services/bot_parser.py` — formato fijo y validaciones

Formato esperado del usuario:

```
1. nombre
2. catastro
3. address
4. email
5. monto
```

Reglas del parser (`parse_message(text) -> dict`):

- Se detecta cada línea por su **número inicial**, tolerando `1.` `1)` `1-` `1 -` `1:`
  y espacios. El orden y las líneas faltantes no importan: se mapea por número.
- Se admite un saludo u otro texto antes de la lista ("Saludos:", etc.) → se ignora.
- Un mensaje que **no contenga ninguna línea numerada** en estado `idle` recibe la
  ayuda con el formato esperado.
- Si el mismo número aparece dos veces, gana la última.
- Devuelve `{name, catastro, address, email, amount}` con `None` en los ausentes.

Validaciones (`validate(data) -> list[str]` devuelve los errores/faltantes):

| Campo | Regla |
|---|---|
| 1. nombre | **obligatorio**, no vacío |
| 2. catastro | opcional; se guarda tal cual, normalizando guiones tipográficos `–` a `-` |
| 3. address | **obligatorio**, no vacío |
| 4. email | opcional; si viene, debe pasar `EmailStr`; si no, se avisa y se pregunta "¿corrijo el email o lo dejo vacío?" |
| 5. monto | **obligatorio**; se limpian `$`, comas y espacios; debe ser número > 0 |

Mensajes de respuesta fijos (en español), por ejemplo:

- Faltantes: `Me falta: 3. address y 5. monto. Envíamelos por favor (puedes mandar solo esas líneas).`
- Email inválido: `El email "folivencia.torres" no parece válido. Envíame el email correcto o escribe "sin email".`
- Ayuda: el formato completo con los 5 puntos y cuáles son obligatorios.

### 3.4 `services/bot_flow.py` — máquina de estados (flujo estático)

`handle_incoming_message(chat_id, text)`:

0. Whitelist: `fn_telegram_user_get` → si no existe/inactivo → "No autorizado" y salir.
1. Cargar sesión; si `cs_update_at` > `SESSION_TTL_MINUTES` → reiniciar a `idle`.
2. **Comandos** (siempre, en cualquier estado):
   - `/start` → bienvenida + formato esperado.
   - `/id` → devuelve el chat_id.
   - `/cancelar` → sesión a `idle`, `cs_data = {}`.
   - `/onAI` → si hay `ANTHROPIC_API_KEY`: `cs_ai_until = now + AI_MODE_TTL`,
     estado `ai`, responde "Modo AI activado por N minutos". Si no hay key: "Modo AI no configurado".
   - `/offAI` → `cs_ai_until = null`, estado `idle`, responde "Modo AI desactivado".
3. **Modo AI**: si `cs_ai_until` no es null y `> now()` → delegar a `bot_ai.handle`
   (§3.5). Si ya expiró → limpiar `cs_ai_until`, avisar "Modo AI expiró, vuelvo al
   modo normal" y seguir con el flujo estático.
4. **Flujo estático por estado:**

   | Estado | Qué hace con el texto |
   |---|---|
   | `idle` / `collecting` | `parse_message` → merge con `cs_data` (lo nuevo pisa lo viejo) → `validate`. Si faltan obligatorios o email inválido → responde con los faltantes/errores, estado `collecting`. Si todo OK → pregunta **"¿Está pago? (sí / no)"**, estado `awaiting_payment`. |
   | `awaiting_payment` | Acepta `sí/si/s/yes/pagado` → `is_pay=true`; `no/n` → `false`; otra cosa → repite la pregunta. Luego muestra el **resumen** y pregunta **"¿Lo registro? (sí / no)"**, estado `awaiting_confirm`. |
   | `awaiting_confirm` | `sí` → crea invoice + PDF (§3.6), responde, sesión a `idle`. `no` → "Cancelado", sesión a `idle`. Si el texto contiene líneas numeradas → se toma como corrección: merge y vuelve a validar/resumir. Otra cosa → repite la pregunta. |

   Formato del resumen:

   ```
   📋 Resumen del invoice
   Cliente:  Francisco J Olivencia Torres
   Catastro: 023-035-213-08
   Dirección: 246 Calle Andalucía Aguadilla PR 00603
   Email:    folivencia.torres@gmail.com   (o "—")
   Servicio: Appraisal Report - Catastro 023-035-213-08
   Monto:    $250.00
   Pago:     Sí / No
   ¿Lo registro? (sí / no)
   ```

5. Guardar sesión con `fn_chat_session_upsert` al final de cada turno.
6. Cualquier excepción → responder "⚠️ Error: …" y **no** perder `cs_data`.

### 3.5 `services/bot_ai.py` — modo /onAI (opcional)

Solo activo dentro de la ventana `cs_ai_until`. Usa `claude_client.py` (httpx directo
a la Messages API, ver §5) con:

- `system`: asistente de facturación de Octagon; extrae nombre, catastro, address,
  email, monto de texto libre; pide en una sola pregunta lo que falte (obligatorios:
  nombre, address, monto); pregunta si está pago; muestra resumen y pide confirmación;
  solo entonces llama la herramienta. Responde en español, breve.
- `tools`: una herramienta `crear_invoice` con `{name, catastro?, address, email?, amount, is_pay}`.
- Historial en `cs_messages`. Cuando el modelo llama la herramienta → **misma
  función de creación** de §3.6 (así el resultado es idéntico al modo estático) →
  PDF al chat → limpiar historial, `cs_ai_until = null` (vuelve a OFF tras crear).

### 3.6 Creación del invoice (compartida por ambos modos)

`create_from_bot_data(u_id, data) -> (invoice_dict, pdf_bytes)`:

| Dato del chat | Campo del invoice |
|---|---|
| nombre | `i_billto` |
| catastro | `i_inscription` (o null) |
| address | `i_address` y `id_adress` ⚠️ confirmar contra `InvoiceModal.tsx` en Fase A |
| email | `i_email` (o null) |
| monto | `id_rate`; `id_qty = 1`; `id_sale_tax = None`; `i_total = monto` (calculado en Python) |
| descripción | `id_description = "Appraisal Report - Catastro <catastro>"` si hay catastro; si no, `"Appraisal Report"` |
| pago | `i_is_pay` (respuesta a "¿Está pago?") |
| — | `i_name` ⚠️ confirmar qué envía el frontend (parece ser el emisor/negocio, no el cliente); si es fijo, mismo valor / configurable en `.env` |
| — | `i_date = date.today()`, `i_serie = get_next_serie_for_user(...)`, `id_number = 1` |

Luego `generate_invoice_pdf(i_id)` → `send_document(chat_id, pdf, f"invoice_{i_serie}.pdf",
caption="✅ Invoice {i_serie} creado — Total ${i_total} — {Pagado|Pendiente}")`.

### 3.7 `api/routes_telegram.py` — webhook

`POST /telegram/webhook`: validar `X-Telegram-Bot-Api-Secret-Token`, ignorar lo que no
sea `message.text` de chat privado (fotos/audio → "por ahora solo texto"), ejecutar el
handler con `BackgroundTasks` y **responder 200 inmediato** (Telegram reintenta si no →
riesgo de duplicados). Montar en `main.py`.

### 3.8 `bot_polling.py` — desarrollo local

`python -m app.bot_polling` desde `backend/`: `deleteWebhook` al arrancar, loop de
`getUpdates` con offset → mismo `handle_incoming_message`.

---

## 4. Ejemplo de conversación (modo estático)

```
Usuario:  Saludos:
          1. Francisco J Olivencia Torres
          2. Catastro: 023–035-213-08
          3. 246 Calle Andalucía Aguadilla PR 00603
          4. Email: folivencia.torres
Bot:      Me falta: 5. monto. Además el email "folivencia.torres" no parece válido:
          envíame el email correcto o escribe "sin email".
Usuario:  5. $250
          4. folivencia.torres@gmail.com
Bot:      ¿Está pago? (sí / no)
Usuario:  no
Bot:      📋 Resumen del invoice … ¿Lo registro? (sí / no)
Usuario:  sí
Bot:      [PDF invoice_2026-08-17-001.pdf]
          ✅ Invoice 2026-08-17-001 creado — Total $250.00 — Pendiente
```

---

## 5. Dependencias

`requirements.txt`: agregar solo `httpx`.

⚠️ El proyecto pinnea `pydantic<2`; el SDK `anthropic` actual requiere pydantic v2.
Para el modo AI se llama la Messages API **directo con httpx** (`POST
https://api.anthropic.com/v1/messages`, headers `x-api-key`, `anthropic-version`).
No instalar el SDK.

---

## 6. Despliegue (EC2 existente)

1. `git pull`, `pip install -r requirements.txt`, claves nuevas en `.env`,
   `sudo systemctl restart invoice-api`.
2. Nginx: verificar que `POST /telegram/webhook` pasa por el proxy. **Telegram exige
   HTTPS válido** — si el API hoy se sirve por IP/HTTP, hay que poner subdominio + cert antes.
3. `python -m app.scripts.set_webhook` una vez; verificar con `getWebhookInfo`.

---

## 7. Fases de trabajo (orden para Claude Code)

- **Fase A — Refactor sin cambios de comportamiento.** `invoice_service.py`; rutas como wrappers.
  ✔ Frontend crea/lista/descarga PDF igual que antes. Resolver las ⚠️ de §3.6.
- **Fase B — Bot eco + whitelist + polling.** SQL, `telegram_client.py`, `bot_polling.py`,
  comandos `/start`, `/id`, `/cancelar`. Eco a whitelisted; rechazo a desconocidos.
- **Fase C — Flujo estático completo en modo simulación.** `bot_parser.py` + `bot_flow.py`.
  Al confirmar, en vez de crear responde "SIMULACIÓN — crearía: {json}".
  ✔ Probar con el mensaje de ejemplo (debe pedir el monto y el email), correcciones,
  `/cancelar`, mensaje sin formato → ayuda.
- **Fase D — Creación real + PDF.** `create_from_bot_data` conectada a Supabase + PDF al chat.
  ✔ Invoice visible en el dashboard, serie correcta, PDF idéntico al del dashboard.
- **Fase E — Webhook + deploy.** `routes_telegram.py`, `set_webhook.py`, EC2.
- **Fase F (opcional) — Modo AI.** `claude_client.py` + `bot_ai.py` + `/onAI` `/offAI` con TTL.
  ✔ `/onAI` → texto libre funciona; expira solo; `/offAI` apaga; sin key → mensaje claro.

---

## 8. Checklist de pruebas

- [ ] Mensaje de ejemplo (sin monto, email incompleto) → pide monto y email en un solo mensaje.
- [ ] Reenviar solo `5. 250` y `4. correo@x.com` → mergea y avanza a "¿Está pago?".
- [ ] `$250`, `250.00`, `1,250` → todos parsean; `abc` → error claro.
- [ ] Sin catastro → descripción "Appraisal Report"; con catastro → "Appraisal Report - Catastro X".
- [ ] "sin email" → email null y avanza.
- [ ] Corrección con línea numerada en `awaiting_confirm` → re-resume.
- [ ] `no` en confirmación → cancela; `/cancelar` en cualquier estado → idle.
- [ ] Texto sin formato en idle → ayuda con el formato.
- [ ] Sesión abandonada > `SESSION_TTL_MINUTES` → arranca limpia.
- [ ] chat_id no whitelisted → rechazo.
- [ ] Error de Supabase/PDF → mensaje de error, `cs_data` intacto.
- [ ] Dos invoices el mismo día (bot + frontend) → `-001`, `-002`.
- [ ] `/onAI` sin key → "no configurado"; con key → conversa; expira a los N min; `/offAI` apaga.
- [ ] Foto/nota de voz → "solo texto por ahora".

## 9. Fuera de alcance (fase 3+)

WhatsApp Cloud API (reusar `bot_flow` con otro adaptador), OCR de fotos, marcar pagado
desde el chat, consultas de totales (`fn_invoices_summary`), multiusuario avanzado.
