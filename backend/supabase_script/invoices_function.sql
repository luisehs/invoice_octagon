-- CREATE: crear invoice
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

-- READ: obtener invoice por id
create or replace function public.fn_invoices_get_by_id(
    p_i_id uuid
)
returns public.invoices
language plpgsql
as $$
declare
    v_invoice public.invoices;
begin
    select *
    into v_invoice
    from public.invoices
    where i_id = p_i_id;

    return v_invoice;
end;
$$;

-- READ: listar invoices (opcional por usuario)
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
    where i_u_id = p_u_id;
$$;

-- UPDATE: actualizar invoice
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

-- DELETE: eliminar invoice (sus detalles se borran por ON DELETE CASCADE)
create or replace function public.fn_invoices_delete(
    p_i_id uuid
)
returns void
language plpgsql
as $$
begin
    delete from public.invoices
    where i_id = p_i_id;
end;
$$;
