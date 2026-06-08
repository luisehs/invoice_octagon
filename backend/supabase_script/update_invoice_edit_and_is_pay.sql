-- Ejecutar este script en Supabase SQL Editor para habilitar:
-- 1. Columnas i_is_pay / i_is_deleted en public.invoices.
-- 2. Funciones de create/update con i_is_pay.
-- 3. Edicion completa de invoice con reemplazo de detalles.

alter table public.invoices
    add column if not exists i_is_pay boolean not null default false;

alter table public.invoices
    add column if not exists i_is_deleted boolean not null default false;

drop function if exists public.fn_invoices_create(
    text, text, text, text, text, date, text, numeric, uuid
);

create or replace function public.fn_invoices_create(
    p_name        text,
    p_inscription text,
    p_email       text,
    p_address     text,
    p_serie       text,
    p_date        date,
    p_billto      text,
    p_total       numeric(12,2),
    p_is_pay      boolean,
    p_u_id        uuid
)
returns public.invoices
language plpgsql
as $$
declare
    v_invoice public.invoices;
begin
    insert into public.invoices (
        i_name, i_inscription, i_email, i_address,
        i_serie, i_date, i_billto, i_total,
        i_is_pay, i_u_id
    ) values (
        p_name, p_inscription, p_email, p_address,
        p_serie, p_date, p_billto, p_total,
        coalesce(p_is_pay, false), p_u_id
    )
    returning * into v_invoice;

    return v_invoice;
end;
$$;

drop function if exists public.fn_invoices_update(
    uuid, text, text, text, text, text, date, text, numeric
);

create or replace function public.fn_invoices_update(
    p_i_id        uuid,
    p_name        text,
    p_inscription text,
    p_email       text,
    p_address     text,
    p_serie       text,
    p_date        date,
    p_billto      text,
    p_total       numeric(12,2),
    p_is_pay      boolean
)
returns public.invoices
language plpgsql
as $$
declare
    v_invoice public.invoices;
begin
    update public.invoices
    set
        i_name        = p_name,
        i_inscription = p_inscription,
        i_email       = p_email,
        i_address     = p_address,
        i_serie       = p_serie,
        i_date        = p_date,
        i_billto      = p_billto,
        i_total       = p_total,
        i_is_pay      = coalesce(p_is_pay, false)
    where i_id = p_i_id
    returning * into v_invoice;

    return v_invoice;
end;
$$;

create or replace function public.fn_invoices_list(
    p_u_id uuid default null
)
returns setof public.invoices
language plpgsql
as $$
begin
    if p_u_id is null then
        return query
        select *
        from public.invoices
        where coalesce(i_is_deleted, false) = false
        order by i_create_at desc;
    else
        return query
        select *
        from public.invoices
        where i_u_id = p_u_id
          and coalesce(i_is_deleted, false) = false
        order by i_create_at desc;
    end if;
end;
$$;

create or replace function public.fn_invoices_list_for_serie(
    p_u_id uuid default null
)
returns setof public.invoices
language plpgsql
as $$
begin
    if p_u_id is null then
        return query
        select *
        from public.invoices
        order by i_create_at desc;
    else
        return query
        select *
        from public.invoices
        where i_u_id = p_u_id
        order by i_create_at desc;
    end if;
end;
$$;

create or replace function public.fn_invoices_summary(
    p_u_id uuid
)
returns table (
    total numeric(12,2),
    total_year numeric(12,2),
    total_month numeric(12,2),
    total_last_month numeric(12,2)
)
language sql
as $$
    select
        coalesce(sum(i_total), 0)::numeric(12,2) as total,
        coalesce(sum(i_total) filter (
            where i_date >= date_trunc('year', current_date)::date
              and i_date < (date_trunc('year', current_date) + interval '1 year')::date
        ), 0)::numeric(12,2) as total_year,
        coalesce(sum(i_total) filter (
            where i_date >= date_trunc('month', current_date)::date
              and i_date < (date_trunc('month', current_date) + interval '1 month')::date
        ), 0)::numeric(12,2) as total_month,
        coalesce(sum(i_total) filter (
            where i_date >= (date_trunc('month', current_date) - interval '1 month')::date
              and i_date < date_trunc('month', current_date)::date
        ), 0)::numeric(12,2) as total_last_month
    from public.invoices
    where i_u_id = p_u_id
      and coalesce(i_is_deleted, false) = false;
