-- CREATE: agregar línea de detalle a una invoice
create or replace function public.fn_invoice_details_create(
    p_id_number    integer,
    p_id_description text,
    p_id_qty       numeric(12,2),
    p_id_rate      numeric(12,2),
    p_id_sale_tax  numeric(12,2),
    p_id_adress    text,
    p_id_adress2   text,
    p_id_id        uuid
)
returns public.invoice_details
language plpgsql
as $$
declare
    v_detail public.invoice_details;
begin
    insert into public.invoice_details (
        id_number, id_description, id_qty, id_rate,
        id_sale_tax, id_adress, id_adress2, id_id
    ) values (
        p_id_number, p_id_description, p_id_qty, p_id_rate,
        p_id_sale_tax, p_id_adress, p_id_adress2, p_id_id
    )
    returning * into v_detail;

    return v_detail;
end;
$$;

-- READ: obtener una línea específica por PK compuesta
create or replace function public.fn_invoice_details_get(
    p_id_number integer,
    p_id_id     uuid
)
returns public.invoice_details
language plpgsql
as $$
declare
    v_detail public.invoice_details;
begin
    select *
    into v_detail
    from public.invoice_details
    where id_number = p_id_number
      and id_id     = p_id_id;

    return v_detail;
end;
$$;

-- READ: listar todas las líneas de una invoice
create or replace function public.fn_invoice_details_list_by_invoice(
    p_id_id uuid
)
returns setof public.invoice_details
language plpgsql
as $$
begin
    return query
    select *
    from public.invoice_details
    where id_id = p_id_id
    order by id_number;
end;
$$;

-- UPDATE: actualizar una línea de detalle
create or replace function public.fn_invoice_details_update(
    p_id_number    integer,
    p_id_id        uuid,
    p_id_description text,
    p_id_qty       numeric(12,2),
    p_id_rate      numeric(12,2),
    p_id_sale_tax  numeric(12,2),
    p_id_adress    text,
    p_id_adress2   text
)
returns public.invoice_details
language plpgsql
as $$
declare
    v_detail public.invoice_details;
begin
    update public.invoice_details
    set
        id_description = p_id_description,
        id_qty         = p_id_qty,
        id_rate        = p_id_rate,
        id_sale_tax    = p_id_sale_tax,
        id_adress      = p_id_adress,
        id_adress2     = p_id_adress2
    where id_number = p_id_number
      and id_id     = p_id_id
    returning * into v_detail;

    return v_detail;
end;
$$;

-- DELETE: borrar una línea de detalle
create or replace function public.fn_invoice_details_delete(
    p_id_number integer,
    p_id_id     uuid
)
returns void
language plpgsql
as $$
begin
    delete from public.invoice_details
    where id_number = p_id_number
      and id_id     = p_id_id;
end;
$$;
