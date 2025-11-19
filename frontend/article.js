// article.js — страница одной статьи по индексу ?i=...

(function () {
  const NEWS_URLS = [
    "data/news.json",
    "frontend/data/news.json",
  ];

  const articleEl = document.getElementById("article");
  const relatedEl = document.getElementById("related");

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

  function renderNotFound(message) {
    articleEl.innerHTML = `
      <div class="empty-state">
        <h1>Статья не найдена</h1>
        <p>${message}</p>
        <p><a href="index.html" class="news-card-link">Вернуться к ленте</a></p>
      </div>
    `;
  }

  function renderArticle(item, allNews, index) {
    const title = getField(item, ["title", "headline", "name"], "Без заголовка");
    const summary = getField(item, ["summary", "lead", "description"], "");
    const date = fmtDate(getField(item, ["published_at", "date", "pub_date"]));
    const sourceName = getField(item, ["source_name", "source", "site"], "");
    const sourceUrl = getField(item, ["url", "link", "source_url"], "");
    const image = getField(item, ["image_url", "image", "img"], "");
    const tags = item.tags || item.rubrics || [];
    const bodyHtml =
      getField(item, ["content_html", "body_html"]) ||
      getField(item, ["content", "body", "text", "full_text", "article"], summary);

    document.title = `${title} — СпецТрейлеры`;

    articleEl.innerHTML = `
      <header class="article-header">
        <p class="article-breadcrumbs">
          <a href="index.html">Новости</a>
          ${
            tags && tags.length
              ? ` · <span>${tags.map((t) => String(t)).join(", ")}</span>`
              : ""
          }
        </p>
        <h1 class="article-title">${title}</h1>
        <div class="article-meta">
          ${date ? `<span class="article-meta-item">${date}</span>` : ""}
          ${sourceName ? `<span class="article-meta-item">${sourceName}</span>` : ""}
        </div>
      </header>

      ${
        image
          ? `<div class="article-image-wrap"><img src="${image}" alt="" class="article-image"/></div>`
          : ""
      }

      <section class="article-body">
        ${
          bodyHtml && /<\/?[a-z][\s\S]*>/i.test(bodyHtml)
            ? bodyHtml
            : `<p>${(bodyHtml || "").replace(/\n{2,}/g, "</p><p>")}</p>`
        }
      </section>

      <footer class="article-footer">
        ${
          sourceUrl
            ? `<a class="primary-btn" href="${sourceUrl}" target="_blank" rel="noopener noreferrer">
                 Читать в источнике
               </a>`
            : ""
        }
        <a href="index.html" class="secondary-btn">Назад к ленте</a>
      </footer>
    `;

    // Простейшие "похожие материалы": соседние по списку
    relatedEl.innerHTML = "";
    const related = [];

    if (index > 0) related.push(allNews[index - 1]);
    if (index + 1 < allNews.length) related.push(allNews[index + 1]);

    related.forEach((r, idx) => {
      const rIndex =
        idx === 0 && index > 0 ? index - 1 : index + 1;
      const rTitle = getField(r, ["title", "headline", "name"], "Без заголовка");
      const rDate = fmtDate(getField(r, ["published_at", "date", "pub_date"]));

      const a = document.createElement("a");
      a.className = "related-item";
      a.href = `article.html?i=${encodeURIComponent(rIndex)}`;
      a.innerHTML = `
        <span class="related-title">${rTitle}</span>
        ${rDate ? `<span class="related-date">${rDate}</span>` : ""}
      `;
      relatedEl.appendChild(a);
    });
  }

  async function init() {
    const params = new URLSearchParams(window.location.search);
    const iParam = params.get("i");

    const index = parseInt(iParam, 10);
    if (!Number.isFinite(index) || index < 0) {
      renderNotFound("Некорректный параметр ?i в адресе страницы.");
      return;
    }

    let news = [];
    for (const url of NEWS_URLS) {
      try {
        const resp = await fetch(url, { cache: "no-store" });
        if (!resp.ok) continue;
        const data = await resp.json();
        news = Array.isArray(data) ? data : data.items || [];
        break;
      } catch {
        // пробуем следующий URL
      }
    }

    if (!news.length) {
      renderNotFound("Не удалось загрузить базу новостей.");
      return;
    }

    // Сортировка должна полностью совпадать с news.js
    news.sort((a, b) => {
      const da = new Date(
        getField(a, ["published_at", "date", "pub_date"]) || 0
      ).getTime();
      const db = new Date(
        getField(b, ["published_at", "date", "pub_date"]) || 0
      ).getTime();
      return db - da;
    });

    if (index >= news.length) {
      renderNotFound("Новость с таким индексом не найдена.");
      return;
    }

    const item = news[index];
    renderArticle(item, news, index);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
