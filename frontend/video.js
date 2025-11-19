// video.js
// Страница "Видео": строим плейлисты и отдельные ролики по данным из aggregator/sources.yml

const SOURCES_YAML_URL =
  "https://raw.githubusercontent.com/MakeMamaMad/Spec-avtoportal/main/aggregator/sources.yml";

document.addEventListener("DOMContentLoaded", () => {
  loadYoutubeSection().catch((err) => {
    console.error("[video] unexpected error", err);
  });
});

async function loadYoutubeSection() {
  const listEl = document.getElementById("video-list");
  const statusEl = document.getElementById("video-status");
  const errorEl = document.getElementById("video-error");
  const emptyEl = document.getElementById("video-empty");

  if (!listEl || !statusEl || !errorEl || !emptyEl) {
    console.warn("[video] required DOM elements not found");
    return;
  }

  const showStatus = (msg) => {
    statusEl.textContent = msg;
    statusEl.hidden = false;
    errorEl.hidden = true;
    emptyEl.hidden = true;
  };

  const showError = (msg) => {
    if (msg) errorEl.textContent = msg;
    statusEl.hidden = true;
    errorEl.hidden = false;
    emptyEl.hidden = true;
  };

  const showEmpty = () => {
    statusEl.hidden = true;
    errorEl.hidden = true;
    emptyEl.hidden = false;
  };

  showStatus("Загружаем конфигурацию каналов…");

  let cfg;
  try {
    const resp = await fetch(SOURCES_YAML_URL, { cache: "no-store" });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const yamlText = await resp.text();
    cfg = jsyaml.load(yamlText) || {};
  } catch (err) {
    console.error("[video] failed to fetch sources.yml", err);
    showError("Не удалось загрузить файл sources.yml.");
    return;
  }

  const youtube = Array.isArray(cfg.youtube) ? cfg.youtube : [];
  if (!youtube.length) {
    showEmpty();
    return;
  }

  statusEl.hidden = true;
  listEl.innerHTML = "";

  youtube.forEach((ch) => {
    const channelId = ch.channel_id || ch.id || ch.channelId;
    if (!channelId) return;

    const name = ch.name || `Канал ${channelId}`;
    const channelUrl = `https://www.youtube.com/channel/${encodeURIComponent(
      channelId
    )}`;
    const videos = Array.isArray(ch.videos) ? ch.videos : [];

    // Пытаемся построить плейлист "Загрузки" на случай, если videos не указан
    let playlistId = null;
    if (channelId.startsWith("UC") && channelId.length > 2) {
      playlistId = "UU" + channelId.slice(2);
    }

    const card = document.createElement("article");
    card.className = "video-card";

    const titleHtml = `
      <h3 class="video-card__title">${escapeHtml(name)}</h3>
      <p class="video-card__meta">
        YouTube · channel_id: <code>${channelId}</code>
      </p>
    `;

    let playersHtml = "";

    if (videos.length) {
      // Рисуем несколько отдельных роликов
      const slice = videos.slice(0, 6); // максимум 6, чтобы страница не умерла
      playersHtml =
        '<div class="video-card__grid">' +
        slice
          .map((videoId) => {
            const src = `https://www.youtube.com/embed/${encodeURIComponent(
              videoId
            )}`;
            return `
              <div class="video-card__player">
                <iframe
                  src="${src}"
                  loading="lazy"
                  title="${escapeHtml(name)} — видео"
                  frameborder="0"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowfullscreen
                ></iframe>
              </div>
            `;
          })
          .join("") +
        "</div>";
    } else if (playlistId) {
      // Фолбэк: один плеер с плейлистом загрузок
      const src = `https://www.youtube.com/embed/videoseries?list=${encodeURIComponent(
        playlistId
      )}`;
      playersHtml = `
        <div class="video-card__player">
          <iframe
            src="${src}"
            loading="lazy"
            title="${escapeHtml(name)} — плейлист"
            frameborder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowfullscreen
          ></iframe>
        </div>
      `;
    } else {
      playersHtml = `
        <div class="video-card__player video-card__player--placeholder">
          Не удалось построить плейлист для этого канала.
        </div>
      `;
    }

    const footerHtml = `
      <div class="video-card__footer">
        <a href="${channelUrl}" target="_blank" rel="noopener noreferrer"
           class="primary-btn primary-btn-sm">
          Открыть канал на YouTube
        </a>
      </div>
    `;

    card.innerHTML = `
      ${titleHtml}
      ${playersHtml}
      ${footerHtml}
    `;

    listEl.appendChild(card);
  });
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
