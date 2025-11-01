export const qs = (sel, el=document) => el.querySelector(sel);
export const qsa = (sel, el=document) => Array.from(el.querySelectorAll(sel));
export const html = (strings, ...values) => String.raw({raw:strings}, ...values);
export function timeAgo(dateStr){
  const d = new Date(dateStr);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "только что";
  if (diff < 3600) return Math.floor(diff/60) + " мин назад";
  if (diff < 86400) return Math.floor(diff/3600) + " ч назад";
  return d.toLocaleDateString('ru-RU', {year:'numeric', month:'short', day:'numeric'});
}
export function slugify(s){
  return s.toLowerCase().replace(/[^a-zа-я0-9]+/g, "-").replace(/^-+|-+$/g, "");
}
export function getParam(name){
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}
