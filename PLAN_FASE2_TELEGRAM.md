# Plan — Fase 2: Bot de Telegram para crear invoices por chat

> Objetivo: enviar un mensaje de texto al bot de Telegram con los datos del cliente,
> que un agente (Claude API) extraiga la información, pregunte lo que falte (ej. el rate),
> cree el invoice en Invoices Octagon y devuelva el PDF al mismo chat.
>
> Este plan está pensado para ejecutarse con Claude Code sobre el repo existente.
> El 100% del trabajo nuevo vive en `backend/` — el frontend no se toca.

---

## 0. Decisiones ya tomadas

| Tema | Decisión |
|---|---|
| Canal | Solo Telegram (Bot API). WhatsApp queda para una fase posterior; el diseño deja el adaptador de mensajería aislado para poder agregarlo después. |
| Recepción de mensajes | **Webhook** en producción (el backend ya corre en EC2 con Nginx). **Long polling** para desarrollo local (no requiere URL pública). Mismo handler para ambos. |
| Agente | Un solo agente, Claude API (Anthropic) con *tool use*. Sin frameworks de agentes — una llamada al modelo con historial + definición de herramienta es suficiente. |
| Estado de conversación | Tabla nueva en Supabase (`chat_sessions`), no memoria en proceso (sobrevive reinicios de uvicorn/systemd). |
| Autorización | Whitelist: tabla que mapea `telegram chat_id → u_id`. Cualquier chat_id desconocido recibe "no autorizado" y se ignora. El bot NO usa JWT — llama la lógica interna directamente con el `u_id` mapeado. |
| Creación de invoice / PDF | Reutilizar lo existente: `fn_invoice_create_with_details` (RPC), `build_next_serie`, y la generación de PDF de `get_invoice_pdf` refactorizada a una función compartida. |

---

## 0.1 Regla de oro: la fase 1 NO puede romperse

Todo lo existente (frontend React, endpoints actuales, PDF del dashboard, login)
debe seguir funcionando **idéntico** durante y después de esta fase. Salvaguardas
obligatorias al implementar:

1. **Todo el trabajo se hace en una rama nueva** (`git checkout -b fase2-telegram`).
   No se mergea a la rama principal ni se despliega a EC2 hasta completar la Fase D
   verificada en local.
2. **Cero cambios de contrato**: no se modifica ninguna ruta existente (paths,
   request/response, status codes), ningún schema Pydantic existente, ni el
   frontend. El único cambio a código existente es la Fase A, que mueve lógica a
   `app/services/` dejando las rutas como wrappers con comportamiento idéntico.
3. **Solo se agrega, no se altera**: tablas nuevas (`telegram_users`,
   `chat_sessions`) y funciones `fn_*` nuevas en Supabase. Prohibido tocar las
   tablas `users`/`invoices`/`invoice_details` o las funciones existentes.
4. **Dependencias**: `anthropic` NO se instala como SDK (conflicto con
   `pydantic<2`, ver §4) — solo se agrega `httpx`, que no toca los pines
   existentes. No se actualiza ninguna dependencia actual (`bcrypt==3.2.2`,
   `pydantic<2` quedan intactos).
5. **Verificación de regresión al final de CADA fase** (no solo la A): login en
   el frontend, crear invoice desde el dashboard, editarlo, descargar su PDF y
   comparar que la serie siga la numeración correcta.
6. Si algo del bot falla en producción, el aislamiento garantiza que el resto del
   API no se afecta: el webhook es una ruta nueva e independiente, y un error ahí
   nunca debe propagar excepciones fuera de su handler.

---

## 1. Prerequisitos (manuales, fuera del código)

1. Crear el bot con **@BotFather** en Telegram → obtener `TELEGRAM_BOT_TOKEN`.
2. Obtener `ANTHROPIC_API_KEY` en console.anthropic.com.
3. Averiguar el `chat_id` de Alfred: escribirle al bot y leerlo del primer update (el plan incluye un comando `/id` para esto).
4. Acceso al SQL editor de Supabase para correr los scripts nuevos (misma mecánica que `backend/supabase_script/*.sql`).

