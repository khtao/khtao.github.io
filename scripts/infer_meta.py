#!/usr/bin/env python3
"""从正文推断文章元信息：分类 / 标签 / 摘要 / 标题兜底。

为什么需要它
------------
直接丢一个 .md 或 .html 进来、不写 front-matter 是最常见的情况。若一律归为
「未分类」、标签留空，话题页就完全失效——访客没法按主题浏览，归档也失去意义。

推断必须"综合全文"而不是只看开头：很多文章的开场是"最近很忙，好久没更新"，
真正的主题要到第二段才出现。所以这里做的是全文统计，而非取首段了事。

纯标准库，不引入 jieba / sklearn
--------------------------------
没有分词器可用，改用两条互补的启发式：
  ① **领域词典匹配**：可靠，覆盖常见写作主题，能给出人类可读的分类名。
  ② **中文 n-gram 词频 + 停用词过滤**：兜底，能抓出词典里没有的新词
     （比如"自驾游""雾化玻璃"这类词表覆盖不到的专有说法）。
两者结合后，摘要再按词频挑出信息量最高的那句话。

只在作者没写对应字段时才生效——显式写的永远优先。
"""
from __future__ import annotations

import re
from collections import Counter

# --------------------------------------------------------------------------
# 领域词典：分类名 -> (强特征词, 弱特征词)
# 强词只在该领域高频，权重 3；弱词跨领域常见，权重 1（不足以单独定性）。
# --------------------------------------------------------------------------
TOPICS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    '旅行': (
        ('景点', '景区', '门票', '自驾', '行程', '酒店', '民宿', '游记', '高铁', '机票',
         '入住', '打卡', '路线', '徒步', '露营', '游览', '签证', '行李', '导览', '观景',
         '一日游', '自驾游', '区间车', '索道'),
        ('攻略', '风景', '出行', '假期', '旅游', '旅行', '出发', '目的地', '地方'),
    ),
    '技术': (
        ('代码', '函数', '接口', '部署', '服务器', '数据库', '配置', '安装', '脚本', '依赖',
         '报错', '调试', '版本', '框架', '前端', '后端', '算法', '缓存', '并发', '仓库',
         '分支', '编译', '日志', '参数', '模块', '命令行', '重构', '单元测试', '静态资源'),
        ('API', 'Git', '终端', '程序', '开发', '项目', '文件', '系统', '工具', '数据'),
    ),
    '摄影': (
        ('镜头', '光圈', '快门', '构图', '曝光', '相机', '焦距', '感光度', '白平衡',
         '后期', '调色', '取景', '长焦', '广角', '定焦', 'RAW'),
        ('照片', '拍摄', '光线', '画面', '修图'),
    ),
    '美食': (
        ('菜谱', '食材', '做法', '口味', '餐厅', '烘焙', '调味', '翻炒', '烤箱', '口感',
         '配方', '小吃', '探店', '腌制', '下锅'),
        ('好吃', '味道', '料理', '美食'),
    ),
    '读书': (
        ('书评', '读后感', '作者', '章节', '小说', '阅读', '出版社', '主人公', '叙事',
         '译本', '再版', '读书笔记'),
        ('这本书', '文字', '故事', '读书'),
    ),
    '影视': (
        ('剧情', '导演', '演员', '观影', '剧集', '上映', '主角', '编剧', '配乐', '影评',
         '纪录片'),
        ('电影', '电视剧', '看完', '故事', '画面'),
    ),
    '游戏': (
        ('关卡', '装备', '技能', '副本', '氪金', '抽卡', '手游', '端游', '存档', '属性',
         '打法', '连招', 'BOSS'),
        ('游戏', '玩家', '版本'),
    ),
    '健身': (
        ('训练', '增肌', '减脂', '组数', '拉伸', '深蹲', '卧推', '硬拉', '有氧', '心率',
         '蛋白质', '力量', '肌肉', '跑步', '配速'),
        ('运动', '锻炼', '身体', '体重', '动作'),
    ),
    '理财': (
        ('基金', '股票', '定投', '保险', '收益率', '资产', '复利', '指数', '仓位', '财报',
         '估值', '理财', 'A股', '港股', '美股', '止盈', '止损'),
        ('投资', '风险', '收入'),
    ),
    '职场': (
        ('面试', '简历', '绩效', '汇报', '述职', '跳槽', '涨薪', '试用期', '复盘', '排期',
         'OKR', 'KPI'),
        ('工作', '公司', '同事', '领导', '团队', '管理', 'offer', 'Offer'),
    ),
    '教育': (
        ('课程', '考试', '复习', '知识点', '笔记', '真题', '教材', '上岸', '考研', '保研',
         '四六级', '学习方法', '背诵', '错题'),
        ('学习', '学生', '老师', '学校', '专业'),
    ),
    '数码': (
        ('评测', '续航', '屏幕', '性能', '性价比', '散热', '芯片', '电池', '音质', '手感',
         '开箱', '刷新率'),
        ('手机', '电脑', '设备', '系统'),
    ),
    '生活': (
        ('日记', '日常', '搬家', '收纳', '装修', '家务', '养猫', '养狗', '阳台', '厨房',
         '绿植'),
        ('生活', '周末'),
    ),
}

