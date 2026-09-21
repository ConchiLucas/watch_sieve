from datetime import datetime, timezone

from watch_sieve.classification import (
    UNCATEGORIZED,
    classification_catalog,
    classify_title,
    query_classifications,
)
from watch_sieve.store import SiteStatus, TitleRecord


def test_classify_title_uses_first_matching_topic():
    assert classify_title("鹈鹕测试，这个算降智了吗") == "model-eval"
    assert classify_title("[富可敌国] ZeroCat 正式上线") == "relay"
    assert classify_title("8年JAVA 前途渺茫 目前外包全栈 9.5K 坐标重庆") == "career"
    assert classify_title("27届秋招，求佬友们指点下简历") == "career"
    assert classify_title("火山 Agent Plan 避雷") == "agent"
    assert classify_title("中英文之间加空格吗") == UNCATEGORIZED


def test_classification_catalog_and_list(memory_store):
    seen = datetime(2026, 9, 8, 1, tzinfo=timezone.utc)
    memory_store.upsert_site(SiteStatus("v2ex", "V2EX", "https://v2ex.com/", "forum", True, "", seen))
    memory_store.upsert_titles(
        [
            TitleRecord("v2ex", "V2EX", "https://v2ex.com/", "forum", "GPT-6 Astra 建模大赛", "https://v2ex.com/t/1", seen),
            TitleRecord("v2ex", "V2EX", "https://v2ex.com/", "forum", "Android 秒级编译插件 Jugg 开源了", "https://v2ex.com/t/2", seen),
            TitleRecord("linux_do", "LINUX DO", "https://linux.do/", "forum", "请不要把互联网上的戾气带来这里！", "https://linux.do/t/3", seen),
        ]
    )

    catalog = classification_catalog()
    assert catalog.uncategorized.count == 0
    eval_topic = next(item for group in catalog.groups for item in group.topics if item.id == "model-eval")
    opensource = next(item for group in catalog.groups for item in group.topics if item.id == "opensource")
    community = next(item for group in catalog.groups for item in group.topics if item.id == "community")
    assert eval_topic.count == 1
    assert opensource.count == 1
    assert community.count == 1

    page = query_classifications(topic="model-eval")
    assert page.total == 1
    assert page.items[0].title == "GPT-6 Astra 建模大赛"
    assert page.items[0].topic_label == "模型测评 / 降智"
    assert "category_label" not in page.items[0].model_dump()

    filtered = query_classifications(topic="opensource", q="Jugg")
    assert filtered.total == 1
    empty = query_classifications(topic="opensource", site_id="linux_do")
    assert empty.total == 0
