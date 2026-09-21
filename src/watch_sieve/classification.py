from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from watch_sieve.store import canonical_key, get_store
from watch_sieve.titles import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

UNCATEGORIZED = "uncategorized"
CLASSIFIER_REVISION = 1


@dataclass(frozen=True)
class TopicDef:
    id: str
    label: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class TopicGroup:
    id: str
    label: str
    topic_ids: tuple[str, ...]


# First matching topic wins. Keep 中转 / 测评 / 额度 ahead of generic AI words.
TOPIC_DEFS: tuple[TopicDef, ...] = (
    TopicDef(
        "relay",
        "中转站 / 反代 / 公益站",
        (
            "富可敌国", "中转", "公益站", "sub2api", "4Router", "AIHUB", "ZeroCat", "SoleAPI", "Nexa", "Krill",
            "快跑AI", "luckyg", "号池", "聚合站", "如何做一个好的中转", "反代", "CPA", "cpa", "WorkBuddy",
            "luna", "terra", "渠道分享", "chat2api", "OOIOO", "基元", "rabisu", "Searchix",
        ),
    ),
    TopicDef(
        "payment",
        "支付 / 礼品卡 / 区号",
        (
            "礼品卡", "USDT", "Bybit", "google play", "教育邮箱", "帕米尔", "国内怎么直冲", "改区", "菲区",
            "PayPal", "Paypal", "Wise", "中银", "接码", "edu", "TenPay", "Starryblu", "开通菲",
        ),
    ),
    TopicDef(
        "model-eval",
        "模型测评 / 降智",
        (
            "鹈鹕", "降智", "智商监测", "骑车", "建模大赛", "羊道", "魔塔", "宇宙飞船", "波奇酱",
            "越思考越傻", "网页端智力", "品鉴", "跑分", "每日一测", "黑洞测试", "灰测", "暗改",
            "斩杀", "胡言乱语", "智商", " Sol",
        ),
    ),
    TopicDef(
        "carpool",
        "拼车 / 卖号",
        ("拼车", "车队", "上车", "临期", "嘀嘀", "48team", "48 team", "k12子号", "送个k12", "空间号"),
    ),
    TopicDef(
        "quota",
        "订阅额度 / 封号退款",
        (
            "额度", "重置", "Plus不", "plus不", "不重置", "配额缩水", "Tibo", "tibo", "TIBO", "20x", "20X",
            "Pro 20", "pro 20", "team号", "5h限制", "封号", "退款", "砍额度", "Coding Plan", "coding plan",
            "订阅方案", "升级pro", "土区", "team 5x", "Plus 还不", "plus订阅", "plus", "pro20",
        ),
    ),
    TopicDef(
        "giveaway",
        "羊毛 / 抽奖 / 发 Key",
        (
            "抽奖", "瑞幸", "羊毛", "分享几个key", "分享Tokens", "送$1000", "抽3个", "抽10杯", "marvis",
            "深夜福利", "免费蹬", "教师节福利", "新人福利", "免费兑换",
        ),
    ),
    TopicDef(
        "relationship",
        "情感 / 婚姻",
        (
            "离婚", "婚姻", "择偶", "未婚妻", "表白", "妈妈的爱", "结婚", "离世", "感情终章", "恋爱",
            "人格剖析", "人生迷茫", "人生十二问", "不会结婚",
        ),
    ),
    TopicDef(
        "career",
        "职场 / 求职 / 转行",
        (
            "转行", "外包", "辞退", "拉人头", "软考", "前途渺茫", "招人", "找开发", "职位的界限", "领导的ai",
            "9.5K", "秋招", "裁员", "简历", "招聘", "实习", "就业", "团建", "月薪", "招一起", "找新的工作",
            "投递", "专业壁垒", "工程能力断层",
        ),
    ),
    TopicDef(
        "life",
        "生活 / 家居 / 出行",
        (
            "停车", "铁锅", "物业", "买车", "驾照", "国庆", "旅游", "南京", "黑头", "蛋白粉", "吸烟", "赐名",
            "道观", "押金", "小黄鱼", "10086", "健身", "凯美瑞", "游泳", "减脂", "拔牙", "髋", "跑步",
            "火车票", "宽带", "外卖", "蚊子", "早睡", "饮料", "播客", "业委会", "培训班", "共享单车",
            "熬夜", "京哈", "无聊", "夜市", "定居在", "新西兰电话", "国外手机卡", "国外手机号",
        ),
    ),
    TopicDef(
        "community",
        "站务 / 社区活动",
        (
            "飞升", "头像", "戾气", "L站是不是", "偷菜", "秘密花园", "吃💊", "梗图", "收藏数量",
            "等级小助手", "板块申请", "CPAMP", "黑与白", "徽章", "新人报道", "等级要求", "动态签名",
            "L友", "linux.do", "L 站", "L站", "水一贴", "请交作业",
        ),
    ),
    TopicDef(
        "security",
        "安全 / 账号风险",
        ("木马", "蜜罐", "号被盗", "扫KEY", "学习版游戏", "病毒", "蠕虫", "指纹浏览器", "卡巴斯基", "反诈", "隐私风险"),
    ),
    TopicDef("local-gpu", "本地部署 / GPU", ("5060", "dgx", "spark gb10", "本地部署")),
    TopicDef(
        "finance",
        "投资 / 理财",
        ("A 股", "投资一定", "招行卡", "量化选股", "割肉", "回购", "散户", "本金", "天才交易员", "记账"),
    ),
    TopicDef(
        "current-events",
        "时事 / 社会",
        ("华为 AI", "4岁小孩", "毛泽东", "核反应堆", "智能算力", "韩国电力", "蠢人", "天生坏种"),
    ),
    TopicDef("games", "游戏 / 电竞", ("LGD", "IG VS", "宝可梦", "塔防", "挂机游戏", "王者灵宝", "斗蛐蛐")),
    TopicDef(
        "sidehustle",
        "副业 / 创业 / 出海",
        ("副业", "创业失败", "盈利的网站", "opc 出海", "游戏开发平台", "做点硬件", "创业公司"),
    ),
    TopicDef(
        "cloud",
        "云主机 / 域名",
        ("甲骨文", "Oracle", "VPS", "vps", "域名那么贵", "vmiss", "NAS", "飞牛"),
    ),
    TopicDef(
        "proxy",
        "代理 / 机场 / 电话卡",
        (
            "clash", "Clash", "Surge", "挂啥节点", "AxisNow", "翻墙", "vpn吗", "机场", "电话卡",
            "随身wifi", "大流量月包", "voxi", "tg账号",
        ),
    ),
    TopicDef(
        "model-news",
        "新模型 / 业界新闻",
        (
            "邀测", "内测招募", "出新模型", "新模型了", "Grok 4.7", "张一鸣", "声明稿", "WeMM", "Kotlin",
            "具身智能", "MiMo", "Mimo", "MIMO", "deepseek出新", "deepseek要疯", "百度的模型",
            "Gemini突然掉队", "AppStore 可能取消", "Appsotre", "DeepMind", "AlphaGenome", "Mercury",
            "Navier", "NS 方程", "NS方程", "千禧年", "下一代模型", "国产模型", "梁圣", "opus 5.1",
            "v4.1", "V4.1", "公开测试", "讯飞", "商汤", "扩散模型", "oai下一代", "OpenAI已发布",
        ),
    ),
    TopicDef(
        "agent",
        "Agent / Skill / 编程工作流",
        (
            "Skill", "SKILL", "skill", "vibe coding", "worktree", "Subagents", "Hermes", "trellis",
            "PI-Desktop", "Headless", "langchain", "知识库", "日程规划", "读CAD", "vibe", "Agent",
            "agent plan", "Agent Plan", "opencode", "OpenCode", "command code", "command go",
            "commond go", "antigravity", "反重力", "Cline", "zcode", "MCP", "写代码", "cc switch", "ui自动化",
        ),
    ),
    TopicDef("codex", "Codex 使用 / 故障", ("Codex", "codex")),
    TopicDef(
        "opensource",
        "开源 / 独立开发 / 学习",
        (
            "开源", "Jugg", "Readest", "墨客", "导航站", "博客设计", "图解 DMA", "DDIA", "Java 全栈",
            "2K Stars", "架构大佬", "小工具", "JSON在线", "Vocat", "青柠", "libcr", "页面设计",
            "UI设计", "CachyOS", "学术文献",
        ),
    ),
    TopicDef(
        "gadgets",
        "数码 / 硬件 / 系统",
        (
            "显示器", "键盘", "插头", "N90", "热点", "iptv", "C盘", "塞班", "输入法", "macos",
            "Mac", "双系统", "Ubuntu", "澎程", "壁纸", "Windows实验",
        ),
    ),
    TopicDef(
        "creative",
        "AI 写作 / 生图 / 创作",
        (
            "生图", "换脸", "写作", "遗憾感", "文艺风", "一语成美图", "生成游戏", "生成《", "P图",
            "AI画", "视频模型", "PPT", "Q版", "flow平台", "武松", "Markdown",
        ),
    ),
    TopicDef(
        "tools",
        "软件故障 / 工具求助",
        (
            "overloaded", "at capacity", "Telegram", "云盘好用", "抖音视频", "企业微信", "自动回复",
            "代替123云盘", "夸克网盘", "微信群", "微信里的聊天", "油猴脚本", "LD士多", "thinking a bit more",
        ),
    ),
    TopicDef(
        "model-compare",
        "模型对比 / 用法问答",
        (
            "豆包", "哈基米", "Fable", "上下文", "破限", "写作风格", "日用和做数学", "哪个模型",
            "什么模型", "国产模型审美", "用什么模型", "模型比较好", "怎么选模型",
        ),
    ),
    TopicDef(
        "ai-misc",
        "AI 用法杂帖",
        (
            "GPT", "gpt", "Claude", "claude", "Astra", "Gemini", "gemini", "Deepseek", "DeepSeek",
            "grok", "token", "Kimi", "GLM", "glm", "OpenAI", "OPENAI", "OAI", "ChatGPT", "chatgpt",
            "AI", "ai", "模型",
        ),
    ),
)

