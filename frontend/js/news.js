// ---------- helpers ----------
const $ = (sel, root = document) => root.querySelector(sel);

const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleString("ru-RU", { hour12: false }) : "";

// Глобальное состояние (его заполняет ваш main.js после загрузки news.json)
window.STATE = window.STATE || { all: [], page: 1, per: 24 };

// ---------- сбор источника картинки ----------
function pickImage(item) {
  return (
    item.image ||
    item.img ||
    (Array.isArray(item.images) ? item.images[0] : "") ||
    ""
  );
}

// ---------- карточка ----------
function cardHTML(item) {
  const imgSrc = pickImage(item);
  const title = (item.title || "").trim();
  const source = (item.domain || item.source || "").toString().trim();
  const published = fmtDate(item.published_at);

  const urlParams = new URLSearchParams({
    id: item.id || "",
    u: item.link || "",
  }).toString();

  return `
  <a class="card" href="article.html?${urlParams}">
    <figure class="card__media">
      ${
        imgSrc
          ? `<img class="card__img" src="${imgSrc}" alt="" loading="lazy"
               onerror="this.closest('.card__media').classList.add('noimg'); this.remove()" />`
          : `<div class="card__placeholder"></div>`
      }
    </figure>

    <h3 class="card__title">${title}</h3>

    <div class="card__meta">
      <span class="card__source">${source}</span>
      ${published ? `<span class="card__dot">·</span><span>${published}</span>` : ""}
    </div>

    ${item.summary ? `<p class="card__summary">${item.summary}</p>` : ""}
  </a>`;
}

// ---------- рендер списка ----------
function paint() {
  const root = $("#news-list");
  if (!root) return;

  const { all, page, per } = STATE;
  const start = (page - 1) * per;
  const slice = all.slice(start, start + per);

  root.innerHTML = slice.map(cardHTML).join("");

  // если у вас есть отладочный блок — обновим его
  const info = $("#news-total");
  if (info) {
    const pages = Math.max(1, Math.ceil(all.length / per));
    info.textContent = `total=${all.length}, render=${slice.length}, page=${page}/${pages}, per=${per}`;
  }
}

// ---------- пагинация ----------
function gotoPage(n) {
  const pages = Math.max(1, Math.ceil(STATE.all.length / STATE.per));
  STATE.page = Math.min(Math.max(1, n), pages);
  paint();
}

// Экспорт для вызова из main.js
window.NewsUI = { paint, gotoPage };
