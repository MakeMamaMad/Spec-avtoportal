// frontend/news.js

const NEWS_URL = "./data/news.json";
const META_URL = "./data/news_meta.json"; // если файла нет — просто проигнорируем

const newsListEl = document.getElementById("news-list");
const emptyEl = document.getElementById("news-empty");
const errorEl = document.getElementById("news-error");
const searchInput = document.getElementById("search-input");
const tagSelect = document.getElementById("tag-select");
const topTopicsEl = document.getElementById("top-topics");
const footerYearEl = document.getElementById("footer-year");

if (footerYearEl) {
  footerYearEl.textContent = new Date().getFullYear();
}

// Более-менее универсальный парсер — подстраиваемся под разные форматы JSON
function normalizeNews(raw) {
  if (!raw) return [];
  let items = Array.isArray(raw) ? raw : raw.items || raw.news || raw.data || [];
  if (!Array.isArray(items)) return [];

  return items.map((item, index) => {
    const title =
      item.title ||
      item.headline ||
      item.name ||
      `Новость #${index + 1}`;

    const url = item.url || item.link || null;
    const source = item.source || item.source_name || "";
    const tags = item.tags || item.rubrics || item.categories || [];
    const dt =
      item.published_at ||
      item.pub_date ||
      item.date ||
      item.datetime ||
      null;
    const snippet =
      item.snippet || item.summary || item.description || "";

    return {
      _index: index,
      title,
      url,
      source,
      tags: Array.isArray(tags) ? tags : typeof tags === "string" ? [tags] : [],
      published_at: dt,
      snippet,
    };
  });
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm}.${yyyy}, ${hh}:${mi}`;
}

function setVisible(el, visible) {
  if (!el) return;
  el.classList.toggle("hidden", !visible);
}

function renderNews(items) {
  newsListEl.innerHTML = "";

  if (!items.length) {
    setVisible(emptyEl, true);
    return;
  }
  setVisible(emptyEl, false);

  for (const item of items) {
    const card = document.createElement("article");
    card.className = "news-card";
    card.dataset.index = String(item._index);

    const titleEl = document.createElement("h2");
    titleEl.className = "news-title";
    titleEl.textContent = item.title;

    const metaEl = document.createElement("div");
    metaEl.className = "news-meta";

    if (item.source) {
      const s = document.createElement("span");
      s.className = "news-source";
      s.textContent = item.source;
      metaEl.appendChild(s);
    }

    if (item.published_at) {
      const d = document.createElement("span");
      d.className = "news-date";
      d.textContent = formatDate(item.published_at);
      metaEl.appendChild(d);
    }

    const tagsEl = document.createElement("div");
    tagsEl.className = "news-tags";

    if (item.tags && item.tags.length) {
      item.tags.slice(0, 4).forEach((tag, idx) => {
        const span = document.createElement("span");
        span.className = "tag" + (idx === 0 ? " tag-primary" : "");
        span.textContent = tag;
        tagsEl.appendChild(span);
      });
    }

    const snippetEl = document.createElement("p");
    snippetEl.className = "news-snippet";
    snippetEl.textContent = item.snippet;

    card.appendChild(titleEl);
    card.appendChild(metaEl);
    if (item.tags && item.tags.length) card.appendChild(tagsEl);
    if (item.snippet) card.appendChild(snippetEl);

    card.addEventListener("click", () => {
      // переходим на страницу статьи по индексу
      const url = new URL("./article.html", window.location.href);
      url.searchParams.set("index", String(item._index));
      window.location.href = url.toString();
    });

    newsListEl.appendChild(card);
  }
}

function collectTags(items) {
  const set = new Set();
  for (const n of items) {
    if (n.tags) {
      for (const t of n.tags) {
        if (t) set.add(String(t));
      }
    }
  }
  return [...set].sort();
}

function renderTagFilter(tags) {
  if (!tagSelect) return;
  tagSelect.innerHTML = "";
  const any = document.createElement("option");
  any.value = "";
  any.textContent = "Все";
  tagSelect.appendChild(any);

  for (const tag of tags) {
    const opt = document.createElement("option");
    opt.value = tag;
    opt.textContent = tag;
    tagSelect.appendChild(opt);
  }
}

function renderTopTopics(tags) {
  if (!topTopicsEl) return;
  topTopicsEl.innerHTML = "";
  tags.slice(0, 8).forEach((tag) => {
    const li = document.createElement("li");
    li.textContent = tag;
    topTopicsEl.appendChild(li);
  });
}

async function loadMetaSafe() {
  try {
    const res = await fetch(META_URL, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function main() {
  try {
    const res = await fetch(NEWS_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = await res.json();
    const items = normalizeNews(raw);

    if (!items.length) {
      renderNews([]);
      return;
    }

    let current = items.slice();

    const tags = collectTags(items);
    renderTagFilter(tags);
    renderTopTopics(tags);

    function applyFilters() {
      const q = (searchInput?.value || "").trim().toLowerCase();
      const tag = tagSelect?.value || "";

      current = items.filter((item) => {
        if (tag && !(item.tags || []).includes(tag)) return false;
        if (!q) return true;
        const haystack =
          (item.title || "") +
          " " +
          (item.snippet || "") +
          " " +
          (item.source || "") +
          " " +
          (item.tags || []).join(" ");
        return haystack.toLowerCase().includes(q);
      });

      renderNews(current);
    }

    if (searchInput) {
      searchInput.addEventListener("input", applyFilters);
      window.addEventListener("keydown", (e) => {
        if (e.key === "/" && document.activeElement !== searchInput) {
          e.preventDefault();
          searchInput.focus();
        }
      });
    }
    if (tagSelect) tagSelect.addEventListener("change", applyFilters);

    renderNews(current);
    setVisible(errorEl, false);

    // метаданные можем использовать позже, пока просто грузим «для будущего»
    void loadMetaSafe();
  } catch (err) {
    console.error("Ошибка загрузки новостей:", err);
    setVisible(errorEl, true);
    setVisible(emptyEl, false);
  }
}

main();