TOPIC_GROUPS: tuple[TopicGroup, ...] = (
    TopicGroup("ai", "AI 用量", ("model-eval", "relay", "ai-misc", "model-news", "quota", "model-compare", "giveaway", "carpool", "payment", "creative")),
    TopicGroup("dev", "开发", ("agent", "codex", "opensource")),
    TopicGroup("life", "生活与社区", ("life", "community", "career", "relationship")),
    TopicGroup(
        "other",
        "其他",
        ("tools", "gadgets", "proxy", "cloud", "sidehustle", "finance", "security", "current-events", "games", "local-gpu"),
    ),
)

TOPIC_BY_ID = {item.id: item for item in TOPIC_DEFS}
KNOWN_TOPIC_IDS = {UNCATEGORIZED, *TOPIC_BY_ID}


class ClassificationTopic(BaseModel):
    id: str
    label: str
    count: int


class ClassificationGroup(BaseModel):
    id: str
    label: str
    topics: list[ClassificationTopic]


class ClassificationCatalog(BaseModel):
    uncategorized: ClassificationTopic
    groups: list[ClassificationGroup]


class ClassificationRow(BaseModel):
    title: str
    url: str = ""
    site_id: str
    site_name: str
    topic_id: str
    topic_label: str
    fetched_at: datetime | None = None


