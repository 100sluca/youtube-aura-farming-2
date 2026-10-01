-- Variante d'accroche (docs/49) : la même vidéo avec une autre accroche et une autre promesse, pour comparer deux
-- accroches sur YouTube. La variante est une copie de la production (mêmes clips, liés sur le disque) avec sa propre
-- vidéo ; variant_of la relie à la vidéo d'origine, pour que l'analyste compare leurs courbes de rétention.

alter table videos add column if not exists variant_of uuid references videos(id) on delete set null;

comment on column videos.variant_of is
  'vidéo d''origine dont celle-ci est une variante d''accroche (docs/49) ; null = vidéo ordinaire';
