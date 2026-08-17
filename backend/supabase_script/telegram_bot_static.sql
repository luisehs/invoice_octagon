-- ============================================================
-- Fase 2b (bot ESTÁTICO + modo /onAI) — migración de chat_sessions.
-- Correr en el SQL editor de Supabase DESPUÉS de telegram_bot.sql.
--
-- Solo AGREGA columnas y reemplaza fn_chat_session_upsert (función
-- del bot, no del API principal). No toca users/invoices/invoice_details.
-- Idempotente: se puede volver a correr.
-- ============================================================

-- 1. Columnas nuevas en chat_sessions
--    cs_status   (ya existe) → estado de la máquina:
--                idle | collecting | awaiting_payment | awaiting_confirm
--    cs_data     → datos capturados del formato numerado
--                {name, catastro, address, email, amount, is_pay}
--    cs_messages (ya existe) → historial SOLO del modo AI
--    cs_ai_until → hasta cuándo está activo /onAI (null = OFF)
alter table public.chat_sessions
    add column if not exists cs_data jsonb not null default '{}'::jsonb;

alter table public.chat_sessions
    add column if not exists cs_ai_until timestamptz;

-- 2. Reemplazar el upsert (firma nueva). Se borra la vieja para que el
--    RPC de supabase no encuentre dos sobrecargas.
drop function if exists public.fn_chat_session_upsert(bigint, jsonb, text);

create or replace function public.fn_chat_session_upsert(
    p_chat_id  bigint,
    p_status   text,
    p_data     jsonb,
    p_messages jsonb,
    p_ai_until timestamptz
)
returns public.chat_sessions
language plpgsql
as $$
declare
    v_row public.chat_sessions;
begin
    insert into public.chat_sessions
        (cs_chat_id, cs_status, cs_data, cs_messages, cs_ai_until, cs_update_at)
    values (
        p_chat_id,
        coalesce(p_status, 'idle'),
        coalesce(p_data, '{}'::jsonb),
        coalesce(p_messages, '[]'::jsonb),
        p_ai_until,            -- null = modo AI apagado (se guarda tal cual)
        now()
    )
    on conflict (cs_chat_id) do update
        set cs_status    = coalesce(excluded.cs_status, public.chat_sessions.cs_status),
            cs_data      = coalesce(excluded.cs_data, public.chat_sessions.cs_data),
            cs_messages  = coalesce(excluded.cs_messages, public.chat_sessions.cs_messages),
            cs_ai_until  = excluded.cs_ai_until,
            cs_update_at = now()
    returning * into v_row;

    return v_row;
end;
$$;
