from aggregator.run import apply_rules


def test_apply_rules_excludes_inflected_keywords():
    rules = {
        "exclude": {"keywords": ["зерновоз"]},
        "classify": {"Рынок": ["рынок"]},
    }
    items = [
        {"title": "Новые зерновозы вышли на рынок", "summary": ""},
        {"title": "Рынок полуприцепов вырос", "summary": ""},
    ]

    result = apply_rules(items, rules)

    assert len(result) == 1
    assert result[0]["title"] == "Рынок полуприцепов вырос"
    assert result[0]["category"] == "Рынок"


def test_apply_rules_drops_stale_category_when_not_classified():
    rules = {"exclude": {"keywords": []}, "classify": {"Выставки": ["выставк"]}}
    item = {"title": "Сервисная сеть обновила график", "summary": "", "category": "Старое"}

    result = apply_rules([item], rules)

    assert "category" not in result[0]
