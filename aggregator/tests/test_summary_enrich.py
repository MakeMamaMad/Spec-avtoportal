from aggregator.pipeline.enrich import extract_summary
from aggregator.translate_news import should_translate_item


def test_extract_summary_prefers_meta_description():
    html = """
    <html><head>
      <meta name="description" content="Подробный анонс новости о рынке грузовой техники и прицепов длиной больше пятидесяти символов.">
    </head><body><article>Другой текст статьи.</article></body></html>
    """
    summary = extract_summary(html, "Заголовок")
    assert summary.startswith("Подробный анонс новости")


def test_partial_translation_is_queued():
    item = {
        "domain": "globaltrailermag.com",
        "title": "Рынок прицепов расширяется",
        "summary": "Manufacturers report higher demand for trailers.",
    }
    assert should_translate_item(item) is True


def test_fully_translated_item_is_not_queued():
    item = {
        "domain": "globaltrailermag.com",
        "title": "Рынок прицепов расширяется",
        "summary": "Производители сообщают о росте спроса.",
        "translation_status": "ru",
    }
    assert should_translate_item(item) is False