Nuevas claves en `backend/.env` (y en `app/core/config.py::Settings`):

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_SECRET=...   # string aleatorio, se pasa a setWebhook y se valida en cada request
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-sonnet-4-5   # o el vigente al momento de implementar
```

---

## 2. Base de datos (Supabase)

Nuevo archivo `backend/supabase_script/telegram_bot.sql`, siguiendo la convención de prefijos por tabla:

### 2.1 `telegram_users` — whitelist y mapeo a usuario

```sql
create table telegram_users (
    tu_chat_id    bigint primary key,          -- chat_id de Telegram
    tu_u_id       uuid not null references users(u_id),
    tu_name       text,                        -- etiqueta humana ("Alfred")
    tu_is_active  boolean not null default true,
    tu_create_at  timestamptz not null default now()
);
```

### 2.2 `chat_sessions` — estado de la conversación en curso

```sql
create table chat_sessions (
    cs_chat_id    bigint primary key references telegram_users(tu_chat_id),
    cs_messages   jsonb not null default '[]'::jsonb,  -- historial [{role, content}]
    cs_status     text not null default 'idle',        -- idle | collecting | done
    cs_update_at  timestamptz not null default now()
);
```

Una sesión por chat es suficiente (un invoice a la vez). El comando `/cancelar` u
`/nuevo` limpia `cs_messages` y vuelve a `idle`. Opcional: en el handler, si
`cs_update_at` tiene más de ~2 horas, empezar sesión nueva automáticamente.

### 2.3 Funciones `fn_*`

Siguiendo el patrón del repo (todo acceso vía RPC), crear en el mismo `.sql`:

- `fn_telegram_user_get(p_chat_id bigint)` → fila de `telegram_users` activa o null.
- `fn_chat_session_get(p_chat_id bigint)` → fila de `chat_sessions` o null.
- `fn_chat_session_upsert(p_chat_id bigint, p_messages jsonb, p_status text)` → upsert + `cs_update_at = now()`.

> Nota práctica: para estas 3 operaciones triviales también sería aceptable usar
> `supabase.table(...)` directo (el repo ya lo hace en el soft-delete). Decidir al
> implementar; el plan asume RPC por consistencia.

---

## 3. Backend — estructura nueva

```
backend/app/
├── api/
│   └── routes_telegram.py      # webhook POST /telegram/webhook
├── services/                   # NUEVO paquete
│   ├── __init__.py
│   ├── invoice_service.py      # lógica compartida (extraída de routes_invoices.py)
│   ├── invoice_agent.py        # el agente: Claude API + tool use + loop de conversación
│   └── telegram_client.py      # llamadas salientes a api.telegram.org (httpx)
└── bot_polling.py              # runner de desarrollo: long polling → mismo handler
```

### 3.1 Refactor previo: `services/invoice_service.py`

Extraer de `routes_invoices.py`, **sin cambiar comportamiento**, para que tanto las
rutas HTTP como el bot usen lo mismo:

- `create_invoice_for_user(u_id: str, invoice: InvoiceCreate) -> dict`
  (el cuerpo actual de `create_invoice`: arma `details_json` y llama
  `fn_invoice_create_with_details`).
- `get_next_serie_for_user(u_id: str, serie_date: date) -> str`
  (la lógica de `get_next_invoice_serie` incluyendo el fallback, usando el
  `build_next_serie` existente).
- `generate_invoice_pdf(invoice_id: str) -> tuple[bytes, dict]`
  (pasos 1–5 del actual `get_invoice_pdf`: fetch invoice + details, render
  `_invoice.html`, `html_to_pdf_bytes`; devuelve bytes + el dict del invoice
  para poder nombrar el archivo con la serie).

Las rutas de `routes_invoices.py` quedan como wrappers finos que validan
ownership/HTTP y delegan en el servicio. **Verificación de este paso: el frontend
actual debe seguir funcionando idéntico (crear, listar, PDF).**

### 3.2 `services/telegram_client.py`

Cliente mínimo con `httpx` (agregar a requirements; async, encaja con FastAPI):

- `send_message(chat_id, text)`
- `send_document(chat_id, file_bytes, filename, caption=None)` — multipart a `sendDocument`
- `send_chat_action(chat_id, "typing")` — feedback mientras el agente piensa
- `set_webhook(url, secret_token)` / `delete_webhook()` — usadas por un pequeño script CLI

### 3.3 `services/invoice_agent.py` — el corazón

**Flujo por mensaje entrante** (`handle_incoming_message(chat_id, text)`):

1. `fn_telegram_user_get(chat_id)` → si no existe/inactivo: responder "No autorizado" y salir.
2. Comandos rápidos sin pasar por el LLM: `/start` (bienvenida + formato esperado),
   `/id` (devuelve el chat_id, para poblar la whitelist), `/cancelar` (resetea sesión).
3. Cargar historial de `chat_sessions`, apendear `{"role": "user", "content": text}`.
4. Llamar Claude API (`messages.create`) con:
   - `system`: prompt del agente (ver 3.4)
   - `messages`: historial completo de la sesión
   - `tools`: una sola herramienta `crear_invoice`
5. Según la respuesta:
   - **Texto** (falta info / pide confirmación) → guardar en historial, enviarlo al chat. Fin del turno.
   - **`tool_use: crear_invoice`** → ejecutar la creación (paso 6).
6. Ejecución de `crear_invoice`:
   - `get_next_serie_for_user(u_id, date.today())` → `i_serie`
   - Calcular `i_total = Σ qty × rate` (+ sale_tax si se dio) **en Python** — no confiar en la aritmética del modelo.
   - Construir `InvoiceCreate` (Pydantic valida, ej. `EmailStr`) y llamar `create_invoice_for_user`.
   - `generate_invoice_pdf(i_id)` → `send_document(chat_id, pdf, f"invoice_{i_serie}.pdf", caption="✅ Invoice ... creado — Total $X")`
   - Devolver `tool_result` al modelo para el mensaje de cierre **o** simplemente cerrar el turno con el caption (más simple; decidir al implementar).
   - Resetear la sesión a `idle`.
7. Guardar historial actualizado con `fn_chat_session_upsert`.
8. Errores (Supabase caído, PDF falla, Claude API error): responder al chat
   "⚠️ Hubo un error creando el invoice: ..." y **no** perder la sesión.

**Definición de la herramienta** (input_schema alineado al mensaje de ejemplo y al esquema real):

```json
{
  "name": "crear_invoice",
  "description": "Crea el invoice cuando TODOS los datos obligatorios estén completos y el usuario haya confirmado.",
  "input_schema": {
    "type": "object",
    "properties": {
      "billto":      {"type": "string",  "description": "Nombre completo del cliente (ej. Francisco J Olivencia Torres)"},
      "inscription": {"type": "string",  "description": "Número de catastro (ej. 023-035-213-08)"},
      "email":       {"type": "string",  "description": "Email completo y válido del cliente"},
      "address":     {"type": "string",  "description": "Dirección de la propiedad"},
      "description": {"type": "string",  "description": "Descripción del servicio facturado"},
      "qty":         {"type": "number",  "default": 1},
      "rate":        {"type": "number",  "description": "Tarifa en USD"},
      "sale_tax":    {"type": "number",  "description": "Impuesto, si aplica"}
    },
    "required": ["billto", "rate", "description"]
  }
}
```

### 3.4 System prompt del agente (borrador)

```
Eres el asistente de facturación de Octagon. El usuario te envía por Telegram los
datos de un cliente para crear un invoice. Tu trabajo:

