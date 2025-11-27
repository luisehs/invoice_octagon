-- CREATE: crear usuario
create or replace function public.fn_users_create(
    p_firstname   text,
    p_lastname    text,
    p_email       text,
    p_password    text, -- IMPORTANTE: aquí debe ir YA hasheada
    p_role        text default 'user',
    p_is_active   boolean default true
)
returns public.users
language plpgsql
as $$
declare
    v_user public.users;
begin
    insert into public.users (
        u_firstname, u_lastname, u_email, u_password, u_role, u_is_active
    ) values (
        p_firstname, p_lastname, p_email, p_password, p_role, p_is_active
    )
    returning * into v_user;

    return v_user;
end;
$$;

-- READ: obtener usuario por id
create or replace function public.fn_users_get_by_id(
    p_u_id uuid
)
returns public.users
language plpgsql
as $$
declare
    v_user public.users;
begin
    select *
    into v_user
    from public.users
    where u_id = p_u_id;

    return v_user;
end;
$$;

-- READ: listar todos los usuarios (opcional filtrar activos)
create or replace function public.fn_users_list(
    p_only_active boolean default false
)
returns setof public.users
language plpgsql
as $$
begin
    if p_only_active then
        return query
        select *
        from public.users
        where u_is_active = true
        order by u_create_at desc;
    else
        return query
        select *
        from public.users
        order by u_create_at desc;
    end if;
end;
$$;

-- UPDATE: actualizar usuario
create or replace function public.fn_users_update(
    p_u_id        uuid,
    p_firstname   text,
    p_lastname    text,
    p_email       text,
    p_role        text,
    p_is_active   boolean
)
returns public.users
language plpgsql
as $$
declare
    v_user public.users;
begin
    update public.users
    set
        u_firstname = p_firstname,
        u_lastname  = p_lastname,
        u_email     = p_email,
        u_role      = p_role,
        u_is_active = p_is_active
    where u_id = p_u_id
    returning * into v_user;

    return v_user;
end;
$$;

-- UPDATE: cambiar contraseña (hash ya calculado fuera)
create or replace function public.fn_users_update_password(
    p_u_id        uuid,
    p_new_password text
)
returns public.users
language plpgsql
as $$
declare
    v_user public.users;
begin
    update public.users
    set
        u_password = p_new_password
    where u_id = p_u_id
    returning * into v_user;

    return v_user;
end;
$$;

-- DELETE: eliminar usuario
create or replace function public.fn_users_delete(
    p_u_id uuid
)
returns void
language plpgsql
as $$
begin
    delete from public.users
    where u_id = p_u_id;
end;
$$;