# 兜底分类名：连一个关键词都提不出来时才用。它仍然是一个可点击的话题，
# 比「未分类」这种死胡同强。
FALLBACK_CATEGORY = '随笔'

# 虚词 / 高频噪音词。n-gram 提取时整词命中或被其包裹的都丢掉。
STOPWORDS = frozenset("""
的 了 是 在 我 有 和 就 不 人 都 一 个 上 也 很 到 说 要 去 你 会 着 没 看 好 自 这 那
我们 你们 他们 可以 因为 所以 但是 然后 这样 那样 什么 怎么 一些 一直 一样 一般 不是
就是 可能 应该 需要 已经 还是 这个 那个 这些 那些 之后 之前 现在 以后 对于 关于 通过
以及 或者 如果 虽然 而且 并且 于是 因此 例如 比如 同时 另外 此外 最后 开始 结束 进行
使用 实现 提供 包含 表示 相关 对应 分别 其中 主要 部分 内容 情况 问题 方式 方法 时候
地方 时间 东西 一下 一点 这里 那里 出来 起来 下来 过去 回来 知道 觉得 感觉 发现 认为
""".split())

_CJK_SEG = re.compile(r'[\u4e00-\u9fff]{2,}')
_SENT_SPLIT = re.compile(r'[。！？!?；;\n]+')
# 扫描上限：超长文章（几 MB）逐字取 n-gram 会拖慢构建，
# 前 3 万字已足够代表主题分布。
_SCAN_LIMIT = 30000


def _count(text: str, word: str) -> int:
    """计数：英文按词边界（避免 Docker 命中 doc），中文按子串。"""
    if re.match(r'^[A-Za-z0-9]', word):
        return len(re.findall(r'(?<![A-Za-z0-9])' + re.escape(word) + r'(?![A-Za-z0-9])',
                              text, re.IGNORECASE))
    return text.count(word)


def _ngrams(text: str) -> Counter:
    """中文 2–4 gram 词频。没有分词器时的兜底手段。"""
    c: Counter = Counter()
    for seg in _CJK_SEG.findall(text[:_SCAN_LIMIT]):
        for n in (2, 3, 4):
            for i in range(len(seg) - n + 1):
                c[seg[i:i + n]] += 1
    return c


# 单字虚词。n-gram 是硬切出来的碎片，像"共跑了四""这一趟"这种首尾都不像词，
# 靠首尾判断拦不住，只能看中间有没有虚词字。
_VIRTUAL_CHARS = frozenset(
    '的了是在和就都也很到要去会着被把从对给使让又还再才更最而或与之其所因但若则'
    '嘛呢吗吧啊呀哦上下中前后里外时分年月日个些这那你我他她它们')


def _is_noise(term: str) -> bool:
    if term in STOPWORDS:
        return True
    # 首尾是虚词的片段基本不成词（如"的时候""我们可"）
    if term[0] in STOPWORDS or term[-1] in STOPWORDS:
        return True
    if any(w in term for w in STOPWORDS if len(w) >= 2):
        return True
    # 硬切出来的碎片只要夹了虚词字，基本不是真词
    return any(c in term for c in _VIRTUAL_CHARS)


