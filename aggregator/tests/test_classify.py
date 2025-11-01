from pipeline.classify import build_classifier
import yaml

def test_classifier_basic():
    rules = yaml.safe_load("""
classify:
  "Выставки": ["выставк"]
  "Новые модели": ["премьера"]
    """)
    clf = build_classifier(rules)
    assert clf("Премьера новой модели", "") == "Новые модели"
    assert clf("Отраслевая выставка прошла", "") == "Выставки"
