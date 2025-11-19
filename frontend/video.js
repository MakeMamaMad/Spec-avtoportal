// video.js
// Страница "Видео": подтягиваем список YouTube-каналов из aggregator/sources.yml

// ВАЖНО: если переименуешь репозиторий или ветку, нужно будет обновить этот URL.
const SOURCES_YAML_URL =
  "https://raw.githubusercontent.com/MakeMamaMad/Spec-avtoportal/main/aggregator/sources.yml";

async function loadYoutubeChannels() {
  const listEl = document.getElementById("video-list");
  const statusEl = document.getElementById("video-status");
  const errorEl = document.getElementById("video-error");
  const emptyEl = document.getElementById("video-empty");

  if (!listEl || !statusEl || !errorEl || !emptyEl) {
    console.warn("[video] required elements not found in DOM");
    return;
  }

  function showStatus(msg) {
    statusEl.textContent = msg;
    statusEl.hidden = false;
    errorEl.hidden = true;
    emptyEl.hidden = true;
  }

  function showError(msg) {
    if (msg) errorEl.textContent = msg;
    statusEl.hidden = true;
    errorEl.hidden = false;
    emptyEl.hidden = true;
  }

  function showEmpty() {
    statusEl.hidden = true;
    errorEl.hidden = true;
    emptyEl.hidden = false;
  }

  try {
    showStatus("Загрузка списка каналов…");

    const resp = await fetch(SOURCES_YAML_URL, { cache: "no-store" });

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }

    const yamlText = await resp.text();

    // js-yaml подключён через CDN в video.html
    const cfg = jsyaml.load(yamlText) || {};
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
      const url = `https://www.youtube.com/channel/${encodeURIComponent(channelId)}`;

      const card = document.createElement("a");
      card.className = "video-card";
      card.href = url;
      card.target = "_blank";
      card.rel = "noopener noreferrer";

      card.innerHTML = `
        <div class="video-card__icon">▶</div>
        <div class="video-card__body">
          <div class="video-card__title">${escapeHtml(name)}</div>
          <div class="video-card__meta">
            YouTube · channel_id: <code>${channelId}</code>
          </div>
          <div class="video-card__hint">
            Откроется в новой вкладке. Добавьте канал в sources.yml — он появится здесь автоматически.
          </div>
        </div>
      `;

      listEl.appendChild(card);
    });
  } catch (err) {
    console.error("[video] failed to load youtube channels", err);
    showError("Не удалось загрузить список каналов. Попробуйте обновить страницу чуть позже.");
  }
}

// простая защита от XSS в имени канала
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

document.addEventListener("DOMContentLoaded", loadYoutubeChannels);