class ClassificationPage(BaseModel):
    topic_id: str
    topic_label: str
    total: int
    page: int
    page_size: int
    items: list[ClassificationRow] = Field(default_factory=list)


def topic_label(topic_id: str) -> str:
    if topic_id == UNCATEGORIZED:
        return "未分类"
    mapped = TOPIC_BY_ID.get(topic_id)
    return mapped.label if mapped else "未分类"


def normalize_topic_id(topic_id: str) -> str:
    value = topic_id.strip() or UNCATEGORIZED
    return value if value in KNOWN_TOPIC_IDS else UNCATEGORIZED


def _title_has(title: str, keyword: str) -> bool:
    if keyword.isascii():
        if len(keyword) <= 3:
            # Allow gpt6 / pro20x: only require a leading boundary.
            return re.search(rf"(?<![A-Za-z0-9]){re.escape(keyword)}", title, re.I) is not None
        return keyword.lower() in title.lower()
    return keyword in title


def classify_title(title: str) -> str:
    for item in TOPIC_DEFS:
        if any(_title_has(title, keyword) for keyword in item.keywords):
            return item.id
    return UNCATEGORIZED


def topic_choices_text() -> str:
    lines = [f"{UNCATEGORIZED} {topic_label(UNCATEGORIZED)}"]
    lines.extend(f"{item.id} {item.label}" for item in TOPIC_DEFS)
    return "\n".join(lines)


