// frontend/news.js

const NEWS_URLS = ["./data/news_meta.json", "./data/news.json"];

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm}.${yyyy}, ${hh}:${min}`;
}

function pick(obj, keys, fallback = "") {
  for (const key of keys) {
    const v = obj?.[key];
    if (v !== undefined && v !== null && String(v).trim() !== "") {
      return v;
    }
  }
  return fallback;
}

function normalizeList(raw) {
  const list = Array.isArray(raw)
    ? raw
    : Array.isArray(raw?.items)
    ? raw.items
    : Array.isArray(raw?.news)
    ? raw.news
    : [];

  return list.map((item, idx) => {
    const title = pick(item, ["title", "headline", "name"], "Без названия");
    const summary = pick(
      item,
      ["summary", "description", "lead", "snippet", "text"],
      ""
    );
    const date = pick(item, ["published_at", "pub_date", "date", "timestamp"], "");
    const source = pick(item, ["source", "source_name", "feed", "site"], "");
    const url = pick(item, ["url", "link", "source_url"], "");
    const image = pick(
      item,
      ["image", "image_url", "thumbnail", "cover", "picture"],
      ""
    );

    let tags = [];
    if (Array.isArray(item.tags)) {
      tags = item.tags;
    } else if (typeof item.category === "string") {
      tags = item.category.split(/[;,/]/).map((t) => t.trim()).filter(Boolean);
    }

    return {
      idx,
      raw: item,
      title,
      summary,
      date,
      source,
      url,
      image,
      tags,
    };
  });
}

async function loadNewsData() {
  for (const url of NEWS_URLS) {
    try {
      const resp = await fetch(url, { cache: "no-store" });
      if (!resp.ok) continue;
      const data = await resp.json();
      const list = normalizeList(data);
      if (list.length) return list;
    } catch (e) {
      console.warn("failed to load", url, e);
    }
  }
  throw new Error("no data");
}

function renderTags(allItems) {
  const tagSet = new Map();

  for (const item of allItems) {
    for (const tag of item.tags || []) {
      const key = tag.toLowerCase();
      tagSet.set(key, (tagSet.get(key) || 0) + 1);
    }
  }

  const tags = [...tagSet.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15);

  const filterRoot = document.getElementById("filter-tags");
  const topRoot = document.getElementById("top-tags");
  if (!filterRoot || !topRoot) return;

  filterRoot.innerHTML = "";
  topRoot.innerHTML = "";

  const allBtn = document.createElement("button");
  allBtn.className = "tag-pill tag-pill_active";
  allBtn.textContent = "Все";
  allBtn.dataset.tag = "";
  filterRoot.appendChild(allBtn);

  for (const [tag, count] of tags) {
    const btn = document.createElement("button");
    btn.className = "tag-pill";
    btn.textContent = tag;
    btn.dataset.tag = tag;
    filterRoot.appendChild(btn);

    const li = document.createElement("li");
    li.className = "tag-cloud__item";
    li.textContent = `${tag} · ${count}`;
    topRoot.appendChild(li);
  }
}

function renderList(items) {
  const listRoot = document.getElementById("news-list");
  const emptyEl = document.getElementById("news-empty");
  if (!listRoot) return;

  listRoot.innerHTML = "";

  if (!items.length) {
    if (emptyEl) emptyEl.hidden = false;
    return;
  }
  if (emptyEl) emptyEl.hidden = true;

  for (const item of items) {
    const a = document.createElement("a");
    a.href = `./article.html?idx=${encodeURIComponent(item.idx)}`;
    a.className = "news-card";

    const main = document.createElement("div");
    const aside = document.createElement("div");
    aside.className = "news-card__aside";

    const title = document.createElement("h3");
    title.className = "news-card__title";
    title.textContent = item.title;

    const meta = document.createElement("div");
    meta.className = "news-card__meta";

    if (item.source) {
      const src = document.createElement("span");
      src.className = "news-card__meta-badge";
      src.textContent = item.source;
      meta.appendChild(src);
    }

    if (item.date) {
      const date = document.createElement("span");
      date.textContent = formatDate(item.date);
      meta.appendChild(date);
    }

    const summary = document.createElement("p");
    summary.className = "news-card__summary";
    summary.textContent = item.summary || "Подробности — в карточке новости.";

    main.appendChild(title);
    main.appendChild(meta);
    main.appendChild(summary);

    if (item.image) {
      const img = document.createElement("img");
      img.className = "news-card__thumb";
      img.src = item.image;
      img.alt = "";
      aside.appendChild(img);
    }

    const more = document.createElement("div");
    more.className = "news-card__more";
    more.textContent = "Читать полностью →";
    aside.appendChild(more);

    a.appendChild(main);
    a.appendChild(aside);
    listRoot.appendChild(a);
  }
}

function setupInteractions(allItems) {
  const searchInput = document.getElementById("search-input");
  const filterRoot = document.getElementById("filter-tags");
  const errorEl = document.getElementById("news-error");

  let activeTag = "";
  let query = "";

  function applyFilter() {
    const q = query.trim().toLowerCase();
    const tag = activeTag;

    const filtered = allItems.filter((item) => {
      if (tag && !(item.tags || []).some((t) => t.toLowerCase() === tag)) {
        return false;
      }
      if (!q) return true;
      const haystack = [
        item.title,
        item.summary,
        item.source,
        (item.tags || []).join(" "),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });

    renderList(filtered);
    if (errorEl) errorEl.hidden = true;
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      query = searchInput.value || "";
      applyFilter();
    });

    window.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement !== searchInput) {
        e.preventDefault();
        searchInput.focus();
      }
    });
  }

  if (filterRoot) {
    filterRoot.addEventListener("click", (e) => {
      const btn = e.target.closest(".tag-pill");
      if (!btn) return;

      activeTag = btn.dataset.tag || "";
      for (const el of filterRoot.querySelectorAll(".tag-pill")) {
        el.classList.toggle("tag-pill_active", el === btn);
      }
      applyFilter();
    });
  }

  applyFilter();
}

async function init() {
  const errorEl = document.getElementById("news-error");
  try {
    const list = await loadNewsData();
    renderTags(list);
    setupInteractions(list);
  } catch (e) {
    console.error(e);
    if (errorEl) {
      errorEl.hidden = false;
    }
  }
}

document.addEventListener("DOMContentLoaded", init);
