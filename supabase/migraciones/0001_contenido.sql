-- ============================================================
-- Adlek — ideador de contenido
--
-- Cinco tablas nuevas en el mismo proyecto "Adlek DataBase" donde ya viven
-- las propuestas. No toca nada de lo que ya existe: solo agrega.
--
-- Reutiliza dos cosas que ya estaban: la función `public.es_socio()` (la
-- lista de correos con permiso) y el trigger `public.tocar_editada_en()`.
-- Para dar acceso a alguien, se sigue editando SOLO esa función.
--
-- Es idempotente: se puede volver a correr sin romper nada.
-- ============================================================

-- ── clientes ────────────────────────────────────────────────
-- Agregar un cliente nuevo es insertar una fila aquí. Nunca tocar código.
--
-- `perfil` guarda la marca, el vocero, servicios, pilares y CTAs permitidos.
-- `conocimiento` es texto libre para contexto adicional (por ejemplo, un
-- informe sobre cómo habla el cliente o su criterio profesional): se inyecta
-- en los prompts tal cual, y por eso está separado del perfil estructurado.

create table if not exists public.clientes (
  id           uuid primary key default gen_random_uuid(),
  nombre       text not null,
  slug         text not null unique,
  perfil       jsonb not null default '{}'::jsonb,
  conocimiento text not null default '',
  activo       boolean not null default true,
  creado_en    timestamptz not null default now(),
  editado_en   timestamptz not null default now()
);

create index if not exists clientes_activo_idx
  on public.clientes (activo, nombre);

-- ── generaciones ────────────────────────────────────────────
-- Una fila por tema pedido. El worker las procesa en orden de llegada.
--
-- `estado` se valida con un CHECK y no con un tipo enum de Postgres a
-- propósito: agregar un estado nuevo a un enum obliga a un ALTER TYPE que no
-- corre dentro de una transacción. Con CHECK es un ALTER TABLE normal.
--
-- `latido_en` lo escribe el worker cada pocos segundos mientras trabaja. Si el
-- contenedor se reinicia a media generación, esa marca deja de avanzar y el
-- propio worker la encuentra y la marca como error en vez de dejarla colgada
-- para siempre.

create table if not exists public.generaciones (
  id                 uuid primary key default gen_random_uuid(),
  cliente_id         uuid not null references public.clientes (id) on delete restrict,
  tema               text not null,
  audiencia          text not null default '',
  plataforma         text not null default 'ambas',
  num_ideas          integer not null default 5,
  usar_investigacion boolean not null default true,
  estado             text not null default 'pendiente',
  progreso           integer not null default 0,
  detalle            text not null default '',
  investigacion      text not null default '',
  error_msg          text,
  advertencias       jsonb not null default '[]'::jsonb,
  tokens_entrada     integer not null default 0,
  tokens_salida      integer not null default 0,
  num_imagenes       integer not null default 0,
  latido_en          timestamptz,
  creada_por         uuid references auth.users (id) on delete set null,
  creada_en          timestamptz not null default now(),
  editada_en         timestamptz not null default now(),

  constraint generaciones_estado_valido check (estado in (
    'pendiente', 'investigando', 'generando_ideas',
    'generando_piezas', 'completado', 'error'
  )),
  constraint generaciones_plataforma_valida check (plataforma in (
    'tiktok', 'youtube', 'ambas'
  )),
  constraint generaciones_num_ideas_valido check (num_ideas between 1 and 10),
  constraint generaciones_progreso_valido check (progreso between 0 and 100)
);

create index if not exists generaciones_creada_en_idx
  on public.generaciones (creada_en desc);

-- El worker pregunta constantemente "¿hay algo pendiente?". Este índice
-- parcial hace que esa consulta no recorra el historial completo.
create index if not exists generaciones_pendientes_idx
  on public.generaciones (creada_en)
  where estado = 'pendiente';

create index if not exists generaciones_activas_idx
  on public.generaciones (estado, latido_en)
  where estado in ('investigando', 'generando_ideas', 'generando_piezas');

-- ── ideas ───────────────────────────────────────────────────
-- `data` guarda la idea completa tal como la devolvió el modelo. Se guarda el
-- objeto entero y no columna por columna porque el esquema de una idea puede
-- cambiar al editar un prompt, y no queremos una migración cada vez.

create table if not exists public.ideas (
  id            uuid primary key default gen_random_uuid(),
  generacion_id uuid not null references public.generaciones (id) on delete cascade,
  orden         integer not null,
  data          jsonb not null,
  creada_en     timestamptz not null default now(),
  unique (generacion_id, orden)
);

create index if not exists ideas_generacion_idx
  on public.ideas (generacion_id, orden);