def build_classify_prompt(titles: list[tuple[int, str]]) -> str:
    numbered = "\n".join(f"{index}. {title}" for index, title in titles)
    return (
        "你是论坛标题分类器。从下列类别中为每条标题选一个最贴切的 topic_id。"
        "只选一个；不确定、水帖或闲聊用 uncategorized。"
        "\n类别：\n"
        + topic_choices_text()
        + "\n输出 JSON 数组，每项: "
        '{"id": n, "topic_id": "类别id", "reason": "简短中文原因"}。\n'
        "标题：\n"
        + numbered
    )


def resolve_topic_id(title: str, site_id: str, url: str, stored: dict[tuple[str, str], str]) -> str:
    stored_id = stored.get((site_id, canonical_key(title, url)))
    if stored_id:
        return normalize_topic_id(stored_id)
    return classify_title(title)


def classify_rows(q: str = "", site_id: str = "") -> list[ClassificationRow]:
    keyword = q.strip().lower()
    stored = get_store().list_title_topic_ids()
    rows: list[ClassificationRow] = []
    for item in get_store().list_title_rows():
        if keyword and keyword not in item.title.lower():
            continue
        if site_id and item.site_id != site_id:
            continue
        topic_id = resolve_topic_id(item.title, item.site_id, item.url, stored)
        rows.append(
            ClassificationRow(
                title=item.title,
                url=item.url,
                site_id=item.site_id,
                site_name=item.site_name,
                topic_id=topic_id,
                topic_label=topic_label(topic_id),
                fetched_at=item.fetched_at,
            )
        )
    rows.sort(
        key=lambda row: row.fetched_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return rows


def classification_catalog(q: str = "", site_id: str = "") -> ClassificationCatalog:
    counts = Counter(row.topic_id for row in classify_rows(q=q, site_id=site_id))
    groups = [
        ClassificationGroup(
            id=group.id,
            label=group.label,
            topics=[
                ClassificationTopic(id=topic_id, label=topic_label(topic_id), count=counts.get(topic_id, 0))
                for topic_id in group.topic_ids
            ],
        )
        for group in TOPIC_GROUPS
    ]
    return ClassificationCatalog(
        uncategorized=ClassificationTopic(id=UNCATEGORIZED, label=topic_label(UNCATEGORIZED), count=counts.get(UNCATEGORIZED, 0)),
        groups=groups,
    )


def query_classifications(
    *,
    topic: str = UNCATEGORIZED,
    q: str = "",
    site_id: str = "",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> ClassificationPage:
    topic_id = normalize_topic_id(topic)
    rows = [row for row in classify_rows(q=q, site_id=site_id) if row.topic_id == topic_id]
    size = min(max(page_size, 1), MAX_PAGE_SIZE)
    total = len(rows)
    last_page = max(1, (total + size - 1) // size) if total else 1
    page = min(max(page, 1), last_page)
    start = (page - 1) * size
    return ClassificationPage(
        topic_id=topic_id,
        topic_label=topic_label(topic_id),
        total=total,
        page=page,
        page_size=size,
        items=rows[start : start + size],
    )
