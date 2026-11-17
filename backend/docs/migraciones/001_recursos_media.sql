-- OPCIONAL. El bot ya lee el material solo desde las carpetas del bucket (ver docs/GUIA_SUBIR_MATERIAL.md).
-- Usa esta tabla solo si quieres leyendas propias o archivos fuera de esas carpetas.
create table if not exists recursos_media (
  id          bigserial primary key,
  cliente     text    not null default 'sague',          -- multi-cliente (SaaS)
  proyecto    text    not null default 'santa_teresa',
  unidad      text    not null default 'ambas',          -- 'casa_1' | 'casa_2' | 'ambas'
  tipo        text    not null,                           -- 'video' | 'ficha' | 'foto_real' | 'render_amoblado'
  ambiente    text,                                       -- 'fachada','sala','cocina','dormitorio','bano','terraza','cochera','jardin','recorrido','planos'
  url         text    not null,                           -- link público del archivo en Storage
  leyenda     text,                                       -- opcional: texto propio; si va vacío el bot usa uno estándar
  orden       int     not null default 0,
  activo      boolean not null default true,
  created_at  timestamptz not null default now(),
  constraint recursos_media_tipo_chk check (tipo in ('video','ficha','foto_real','render_amoblado')),
  constraint recursos_media_unidad_chk check (unidad in ('casa_1','casa_2','ambas'))
);
create index if not exists recursos_media_cliente_idx on recursos_media (cliente, activo, orden);

-- Ejemplos (reemplaza las URLs por las tuyas):
-- insert into recursos_media (unidad, tipo, ambiente, url, orden) values
--  ('casa_1','video','recorrido','https://<proyecto>.supabase.co/storage/v1/object/public/recursos/santa-teresa/casa-1/video/recorrido.mp4', 1),
--  ('casa_2','video','recorrido','https://<proyecto>.supabase.co/storage/v1/object/public/recursos/santa-teresa/casa-2/video/recorrido.mp4', 2),
--  ('casa_1','ficha','planos','https://.../santa-teresa/casa-1/ficha/ficha-casa-1.pdf', 3),
--  ('casa_2','ficha','planos','https://.../santa-teresa/casa-2/ficha/ficha-casa-2.pdf', 4),
--  ('ambas','foto_real','fachada','https://.../santa-teresa/comun/fotos/fachada.jpg', 5),
--  ('ambas','render_amoblado','sala','https://.../santa-teresa/comun/renders/sala-amoblada.jpg', 6),
--  ('casa_1','foto_real','terraza','https://.../santa-teresa/casa-1/fotos/terraza.jpg', 7);
