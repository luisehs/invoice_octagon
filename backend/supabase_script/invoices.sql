create or replace function public.fn_invoice_create_with_details(
    p_name        text,
    p_inscription text,
    p_email       text,
    p_address     text,
    p_serie       text,
    p_date        date,
    p_billto      text,
    p_total       numeric(12,2),
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
        i_serie, i_date, i_billto, i_total, i_u_id
    ) values (
        p_name, p_inscription, p_email, p_address,
        p_serie, p_date, p_billto, p_total, p_u_id
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