def _prune(counter: Counter, topn: int, min_count: int = 2) -> list[tuple[str, int]]:
    """去掉噪音与被更长词包含的短词，按「频次 × 长度」取 top N。

    排序让长词优先，于是遍历时跳过"已选词的子串"，剩下的就是最有信息量的词。
    """
    items = [(w, n) for w, n in counter.items()
             if n >= min_count and not _is_noise(w)]
    # 频次与长度都重要：「自驾」出现 5 次 比「的时」出现 20 次有价值得多
    items.sort(key=lambda x: (-(x[1] * len(x[0])), -len(x[0]), x[0]))
    kept: list[tuple[str, int]] = []
    for w, n in items:
        if any(w in k for k, _ in kept):
            continue          # 已有一个更长的词包含它
        kept.append((w, n))
        if len(kept) >= topn:
            break
    return kept


def _score_topics(title: str, plain: str):
    """对全文做领域打分。标题权重 ×3——它往往是主题最密的那一句。

    返回 (分类名, 得分, 强词命中, 弱词命中)。
    两类分开返回是因为它们用途不同：
      强词有区分度 → 既能定性，也适合做标签和摘要关键词；
      弱词（"文件""项目""系统"）到处都是 → 只用来给分类加分，
      若拿去挑摘要句，会把"这会把项目文件复制到仓库"这种说明句顶上来。
    """
    weighted = (title + ' ') * 3 + plain
    best_name, best_score = '', 0
    strong_hits: list[tuple[str, int]] = []
    weak_hits: list[tuple[str, int]] = []
    for name, (strong, weak) in TOPICS.items():
        score = 0
        for w in strong:
            n = _count(weighted, w)
            if n:
                score += n * 3
                strong_hits.append((w, n))
        for w in weak:
            n = _count(weighted, w)
            if n:
                score += n * 1
                weak_hits.append((w, n))
        if score > best_score:
            best_name, best_score = name, score
    strong_hits.sort(key=lambda x: (-x[1], -len(x[0])))
    weak_hits.sort(key=lambda x: (-x[1], -len(x[0])))
    return best_name, best_score, strong_hits, weak_hits


# 这些是元信息残留而非正文，若漏进候选句会变成很怪的摘要
_META_LEFTover = re.compile(r'(?:category|tags|tag|cover|draft|title|date|summary)\s*[:：]')
# 列表项 / 编号条目：信息密度高但不像摘要
_LIST_ITEM = re.compile(r'^\s*(?:\d+[.)、]|[-*+•·]|第\s*[一二三四五六七八九十\d]+)')


def _naturalness(s: str) -> float:
    """这句话像不像一句正常的叙述？

    纯关键词密度打分有个副作用：表格行和列表项往往堆满了主题词
    （"旺季门票 108 观光车 35 基础合计 ¥143"），得分远高于真正的概括句。
    这里按"中文占比 / 数字密度 / 是否列表项"降权，把摘要拉回自然语句。
    """
    n = len(s)
    if not n:
        return 0.0
    cjk = sum(1 for c in s if '\u4e00' <= c <= '\u9fff')
    digits = sum(1 for c in s if c.isdigit())
    ratio = cjk / n
    if ratio < 0.30:
        return 0.12          # 几乎全是数字与符号 → 表格碎片
    if digits / n > 0.22:
        return 0.30          # 数字过密 → 报价/参数表
    if _LIST_ITEM.match(s):
        return 0.35          # 列表项，不像摘要
    return 1.0


def _best_sentence(plain: str, keywords: list[tuple[str, int]], title: str = '') -> str:
    """挑信息量最高的一句话当摘要——综合全文，而不是默认取首段。

    打分 = 命中词权重之和 ÷ 句长开方（抑制长句垄断）× 位置加成。
    只用强特征词与 n-gram 新词计分：弱词没有区分度，会让摘要退化成
    "这会把项目文件复制到你的新仓库"这类说明句。
    """
    sents = []
    for s in _SENT_SPLIT.split(plain):
        s = s.strip()
        # 太短撑不起摘要；元信息残留和标题本身都不该当选
        if len(s) < 16 or _META_LEFTover.search(s):
            continue
        if title and s.strip() == title.strip():
            continue
        sents.append(s)
    if not sents:
        # 放宽阈值再来一次，否则短文会没有摘要
        sents = [s.strip() for s in _SENT_SPLIT.split(plain) if len(s.strip()) >= 8]
        sents = [s for s in sents if not _META_LEFTover.search(s)]
        if not sents:
            return ''
    kw = dict(keywords)
    best, best_val = sents[0], -1.0
    for i, s in enumerate(sents[:80]):        # 只看前 80 句，足够且省时
        base = sum(w * s.count(k) for k, w in kw.items())
        # 位置加成：首句最占优，之后快速衰减。开场白通常是作者写的最概括的一句。
        pos = 1.0 + 0.8 / (1 + i * 0.6)
        val = base * pos * _naturalness(s) / (len(s) ** 0.5 + 1)
        if val > best_val:
            best, best_val = s, val
    # 关键词一个都没命中（纯抒情短文等），退回首句
    return best if best_val > 0 else sents[0]