-- ── piezas ──────────────────────────────────────────────────
-- Las cuatro piezas de cada idea. Una fila por pieza para poder regenerar una
-- sola (los ganchos de la idea 3, por ejemplo) sin tocar las demás.

create table if not exists public.piezas (
  id         uuid primary key default gen_random_uuid(),
  idea_id    uuid not null references public.ideas (id) on delete cascade,
  tipo       text not null,
  data       jsonb,
  estado     text not null default 'completado',
  error_msg  text,
  creada_en  timestamptz not null default now(),
  editada_en timestamptz not null default now(),

  constraint piezas_tipo_valido check (tipo in (
    'tiktok', 'youtube', 'ganchos', 'prompts_imagen'
  )),
  constraint piezas_estado_valido check (estado in (
    'pendiente', 'generando', 'completado', 'error'
  )),
  unique (idea_id, tipo)
);

create index if not exists piezas_idea_idx on public.piezas (idea_id);

-- ── imagenes ────────────────────────────────────────────────
-- Se generan bajo demanda, nunca automáticamente: 10 imágenes por idea y 5
-- ideas por tema serían 50 llamadas de las que casi ninguna se usa.
--
-- Cada prompt es una fila propia. En el workflow de n8n se generaban 10 y se
-- guardaban 8; aquí eso no puede pasar, y una que falle deja su `error_msg`
-- sin arrastrar a las demás.

create table if not exists public.imagenes (
  id         uuid primary key default gen_random_uuid(),
  idea_id    uuid not null references public.ideas (id) on delete cascade,
  orden      integer not null,
  prompt     text not null,
  url        text,
  estado     text not null default 'pendiente',
  error_msg  text,
  creada_en  timestamptz not null default now(),

  constraint imagenes_estado_valido check (estado in (
    'pendiente', 'generando', 'completado', 'error'
  )),
  unique (idea_id, orden)
);

create index if not exists imagenes_idea_idx on public.imagenes (idea_id, orden);

-- ── editada_en se actualiza sola ────────────────────────────
-- Reutiliza la función que ya existe para las propuestas.

drop trigger if exists clientes_editada_en on public.clientes;
create trigger clientes_editada_en
  before update on public.clientes
  for each row execute function public.tocar_editada_en();

drop trigger if exists piezas_editada_en on public.piezas;
create trigger piezas_editada_en
  before update on public.piezas
  for each row execute function public.tocar_editada_en();

-- `generaciones` no lleva este trigger: la función escribe en `editada_en`,
-- pero el worker actualiza esa fila cada pocos segundos con el latido y el
-- progreso, así que ahí `editada_en` se mantiene sola de todos modos.
drop trigger if exists generaciones_editada_en on public.generaciones;
create trigger generaciones_editada_en
  before update on public.generaciones
  for each row execute function public.tocar_editada_en();

-- ── Seguridad ───────────────────────────────────────────────
-- Las mismas dos barreras que protegen las propuestas:
--   1. RLS: sin sesión no se ve nada.
--   2. `es_socio()`: y con sesión, solo si tu correo está en la lista.
--
-- El backend en el VPS usa la service_role key, que salta RLS por diseño: es
-- quien escribe los resultados. Esa llave vive solo en EasyPanel, nunca en el
-- panel ni en el navegador.
--
-- auth.uid() y es_socio() van envueltos en un select para que Postgres los
-- evalúe una vez por consulta y no una vez por fila.

alter table public.clientes     enable row level security;
alter table public.generaciones enable row level security;
alter table public.ideas        enable row level security;
alter table public.piezas       enable row level security;
alter table public.imagenes     enable row level security;

do $$
declare
  t text;
begin
  foreach t in array array['clientes', 'generaciones', 'ideas', 'piezas', 'imagenes']
  loop
    execute format('drop policy if exists "%s: leer solo socios" on public.%I', t, t);
    execute format(
      'create policy "%s: leer solo socios" on public.%I for select
         to authenticated using ((select public.es_socio()))', t, t);

    execute format('drop policy if exists "%s: crear solo socios" on public.%I', t, t);
    execute format(
      'create policy "%s: crear solo socios" on public.%I for insert
         to authenticated with check ((select public.es_socio()))', t, t);

    execute format('drop policy if exists "%s: editar solo socios" on public.%I', t, t);
    execute format(
      'create policy "%s: editar solo socios" on public.%I for update
         to authenticated using ((select public.es_socio()))
         with check ((select public.es_socio()))', t, t);

    execute format('drop policy if exists "%s: borrar solo socios" on public.%I', t, t);
    execute format(
      'create policy "%s: borrar solo socios" on public.%I for delete
         to authenticated using ((select public.es_socio()))', t, t);
  end loop;
end
$$;
