-- Минимальная схема, если решите перейти на БД Postgres + headless CMS свой
create table sources(
  id serial primary key,
  name text not null,
  url text not null,
  type text check (type in ('manufacturer','media','dealer','regulator')) default 'media'
);

create table posts(
  id serial primary key,
  ext_id text unique,
  title text not null,
  summary text,
  content_html text,
  category text,
  tags text[] default '{}',
  source_id int references sources(id) on delete set null,
  url text,
  published_at timestamptz,
  image text,
  status text check (status in ('draft','review','published','hidden')) default 'review',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index posts_cat_idx on posts(category);
create index posts_published_idx on posts(published_at desc);