def analyze(title: str, plain: str, name: str = '') -> dict:
    """综合标题与正文，给出分类、标签、摘要与标题兜底。

    Args:
        title: 已解析出的标题（可能来自 front-matter / h1 / 文件名，也可能是空）
        plain: 去标签后的纯文本正文
        name:  文件名，用作最后兜底

    Returns:
        {'category', 'tags', 'summary', 'title_hint'}
        调用方应当只对作者没写的字段取用这里的值。
    """
    body = plain or ''
    cat_name, cat_score, strong_hits, weak_hits = _score_topics(title or '', body)
    terms = _prune(_ngrams(body), topn=6) if body else []

    # ---- 分类 ----
    if cat_name and cat_score >= 2:
        category = cat_name
    elif terms:
        # 词典没覆盖这篇文章的主题：用全文最高频的实词当分类名。
        # 它至少是一个真实存在的主题词，而不是"未分类"。
        category = terms[0][0].strip()
    elif title:
        category = title.strip()[:8]
    else:
        category = FALLBACK_CATEGORY

    # ---- 标签：词典命中词优先（可读性好），n-gram 新词补充 ----
    tags: list[str] = []
    seen: set[str] = set()

    def _push(t: str):
        t = t.strip()
        if not t or len(t) > 8 or t.lower() in seen:
            return
        seen.add(t.lower())
        tags.append(t)

    for w, _ in strong_hits[:4]:
        _push(w)
    # n-gram 是硬切的，偶尔不通顺（"共跑了四"）。强词够用时就不拿它凑数，
    # 只在词典覆盖不到这篇文章时才补，且只要 2–3 字（越长越容易切歪）。
    if len(tags) < 3:
        for w, _ in terms:
            if 2 <= len(w) <= 3:
                _push(w)
    if not tags:
        for w, _ in weak_hits[:3]:
            _push(w)
    if not tags:
        _push(category)
    tags = tags[:5]

    # ---- 摘要：全文选句 ----
    kw_for_sent = strong_hits[:12] + terms
    summary = _best_sentence(body, kw_for_sent, title or '')

    # ---- 标题兜底：文件名无意义（纯数字/空）时用首句 ----
    title_hint = ''
    if title and not re.fullmatch(r'[\d\s._-]*', title):
        title_hint = title
    elif summary:
        title_hint = summary[:24]

    return {
        'category': category,
        'tags': tags,
        'summary': summary,
        'title_hint': title_hint,
    }


if __name__ == '__main__':
    # 调试用：看看某一篇会推断出什么。
    # 刻意复用 build_index 的提取函数，保证与真实构建走同一条路径。
    import sys
    from pathlib import Path
    if len(sys.argv) < 2:
        print('用法: python3 scripts/infer_meta.py <文章路径>')
        raise SystemExit(1)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_index  # noqa: E402

    src = Path(sys.argv[1])
    raw = src.read_text(encoding='utf-8-sig')
    if src.suffix.lower() in {'.html', '.htm'}:
        meta, body = ({}, raw)
        picked, picked_sum, plain = build_index.html_pick(raw)
        title = picked or build_index.name_title(src.name)
    else:
        meta, body = build_index.frontmatter(raw)
        picked, picked_sum, plain = build_index.md_pick(body)
        title = meta.get('title') or picked or build_index.name_title(src.name)

    r = analyze(title, plain, src.name)
    print(f"标题  : {title}")
    print(f"分类  : {r['category']}")
    print(f"标签  : {', '.join(r['tags'])}")
    print(f"摘要  : {r['summary'][:140]}")
    print(f"（首段: {picked_sum[:60]}）")
