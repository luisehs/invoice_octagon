-- Ejecutar en Supabase SQL Editor para habilitar soft delete de invoices.
-- Las invoices con i_is_deleted = true no aparecen en la tabla ni cuentan en sumas.
-- La funcion de serie incluye invoices eliminadas para mantener auditoria.

alter table public.invoices
    add column if not exists i_is_deleted boolean not null default false;

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
