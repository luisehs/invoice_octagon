-- Extensión para generar UUIDs (en Supabase normalmente ya está disponible)

create extension if not exists "pgcrypto";

-- Table users
create table if not exists public.users (
    u_id uuid primary key default gen_random_uuid(),
    u_firstname text not null,
    u_lastname text not null,
    u_email text not null unique,
    u_password text not null,
    u_role text not null default 'user',
    u_is_active boolean not null default true,
    u_create_at timestamptz not null default now()
);

-- Table invoices
create table if not exists public.invoices (
    i_id uuid primary key default gen_random_uuid(),
    i_name text not null,
    i_inscription text,
    i_email text,
    i_address text,
    i_serie text,
    i_date date not null,
    i_billto text,
    i_total numeric(12, 2) not null,
    i_u_id uuid not null,
    i_create_at timestamptz not null default now(),
    constraint invoices_user_fk
        foreign key (i_u_id)
        references public.users (u_id)
        on delete restrict
);

-- Table invoice_details
create table if not exists public.invoice_details (
    id_number integer not null,
    id_description text not null,
    id_qty numeric(12, 2) not null,
    id_rate numeric(12, 2) not null,
    id_sale_tax numeric(12, 2),
    id_adress text,
    id_adress2 text,
    id_id uuid not null,
    id_create_at timestamptz not null default now(),
    constraint invoice_details_pk
        primary key (id_number, id_id),
    constraint invoice_details_invoice_fk
        foreign key (id_id)
        references public.invoices (i_id)
        on delete cascade
);
