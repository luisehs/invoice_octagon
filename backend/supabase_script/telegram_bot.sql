-- ============================================================
-- Fase 2 (bot de Telegram) — tablas y funciones NUEVAS.
-- Correr en el SQL editor de Supabase, igual que el resto de
-- backend/supabase_script/*.sql.
--
-- Este script SOLO AGREGA objetos nuevos. No toca (ni debe tocar)
-- las tablas users / invoices / invoice_details ni sus funciones.
-- Es idempotente: se puede volver a correr sin romper nada.
-- ============================================================

-- ------------------------------------------------------------
-- 2.1  telegram_users — whitelist y mapeo chat_id -> usuario
-- ------------------------------------------------------------
create table if not exists public.telegram_users (
    tu_chat_id    bigint primary key,                         -- chat_id de Telegram
    tu_u_id       uuid not null references public.users(u_id),-- usuario dueño de los invoices
    tu_name       text,                                       -- etiqueta humana ("Alfred")
    tu_is_active  boolean not null default true,
    tu_create_at  timestamptz not null default now()
);

-- ------------------------------------------------------------
-- 2.2  chat_sessions — estado de la conversación en curso
--      (una sesión por chat; un invoice a la vez)
-- ------------------------------------------------------------
create table if not exists public.chat_sessions (
    cs_chat_id    bigint primary key references public.telegram_users(tu_chat_id),
    cs_messages   jsonb not null default '[]'::jsonb,         -- historial [{role, content}]
    cs_status     text  not null default 'idle',              -- idle | collecting | done
    cs_update_at  timestamptz not null default now()
);

-- ------------------------------------------------------------
-- 2.3  Funciones fn_* (todo acceso vía RPC, como el resto del repo)
-- ------------------------------------------------------------

-- READ: whitelist. Devuelve la fila ACTIVA del chat, o un registro
-- all-null si el chat_id no existe o está inactivo (mismo patrón que
-- fn_invoices_get_by_id / fn_users_get_by_id). El backend detecta el
-- "no encontrado" comprobando que tu_u_id venga en null.
create or replace function public.fn_telegram_user_get(
    p_chat_id bigint
)
returns public.telegram_users
language plpgsql
as $$
declare
    v_row public.telegram_users;
begin
    select *
    into v_row
    from public.telegram_users
    where tu_chat_id = p_chat_id
      and tu_is_active = true;

    return v_row;
end;
$$;

-- READ: sesión de chat. Devuelve la fila o un registro all-null si no existe.
create or replace function public.fn_chat_session_get(
    p_chat_id bigint
)
returns public.chat_sessions
language plpgsql
as $$
declare
    v_row public.chat_sessions;
begin
    select *
    into v_row
    from public.chat_sessions
    where cs_chat_id = p_chat_id;

    return v_row;
end;
$$;

-- UPSERT: crea o actualiza la sesión y refresca cs_update_at.
-- Usado por /cancelar (resetea a []/idle) y, más adelante, por el agente.
-- Requiere que el chat ya esté en telegram_users (FK).
create or replace function public.fn_chat_session_upsert(
    p_chat_id  bigint,
    p_messages jsonb,
    p_status   text
)
returns public.chat_sessions
language plpgsql
as $$
declare
    v_row public.chat_sessions;
begin
    insert into public.chat_sessions (cs_chat_id, cs_messages, cs_status, cs_update_at)
    values (
        p_chat_id,
        coalesce(p_messages, '[]'::jsonb),
        coalesce(p_status, 'idle'),
        now()
    )
    on conflict (cs_chat_id) do update
        set cs_messages  = coalesce(excluded.cs_messages, public.chat_sessions.cs_messages),
            cs_status    = coalesce(excluded.cs_status,   public.chat_sessions.cs_status),
            cs_update_at = now()
    returning * into v_row;

    return v_row;
end;
$$;

-- UPSERT: registra (o reactiva) un chat en la whitelist mapeándolo a un u_id.
-- Lo usa el comando /register del bot: tras verificar email+password con la
-- MISMA lógica que el login web (verify_password), vincula el chat al usuario
-- autenticado. Si el chat ya existía, actualiza el u_id y lo reactiva.
create or replace function public.fn_telegram_user_upsert(
    p_chat_id bigint,
    p_u_id    uuid,
    p_name    text
)
returns public.telegram_users
language plpgsql
as $$
declare
    v_row public.telegram_users;
begin
    insert into public.telegram_users (tu_chat_id, tu_u_id, tu_name, tu_is_active)
    values (p_chat_id, p_u_id, p_name, true)
    on conflict (tu_chat_id) do update
        set tu_u_id      = excluded.tu_u_id,
            tu_name      = coalesce(excluded.tu_name, public.telegram_users.tu_name),
            tu_is_active = true
    returning * into v_row;

    return v_row;
end;
$$;

-- ------------------------------------------------------------
-- Alta de usuarios (ya NO es manual): el usuario abre el chat con el bot y
-- manda /register; el bot le pide email + contraseña de su cuenta de la app y
-- los valida igual que el login web. Si son correctos, se agrega solo a la
-- whitelist vía fn_telegram_user_upsert.
--
-- (Para desactivar a alguien manualmente:
--    update public.telegram_users set tu_is_active = false where tu_chat_id = 123;)
-- ------------------------------------------------------------
