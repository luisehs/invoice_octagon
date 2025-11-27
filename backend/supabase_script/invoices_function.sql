-- CREATE: crear invoice
create or replace function public.fn_invoices_create(
    p_name        text,
    p_inscription text,
    p_email       text,
    p_address     text,
    p_serie       text,
    p_date        date,
    p_billto      text,
    p_total       numeric(12,2),
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
        i_u_id
    ) values (
        p_name, p_inscription, p_email, p_address,
        p_serie, p_date, p_billto, p_total,
        p_u_id
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

-- UPDATE: actualizar invoice
create or replace function public.fn_invoices_update(
    p_i_id        uuid,
    p_name        text,
    p_inscription text,
    p_email       text,
    p_address     text,
    p_serie       text,
    p_date        date,
    p_billto      text,
    p_total       numeric(12,2)
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
        i_total       = p_total
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
