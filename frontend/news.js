// news.js — лента новостей на главной

(function () {
  const NEWS_URLS = [
    "data/news.json",
    "frontend/data/news.json",
  ];

  // Ключ в localStorage для баннера "лента обновилась"
  const STORAGE_KEY = "st_news_first_key_v1";

  const els = {
    list: document.getElementById("news-list"),
    empty: document.getElementById("news-empty"),
    loading: document.getElementById("news-loading"),
    error: document.getElementById("news-error"),
    search: document.getElementById("search"),
    rubricFilters: document.getElementById("rubric-filters"),
    topTags: document.getElementById("top-tags"),
    banner: document.getElementById("news-banner"),
    bannerText: document.getElementById("news-banner-text"),
    bannerBtn: document.getElementById("news-banner-btn"),
  };

  let allNews = [];
  let activeRubric = null;
  let searchQuery = "";

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(+d)) return "";
    const p = (n) => String(n).padStart(2, "0");
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
  }

  function getField(obj, candidates, fallback = "") {
    for (const key of candidates) {
      if (obj && obj[key] != null && obj[key] !== "") return obj[key];
    }
    return fallback;
  }

  function buildRubrics(news) {
    const set = new Set();
    for (const item of news) {
      const tags = item.tags || item.rubrics || [];
      if (Array.isArray(tags)) {
        for (const t of tags) {
          const s = String(t || "").trim();
          if (s) set.add(s);
        }
      }
    }

    els.rubricFilters.innerHTML = "";

    const allBtn = document.createElement("button");
    allBtn.className = "chip chip-active";
    allBtn.textContent = "Все";
    allBtn.dataset.rubric = "";
    els.rubricFilters.appendChild(allBtn);

    [...set].sort().forEach((tag) => {
      const btn = document.createElement("button");
      btn.className = "chip";
      btn.textContent = tag;
      btn.dataset.rubric = tag;
      els.rubricFilters.appendChild(btn);
    });
  }

  function buildTopTags(news) {
    const counter = new Map();
    for (const item of news) {
      const tags = item.tags || item.rubrics || [];
      if (Array.isArray(tags)) {
        for (const t of tags) {
          const key = String(t || "").trim();
          if (!key) continue;
          counter.set(key, (counter.get(key) || 0) + 1);
        }
      }
    }
    const top = [...counter.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);

    els.topTags.innerHTML = "";
    for (const [tag, count] of top) {
      const li = document.createElement("li");
      li.className = "tag-pill";
      li.textContent = `${tag} (${count})`;
      els.topTags.appendChild(li);
    }
  }

  function render() {
    const q = searchQuery.trim().toLowerCase();
    const rubric = activeRubric;

    const filtered = allNews.filter((item) => {
      const title = getField(item, ["title", "headline", "name"]).toLowerCase();
      const tags = (item.tags || item.rubrics || []).map((t) =>
        String(t).toLowerCase()
      );

      if (q && !title.includes(q)) return false;
      if (rubric && !tags.includes(rubric.toLowerCase())) return false;
      return true;
    });

    els.list.innerHTML = "";

    if (!filtered.length) {
      els.empty.hidden = false;
      return;
    }

    els.empty.hidden = true;

    filtered.forEach((item, index) => {
      // Индекс в отсортированном массиве — наш "id" для статьи
      const idx = index;
      const title = getField(item, ["title", "headline", "name"], "Без заголовка");
      const summary = getField(item, ["summary", "lead", "description"], "");
      const date = fmtDate(getField(item, ["published_at", "date", "pub_date"]));
      const sourceName = getField(item, ["source_name", "source", "site"], "");
      const image = getField(item, ["image_url", "image", "img"], "");
      const tags = item.tags || item.rubrics || [];

      const card = document.createElement("article");
      card.className = "news-card";

      card.innerHTML = `
        ${image ? `<div class="news-card-image-wrap"><img src="${image}" alt="" class="news-card-image" loading="lazy"/></div>` : ""}
        <div class="news-card-body">
          <header class="news-card-header">
            <h3 class="news-card-title">
              <a href="article.html?i=${encodeURIComponent(idx)}">${title}</a>
            </h3>
            <div class="news-card-meta">
              ${date ? `<span class="news-card-meta-item">${date}</span>` : ""}
              ${sourceName ? `<span class="news-card-meta-item">${sourceName}</span>` : ""}
            </div>
          </header>
          ${summary ? `<p class="news-card-summary">${summary}</p>` : ""}
          <div class="news-card-footer">
            <a class="news-card-link" href="article.html?i=${encodeURIComponent(idx)}">Читать полностью</a>
            <div class="news-card-tags">
              ${
                Array.isArray(tags)
                  ? tags
                      .map(
                        (t) =>
                          `<button type="button" class="tag-badge" data-tag="${String(
                            t
                          )}">${String(t)}</button>`
                      )
                      .join("")
                  : ""
              }
            </div>
          </div>
        </div>
      `;

      els.list.appendChild(card);
    });
  }

  function handleUpdateBanner(news) {
    if (!els.banner || !news.length) return;

    const first = news[0];
    const firstDate = getField(first, ["published_at", "date", "pub_date"], "");
    const firstTitle = getField(first, ["title", "headline", "name"], "");
    const newKey = `${firstDate}|${firstTitle}`;
    const prevKey = window.localStorage.getItem(STORAGE_KEY);

    // Первый заход — запоминаем состояние, баннер не показываем.
    if (!prevKey) {
      window.localStorage.setItem(STORAGE_KEY, newKey);
      return;
    }

    if (prevKey === newKey) return;

    // Есть обновления. Прикидываем, сколько новостей новее прошлого "первого".
    let diffCount = 0;
    if (prevKey.split("|")[0]) {
      const prevDate = new Date(prevKey.split("|")[0]);
      if (!Number.isNaN(+prevDate)) {
        diffCount = news.filter((n) => {
          const ds = getField(n, ["published_at", "date", "pub_date"], "");
          if (!ds) return false;
          const d = new Date(ds);
          if (Number.isNaN(+d)) return false;
          return d > prevDate;
        }).length;
      }
    }

    if (els.bannerText) {
      els.bannerText.textContent =
        diffCount > 0
          ? `Появилось новых новостей: ${diffCount}`
          : "Лента новостей обновилась";
    }

    els.banner.hidden = false;

    if (els.bannerBtn) {
      els.bannerBtn.addEventListener(
        "click",
        () => {
          els.banner.hidden = true;
          window.localStorage.setItem(STORAGE_KEY, newKey);
        },
        { once: true }
      );
    }
  }

  async function loadNews() {
    for (const url of NEWS_URLS) {
      try {
        const resp = await fetch(url, { cache: "no-store" });
        if (!resp.ok) continue;
        const data = await resp.json();
        allNews = Array.isArray(data) ? data : data.items || [];
        break;
      } catch {
        // пробуем следующий URL
      }
    }

    if (!allNews.length) {
      els.loading.style.display = "none";
      els.error.hidden = false;
      return;
    }

    // Одинаковая сортировка для главной и страницы статьи
    allNews.sort((a, b) => {
      const da = new Date(
        getField(a, ["published_at", "date", "pub_date"]) || 0
      ).getTime();
      const db = new Date(
        getField(b, ["published_at", "date", "pub_date"]) || 0
      ).getTime();
      return db - da;
    });

    buildRubrics(allNews);
    buildTopTags(allNews);
    render();
    handleUpdateBanner(allNews);

    els.loading.style.display = "none";
  }

  function onSearchChange(e) {
    searchQuery = e.target.value || "";
    render();
  }

  function onRubricClick(e) {
    const btn = e.target.closest("button[data-rubric]");
    if (!btn) return;

    activeRubric = btn.dataset.rubric || null;

    for (const el of els.rubricFilters.querySelectorAll(".chip")) {
      el.classList.toggle("chip-active", el === btn);
    }

    render();
  }

  function onTagClickFromCard(e) {
    const btn = e.target.closest("button.tag-badge");
    if (!btn) return;
    const tag = btn.dataset.tag;
    if (!tag) return;

    activeRubric = tag;

    for (const el of els.rubricFilters.querySelectorAll(".chip")) {
      el.classList.toggle("chip-active", el.dataset.rubric === tag);
    }

    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function setupEvents() {
    if (els.search) els.search.addEventListener("input", onSearchChange);
    if (els.rubricFilters)
      els.rubricFilters.addEventListener("click", onRubricClick);
    if (els.list) els.list.addEventListener("click", onTagClickFromCard);

    window.addEventListener("keydown", (e) => {
      if (e.key === "/" && !e.target.closest("input, textarea")) {
        e.preventDefault();
        els.search && els.search.focus();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    setupEvents();
    loadNews();
  });
})();