1. Extrae del mensaje: nombre del cliente, número de catastro, dirección, email,
   descripción del servicio, cantidad y rate. Los mensajes suelen venir como lista
   numerada pero pueden venir en cualquier formato.
2. Campos obligatorios: nombre del cliente, rate y descripción del servicio.
   Si falta alguno, pídelo en UNA sola pregunta breve y clara (agrupa todo lo que
   falte en un mismo mensaje). No inventes valores.
3. Valida lo evidente: un email sin dominio (ej. "folivencia.torres") está
   incompleto — pregúntalo. Un catastro con formato raro, confírmalo.
4. Cuando tengas todo, muestra un resumen (cliente, catastro, dirección, email,
   descripción, qty × rate = total) y pide confirmación ("¿Lo creo?").
5. Solo tras la confirmación del usuario llama la herramienta crear_invoice.
6. Responde siempre en español, tono breve y profesional. No des explicaciones
   técnicas ni menciones que eres una IA.
```

> El paso de confirmación (4–5) es deliberado: evita crear invoices por una mala
> extracción. Si en la práctica resulta pesado, se quita ajustando el prompt.

**Mapeo de campos** al crear `InvoiceCreate` (✅ confirmado en la Fase A contra
`InvoiceModal.tsx::handleSubmit`, `DashboardPage.tsx` y `_invoice.html` — ver
"Hallazgos Fase A" abajo). **Dato variable del cliente** que el frontend realmente
captura hoy: solo el nombre, la dirección de la propiedad, qty y rate.

| Dato del chat | Campo | ¿Se imprime en el PDF? |
|---|---|---|
| Nombre del cliente | `i_billto` | Sí → "BILL TO:" |
| Dirección de la propiedad | `id_adress` (+ `id_adress2` = 2ª línea) | Sí → bloque "Located at:" |
| **Catastro (opcional)** | se **agrega a `id_description`**: `"Appraisal Report - Catastro <n>"` | Sí → columna DESCRIPTION |
| rate | `id_rate` | Sí → RATE / AMOUNT |
| qty (por defecto 1) | `id_qty` | Sí → QTY |
| Fecha (opcional) | `i_date`; **hoy por defecto**, solo cambia si el usuario la da | Sí → DATE |
| Email del cliente (opcional) | `i_email` si lo dan, si no el del emisor | No (el template usa un literal) |
| ¿Pagó el rate? | `i_is_pay` (el agente SIEMPRE lo pregunta antes de crear) | Sí → sello "PAID" cuando está pagado |
| sale_tax (opcional) | `id_sale_tax` | Sí → filas TAX RATE / SALES TAX (normalmente `0`) |

**Constantes del emisor** — el frontend las hardcodea idénticas en cada invoice; el
bot debe mandar **los mismos literales** para no divergir del dashboard:

| Campo | Valor fijo que manda el frontend | ¿Se imprime? |
|---|---|---|
| `i_name` | `"Raimundo Marrero - TASADOR"` | Sí → título del encabezado |
| `i_inscription` | `"EPA 780 -CGA 195"` | Sí → subtítulo (licencia del emisor) |
| `i_email` | `"raimundo.marrero2@gmail.com"` | **No** (el template imprime un literal propio) |
| `i_address` | `"Cond. El Centro \| 500 Muñoz Rivera Ste 301 San Juan, PR 00918"` | **No** (el template imprime un literal propio) |

Generados por el backend/bot: `i_serie` generada, `i_total = Σ qty×rate (+ sale_tax)`,
`i_is_pay = False`, `id_number = 1`.

> **✅ Decisión (implementada en Fase C — `invoice_agent.build_invoice_fields`):**
> el catastro NO va a `i_inscription` (esa es la licencia del emisor); se **agrega
> a la descripción del servicio** como `"Appraisal Report - Catastro <n>"`. El email
> del cliente **no se pide** (no se imprime). Los campos variables reales del chat
> son: **nombre (→ `i_billto`), dirección de la propiedad (→ `id_adress`), rate** y,
> opcionales, **catastro, fecha y qty**. `i_date` es hoy salvo que el usuario indique
> otra. Así **no hace falta tocar `_invoice.html`** ni la Fase 1. La herramienta
> `crear_invoice` (§3.3) y el prompt (§3.4) de arriba quedan desactualizados respecto
> a esta decisión — la versión vigente vive en `app/services/invoice_agent.py`.

> **Hallazgos Fase A — resolución de las dos ⚠️** (verificado en código y con un PDF
> real generado por el endpoint refactorizado):
>
> 1. **`i_name` = nombre del EMISOR, no del cliente.** `InvoiceModal.tsx`
>    (`handleSubmit`, línea 104) lo fija a `"Raimundo Marrero - TASADOR"`; el
>    template lo imprime como título grande del encabezado (fallback "Raimundo
>    Marrero" si viniera vacío). El bot debe mandar ese mismo literal. (Idea:
>    moverlo a `.env`/`Settings`, pero eso tocaría el frontend → fuera de Fase A.)
>
> 2. **`i_address` vs `id_adress` NO son intercambiables.** `_invoice.html` **solo
>    imprime `d.id_adress`/`d.id_adress2`** (bajo "Located at:"). El bloque de
>    dirección y el email del encabezado son **texto literal del template**:
>    `invoice.i_address` e `invoice.i_email` **no aparecen en ningún `{{ }}`**. Por
>    tanto la dirección de la propiedad del cliente va **solo a `id_adress`**, nunca
>    a `i_address`. El frontend rellena `i_address`/`i_email` con datos del emisor
>    que se guardan en la BD pero **jamás se imprimen** (confirmado: mandé
>    `i_address="Cond. El Centro | ..."` y el PDF mostró el literal del template).
>
> 3. **El mapeo original del plan estaba equivocado en 3 filas.** "Catastro →
>    `i_inscription`", "Email → `i_email`" y "Dirección → `i_address` y `id_adress`"
>    no coinciden con la realidad: `i_inscription` es la **licencia del emisor**
>    (subtítulo), e `i_email`/`i_address` no se imprimen. Hoy **no hay lugar en el
>    PDF para el catastro ni el email del cliente**. Decisión pendiente (Fase C/D):
>    (a) incrustar catastro/email dentro de `id_description` o del bloque "Located
>    at:", o (b) aceptar que no se impriman. Darles un lugar propio exige **editar
>    `_invoice.html`** — permitido (solo se *agrega*), pero afecta también al PDF del
>    dashboard, así que hay que verificar la Fase 1 después.

### 3.5 `api/routes_telegram.py` — webhook

```
POST /telegram/webhook
```

- Validar header `X-Telegram-Bot-Api-Secret-Token == settings.TELEGRAM_WEBHOOK_SECRET`; si no, 403.
- Parsear el update; ignorar todo lo que no sea `message.text` de un chat privado (responder cortésmente a fotos/audios: "por ahora solo texto").
- Llamar `handle_incoming_message(chat_id, text)`.
- **Responder 200 siempre y rápido.** Telegram reintenta si no hay 200 → riesgo de invoices duplicados. Como la cadena Claude+PDF puede tardar >10 s, ejecutar el handler con `BackgroundTasks` de FastAPI (o `asyncio.create_task`) y retornar 200 de inmediato. Enviar `send_chat_action("typing")` al arrancar.
- Montar el router en `main.py` (`app.include_router(telegram_router)`).

### 3.6 `bot_polling.py` — desarrollo local

Script standalone (`python -m app.bot_polling` desde `backend/`): loop de
`getUpdates` con offset que llama el mismo `handle_incoming_message`. Permite
desarrollar todo el flujo sin URL pública ni tocar el EC2. (Regla de Telegram:
webhook y polling son excluyentes — el script hace `deleteWebhook` al arrancar.)

---

## 4. Dependencias nuevas

En `backend/requirements.txt` agregar:

```
anthropic
httpx
```

⚠️ **Restricción importante**: el proyecto pinnea `pydantic<2`. Las versiones
recientes del SDK `anthropic` requieren pydantic v2. Regla de decisión al implementar:

- **Opción A (preferida, cero riesgo):** no usar el SDK; llamar la Messages API
  directo con `httpx` (`POST https://api.anthropic.com/v1/messages`, headers
  `x-api-key` + `anthropic-version`). Son ~30 líneas y elimina el conflicto.