$$;

create or replace function public.fn_invoices_delete(
    p_i_id uuid
)
returns void
language plpgsql
as $$
begin
    update public.invoices
    set i_is_deleted = true
    where i_id = p_i_id;
end;
$$;

drop function if exists public.fn_invoice_create_with_details(
    text, text, text, text, text, date, text, numeric, uuid, jsonb
);

create or replace function public.fn_invoice_create_with_details(
    p_name        text,
    p_inscription text,
    p_email       text,
    p_address     text,
    p_serie       text,
    p_date        date,
    p_billto      text,
    p_total       numeric(12,2),
    p_is_pay      boolean,
    p_u_id        uuid,
    p_details     jsonb
)
returns public.invoices
language plpgsql
as $$
declare
    v_invoice   public.invoices;
    v_item      jsonb;
    v_id_number integer;
    v_desc      text;
    v_qty       numeric(12,2);
    v_rate      numeric(12,2);
    v_sale_tax  numeric(12,2);
    v_adress    text;
    v_adress2   text;
begin
    insert into public.invoices (
        i_name, i_inscription, i_email, i_address,
        i_serie, i_date, i_billto, i_total, i_is_pay, i_u_id
    ) values (
        p_name, p_inscription, p_email, p_address,
        p_serie, p_date, p_billto, p_total, coalesce(p_is_pay, false), p_u_id
    )
    returning * into v_invoice;

    if p_details is not null then
        for v_item in
            select value
            from jsonb_array_elements(p_details) as t(value)
        loop
            insert into public.invoice_details (
                id_number,
                id_description,
                id_qty,
                id_rate,
                id_sale_tax,
                id_adress,
                id_adress2,
                id_id
            ) values (
                (v_item->>'id_number')::integer,
                v_item->>'id_description',
                (v_item->>'id_qty')::numeric,
                (v_item->>'id_rate')::numeric,
                nullif(v_item->>'id_sale_tax', '')::numeric,
                v_item->>'id_adress',
                v_item->>'id_adress2',
                v_invoice.i_id
            );
        end loop;
    end if;

    return v_invoice;
end;
$$;

create or replace function public.fn_invoice_update_with_details(
    p_i_id        uuid,
    p_name        text,
    p_inscription text,
    p_email       text,
    p_address     text,
    p_serie       text,
    p_date        date,
    p_billto      text,
    p_total       numeric(12,2),
    p_is_pay      boolean,
    p_details     jsonb
)
returns public.invoices
language plpgsql
as $$
declare
    v_invoice public.invoices;
    v_item    jsonb;
begin
    update public.invoices
    set
        i_name        = p_name,
        i_inscription = p_inscription,
        i_email       = p_email,
        i_address     = p_address,
        i_serie       = p_serie,
        i_date        = p_date,
        i_billto      = p_billto,
        i_total       = p_total,
        i_is_pay      = coalesce(p_is_pay, false)
    where i_id = p_i_id
    returning * into v_invoice;

    if not found then
        raise exception 'Invoice % not found', p_i_id;
    end if;

    delete from public.invoice_details
    where id_id = p_i_id;

    if p_details is not null then
        for v_item in
            select value
            from jsonb_array_elements(p_details) as t(value)
        loop
            insert into public.invoice_details (
                id_number,
                id_description,
                id_qty,
                id_rate,
                id_sale_tax,
                id_adress,
                id_adress2,
                id_id
            ) values (
                (v_item->>'id_number')::integer,
                v_item->>'id_description',
                (v_item->>'id_qty')::numeric,
                (v_item->>'id_rate')::numeric,
                nullif(v_item->>'id_sale_tax', '')::numeric,
                v_item->>'id_adress',
                v_item->>'id_adress2',
                p_i_id
            );
        end loop;
    end if;

    return v_invoice;
end;
$$;
