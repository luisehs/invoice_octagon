alter table public.invoices
    add column if not exists i_is_pay boolean not null default false;

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
    -- 1. Crear la invoice (header)
    insert into public.invoices (
        i_name, i_inscription, i_email, i_address,
        i_serie, i_date, i_billto, i_total, i_is_pay, i_u_id
    ) values (
        p_name, p_inscription, p_email, p_address,
        p_serie, p_date, p_billto, p_total, coalesce(p_is_pay, false), p_u_id
    )
    returning * into v_invoice;

    -- 2. Insertar los detalles (líneas)
    if p_details is not null then
        for v_item in
            select value
            from jsonb_array_elements(p_details) as t(value)
        loop
            -- Extraer campos del JSON
            v_id_number := (v_item->>'id_number')::integer;
            v_desc      :=  v_item->>'id_description';
            v_qty       := (v_item->>'id_qty')::numeric;
            v_rate      := (v_item->>'id_rate')::numeric;
            v_sale_tax  := nullif(v_item->>'id_sale_tax', '')::numeric;
            v_adress    :=  v_item->>'id_adress';
            v_adress2   :=  v_item->>'id_adress2';

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
                v_id_number,
                v_desc,
                v_qty,
                v_rate,
                v_sale_tax,
                v_adress,
                v_adress2,
                v_invoice.i_id   -- FK al header recién creado
            );
        end loop;
    end if;

    -- 3. Devolver la invoice creada
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
            v_id_number := (v_item->>'id_number')::integer;
            v_desc      :=  v_item->>'id_description';
            v_qty       := (v_item->>'id_qty')::numeric;
            v_rate      := (v_item->>'id_rate')::numeric;
            v_sale_tax  := nullif(v_item->>'id_sale_tax', '')::numeric;
            v_adress    :=  v_item->>'id_adress';
            v_adress2   :=  v_item->>'id_adress2';

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
                v_id_number,
                v_desc,
                v_qty,
                v_rate,
                v_sale_tax,
                v_adress,
                v_adress2,
                p_i_id
            );
        end loop;
    end if;

    return v_invoice;
end;
$$;