- **Opción B:** instalar un `anthropic` viejo compatible con pydantic v1 — frágil, no recomendada.
- **Opción C (proyecto aparte):** migrar el backend a pydantic 2 — fuera de alcance de esta fase.

El plan asume la **Opción A**: módulo `services/claude_client.py` con una función
`call_claude(system, messages, tools) -> dict` sobre httpx.

---

## 5. Despliegue (EC2 existente)

1. `git pull`, `pip install -r requirements.txt` en el entorno conda, añadir las claves nuevas a `backend/.env`, `sudo systemctl restart invoice-api`.
2. Nginx: el server block existente ya proxya al backend; solo verificar que `POST /telegram/webhook` pasa (si el proxy es catch-all, no hay que tocar nada). **Requisito de Telegram: HTTPS válido** — confirmar que el dominio del API tiene cert (si hoy se sirve por IP/HTTP, hay que poner un subdominio + certbot antes de esta fase).
3. Registrar el webhook (una vez): script `backend/scripts/set_webhook.py` que llama `setWebhook` con la URL pública y `secret_token`.
4. Verificar con `getWebhookInfo` que no haya `last_error_message`.

---

## 6. Fases de trabajo (orden para Claude Code)

Cada fase deja el sistema funcionando y es verificable por sí sola:

- **Fase A — Refactor sin cambios de comportamiento.**
  Crear `app/services/invoice_service.py`, mover la lógica, dejar las rutas como wrappers.
  ✔ Verificar: el frontend crea/lista/descarga PDF igual que antes.

- **Fase B — Bot "eco" + whitelist.**
  SQL de `telegram_users`/`chat_sessions` + `telegram_client.py` + `bot_polling.py` +
  comandos `/start`, `/id`, `/cancelar`. El bot responde eco a texto de usuarios whitelisted.
  ✔ Verificar: `/id` devuelve el chat_id; tras insertarlo en `telegram_users`, el bot responde; desde otro teléfono, rechaza.

- **Fase C — Agente conversacional (sin crear nada todavía).**
  `claude_client.py` + `invoice_agent.py` con historial en `chat_sessions`. La herramienta
  `crear_invoice` existe pero su ejecución solo responde el resumen "crearía este invoice: …".
  ✔ Verificar con el mensaje de ejemplo real: debe pedir el rate y el email completo, y al darlos, mostrar el resumen correcto. Probar también: mensaje desordenado, datos en dos mensajes, `/cancelar` a mitad.

- **Fase D — Creación real + PDF.**
  Conectar la herramienta a `create_invoice_for_user` + `generate_invoice_pdf` + `send_document`.
  ✔ Verificar: el invoice aparece en el dashboard web con la serie correcta y el siguiente invoice creado desde el frontend continúa la numeración; el PDF del chat es idéntico al del botón del dashboard.

- **Fase E — Webhook + deploy.**
  `routes_telegram.py` con secret + BackgroundTasks, `set_webhook.py`, deploy en EC2.
  ✔ Verificar: flujo completo desde el teléfono contra producción; enviar dos mensajes seguidos rápido y confirmar que no se duplica nada.

---

## 7. Casos borde a cubrir (checklist de pruebas)

- [ ] Mensaje de ejemplo completo pero sin rate → pregunta solo el rate.
- [ ] Email incompleto (`folivencia.torres`) → lo detecta y pregunta.
- [ ] Usuario responde el rate con "$250" o "250" → ambos funcionan.
- [ ] Usuario cambia un dato después del resumen ("la dirección es otra…") → corrige y re-resume.
- [ ] Usuario no confirma y manda un cliente nuevo → el agente entiende o se le indica `/cancelar`.
- [ ] chat_id no whitelisted → rechazo, no toca la API de Claude.
- [ ] Falla la creación en Supabase → mensaje de error en el chat, la sesión no se corrompe.
- [ ] Dos invoices creados el mismo día (bot y/o frontend) → series `-001`, `-002` correctas.
- [ ] Foto/nota de voz → respuesta "solo texto por ahora" (v1 no hace OCR/transcripción).

## 8. Fuera de alcance (fase 3+)

WhatsApp Cloud API (reusar `invoice_agent` con otro adaptador), OCR de fotos de
documentos, marcar invoices como pagados desde el chat, consultas ("¿cuánto he
facturado este mes?" → `fn_invoices_summary`), multiusuario avanzado.
