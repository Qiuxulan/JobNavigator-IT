"""国内大厂官网社招岗位采集（实时数据层）。

数据源：34 家国内科技公司官网招聘页公开的岗位列表接口（腾讯/字节跳动/百度/美团/网易/京东
+ 小米/蔚来/小鹏/Momenta/商汤/零一万物/小马智行/库洛/叠纸/美图/轻舟智航/极兔/永辉（飞书招聘托管）
+ 高德/阿里云/饿了么/夸克/钉钉/菜鸟/灵犀互娱/平头哥/盒马/通义/淘天/阿里健康/阿里国际/阿里控股/虎鲸文娱（阿里系子集团）），
无需登录、robots 未禁止。
每天运行一次，得到当天的全量在招快照，并维护“首次出现/最后出现”台账：
    python -m pipelines.cn_jobs.collect                 # 全部来源
    python -m pipelines.cn_jobs.collect --sources tencent,baidu --max-pages 2

输出（目录 data/cn_jobs/，体量小，可直接被后端读取）：
    snapshots/YYYY-MM-DD.jsonl.gz   当天全量 IT 岗位快照
    jobs_ledger.jsonl.gz            所有出现过的岗位 + first_seen / last_seen / active
    company_daily.json              每家公司每天的在招 IT 岗位数、新增数、下架数
    collect_log.jsonl               每次运行的来源级统计
外网需走代理：环境变量 https_proxy（与新闻采集 cron 相同）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import html
import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Callable, Iterable, Iterator

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "cn_jobs"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
SLEEP = 0.4          # 两次请求之间的间隔（秒），控制访问频率
TIMEOUT = 25

COMPANIES = {
    "tencent": ("腾讯", "Tencent"),
    "bytedance": ("字节跳动", "ByteDance"),
    "baidu": ("百度", "Baidu"),
    "meituan": ("美团", "Meituan"),
    "netease": ("网易", "NetEase"),
    "jd": ("京东", "JD.com"),
    # 飞书招聘 ATS 托管的官网（{slug}.jobs.feishu.cn，接口形态与字节 jobs 一致）
    "xiaomi": ("小米", "Xiaomi"),
    "nio": ("蔚来", "NIO"),
    "xpeng": ("小鹏", "XPeng"),
    "momenta": ("Momenta", "Momenta"),
    "sensetime": ("商汤科技", "SenseTime"),
    "01ai": ("零一万物", "01.AI"),
    "ponyai": ("小马智行", "Pony.ai"),
    # 第二批（slug 字典爆破发现，2026-11-10）
    "kurogame": ("库洛游戏", "Kuro Games"),
    "papergames": ("叠纸游戏", "Papergames"),
    "meitu": ("美图", "Meitu"),
    "qcraft": ("轻舟智航", "QCraft"),
    "jtexpress": ("极兔速递", "J&T Express"),
    "yonghui": ("永辉超市", "Yonghui"),
    # 第三批：阿里系子集团招聘门户（同一平台，XSRF-TOKEN cookie + _csrf 参数即可公开访问，2026-11-10 逆向）
    "amap": ("高德", "Amap"),
    "aliyun": ("阿里云", "Alibaba Cloud"),
    "eleme": ("饿了么", "Ele.me"),
    "quark": ("夸克", "Quark"),
    "dingtalk": ("钉钉", "DingTalk"),
    "cainiao": ("菜鸟", "Cainiao"),
    "lingxi": ("灵犀互娱", "Lingxi Games"),
    "thead": ("平头哥", "T-Head"),
    "freshippo": ("盒马", "Freshippo"),
    "tongyi": ("通义", "Tongyi"),
    "taotian": ("淘天集团", "Taotian"),
    "alihealth": ("阿里健康", "AliHealth"),
    "aidc": ("阿里国际", "AIDC"),
    "aliholding": ("阿里控股", "Alibaba Holding"),
    "hujing": ("虎鲸文娱", "Hujing Media"),
    # 第四批（slug 爆破第二轮，2026-11-10）
    "poizon": ("得物", "Poizon"),
    "modelbest": ("面壁智能", "ModelBest"),
    "thundersoft": ("中科创达", "ThunderSoft"),
    "herogames": ("英雄游戏", "Hero Games"),
    "chagee": ("霸王茶姬", "CHAGEE"),
    "secoo": ("寺库", "Secoo"),
    "idreamsky": ("创梦天地", "iDreamSky"),
    "navinfo": ("四维图新", "NavInfo"),
    # 第五批（slug 爆破第三轮，2026-11-18，约 260 词字典探测）
    "holomatic": ("禾多科技", "HoloMatic"),
    "trunk": ("主线科技", "Trunk Tech"),
    "neusoft": ("东软集团", "Neusoft"),
    "boke": ("波克城市", "Boke"),
    "moonton": ("沐瞳", "Moonton"),
    "wumart": ("物美", "Wumart"),
    "duxiaoman": ("度小满", "Du Xiaoman"),
    # 聚合平台（company 字段为真实雇主名）
    "iguopin": ("国聘", "iguopin"),
    "mohrss": ("中国公共招聘网", "mohrss"),
}
ALI_GROUP_HOSTS = {
    "amap": "talent.amap.com", "aliyun": "careers.aliyun.com", "eleme": "talent.ele.me",
    "quark": "talent.quark.cn", "dingtalk": "talent.dingtalk.com", "cainiao": "talent.cainiao.com",
    "lingxi": "talent.lingxigames.com", "thead": "recruitment.t-head.cn",
    "freshippo": "hire.freshippo.com", "tongyi": "careers-tongyi.alibaba.com",
    "taotian": "talent.taotian.com", "alihealth": "careers.alihealth.cn",
    "aidc": "aidc-jobs.alibaba.com", "aliholding": "talent-holding.alibaba.com",
    "hujing": "jobs.hujing-dme.com",
}
# 探测过但暂不可用：飞猪（不同版本门户，不下发 XSRF cookie）、cn-jobs.cainiao.com（403）、
# 橙狮体育（接口返回空）、talent.alibaba.com 主站（只做导航，岗位分散在各子集团站点）
FEISHU_PORTALS = {"xiaomi": "mi", "nio": "nio", "xpeng": "xiaopeng", "momenta": "momenta",
                  "sensetime": "sensetime", "01ai": "01ai", "ponyai": "ponyai",
                  "kurogame": "kurogame", "papergames": "papergames", "meitu": "meitu",
                  "qcraft": "qcraft", "jtexpress": "jtexpress", "yonghui": "yonghui",
                  "poizon": "poizon", "modelbest": "modelbest", "thundersoft": "thundersoft",
                  "herogames": "herogames", "chagee": "chagee", "secoo": "secoo",
                  "idreamsky": "idreamsky", "navinfo": "navinfo",
                  "holomatic": "holomatic", "trunk": "trunk", "neusoft": "neusoft",
                  "boke": "boke", "moonton": "moonton", "wumart": "wumart",
                  "duxiaoman": "duxiaoman"}
# 第四轮爆破命中但为空壳（portal 存在但 0 岗位）：horizon/moonshot/roborock/huolala
# 探测过但暂不可用的来源（2026-11 更新）：快手（列表接口需内部鉴权）、
# 拼多多 careers.pinduoduo.com（403）、B站 jobs.bilibili.com（ajSessionId 登录态）、小红书（无公开接口）、
# 知乎/大疆（Moka ATS 响应体加密）、华为/滴滴/米哈游（未发现公开列表接口）；
# 第三轮字典探测命中但弃用：hypergryph 鹰角（仅 2 条测试岗）、kingnet 恺英（1 条）、liulishuo 流利说（2 条非技术岗）

# ---------------------------------------------------------------- IT 岗位过滤
_IT_TITLE = re.compile(
    r"工程师|开发|研发|算法|架构|测试|运维|SRE|DBA|数据|安全|前端|后端|客户端|服务端|全栈|"
    r"大模型|LLM|AIGC|人工智能|AI|机器学习|深度学习|NLP|CV|推荐|搜索|广告技术|"
    r"Java|Python|Golang|Go|C\+\+|iOS|Android|鸿蒙|HarmonyOS|嵌入式|芯片|驱动|网络|云|"
    r"技术|程序|产品经理|技术美术|引擎|图形|音视频|编译|分布式|存储|数据库|机器人|自动驾驶",
    re.I)
_NON_IT_TITLE = re.compile(
    r"销售|客服|店长|主播|采购|招商|行政|法务|财务|会计|出纳|人力|HRBP|招聘|司机|骑手|仓储|物流|商务|BD|门店|导购|"
    r"编辑|翻译|保洁|厨师|运营|组织发展|渠道|商家|市场|品牌|公关|政府事务|公共事务|律师|审计|税务|投资|"
    r"原画|概念设计|动画|美术|插画|音效|配音|剪辑|摄影|直播|内容审核|培训|讲师|顾问(?!.*技术)|"
    r"(配送|食品|生产|消防|骑行|出行|履约|区域|城市)安全|安全经理")
_STRONG_IT = re.compile(r"工程师|开发|研发|算法|架构|测试|运维|SRE|程序|技术美术|产品经理|数据分析|数据科学|"
                        r"研究员|安全(工程|研究|专家)|渗透|攻防", re.I)
# 硬排除：制造业/建筑业/医教等岗位，标题里常带“工程师”会被 _STRONG_IT 救回，需单独拦截；
# 但带明显软件/IT 语境的（如“大模型数据质量工程师”“激光雷达算法”）仍保留
_HARD_NON_IT = re.compile(
    r"SQE|供应商质量|整车质量|市场质量|来料检验|IQC|IPQC|OQC|PQE|CQE|DQE|质量(工程师|经理|主管|专员)|品质(工程师|经理|主管)|"
    r"车灯|座椅|冲压|焊装|涂装|总装|车身尺寸|尺寸工程|金相|无损检测|"
    r"建筑电气|电气设计|给排水|暖通|土木|结构工程|造价工程师|测绘|地质工程|采矿|选矿|冶炼|"
    r"化工工程师|化学工程|护理|医师|医生|药师|教师|教练|班主任|教务|"
    r"机械(设计|工程师|制造|工艺)|模具|数控|CNC|焊接工程师|钣金|铸造|注塑|"
    r"安全员|保安|保洁|普工|操作工|电工|焊工|钳工|车工|铣工|仓管|理货|搬运|装配工|检修工|巡检员|"
    r"环保工程|工艺工程师|工艺员|"
    r"光(电|学)(传感器|工程师|设计)|激光(技术|工程)|毫米波雷达", re.I)
_SOFT_CONTEXT = re.compile(
    r"软件|开发|研发|算法|数据|大模型|AI|智能|系统|平台|网络|云|信息安全|测试|嵌入|芯片|驱动|仿真|"
    r"自动驾驶|计算机|计算技术|IT|信息化|数字化|程序|代码|前端|后端|客户端|服务端|架构|运维|数据库|agent|产品", re.I)
_IT_CATEGORY = re.compile(r"技术|研发|开发|产品|测试|算法|数据|运维|安全|程序|工程|AI|游戏程序|游戏测试", re.I)


def is_it_job(title: str, category: str) -> bool:
    title = title or ""
    if _HARD_NON_IT.search(title) and not _SOFT_CONTEXT.search(title):
        return False
    if _NON_IT_TITLE.search(title):
        # 带“运营/市场”等字样但本身是研发岗（如“运营平台开发工程师”）仍保留；“安全经理”类一律剔除
        return bool(_STRONG_IT.search(title)) and not re.search(r"安全经理|(配送|食品|生产|骑行|履约)安全", title)
    return bool(_IT_CATEGORY.search(category or "")) or bool(_IT_TITLE.search(title))


# ---------------------------------------------------------------- 通用工具
def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*"})
    return s


def _pick(d: dict, *keys, default=""):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return default


def _ms_to_date(v) -> str:
    try:
        return dt.datetime.fromtimestamp(int(v) / 1000, dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _cn_date(s: str) -> str:
    """'2026年11月10日' / '2026-11-10' / '2026/11/10' -> '2026-11-10'。"""
    m = re.search(r"(\d{4})\D(\d{1,2})\D(\d{1,2})", s or "")
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def _clean(text) -> str:
    text = text if isinstance(text, str) else ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def _city(name: str) -> str:
    return re.sub(r"(市|特别行政区)$", "", (name or "").strip())


_OVERSEAS = re.compile(r"新加坡|伦敦|纽约|洛杉矶|旧金山|圣何塞|山景城|西雅图|东京|首尔|雅加达|迪拜|悉尼|墨尔本|"
                       r"柏林|巴黎|都柏林|阿姆斯特丹|多伦多|吉隆坡|曼谷|胡志明|马尼拉|圣保罗|墨西哥|利雅得|"
                       r"伊斯坦布尔|华沙|苏黎世|海外|美国|英国|日本|韩国|印尼|新西兰|澳大利亚|加拿大|"
                       r"科威特|沙特|阿联酋|阿布扎比|多哈|卡塔尔|巴西|德国|法国|荷兰|西班牙|意大利|泰国|越南|"
                       r"菲律宾|马来西亚|印度|土耳其|波兰|爱尔兰|瑞士|以色列|埃及|尼日利亚|南非|俄罗斯|哈萨克|"
                       r"孟买|班加罗尔|曼彻斯特|慕尼黑|米兰|马德里|里斯本|约翰内斯堡|开罗|拉各斯|波哥大|利马|圣地亚哥|布宜诺斯艾利斯")


def is_domestic(cities: list[str]) -> bool:
    """至少有一个工作城市在中国大陆/港澳台；没有城市信息时保留。"""
    return not cities or any(c and not _OVERSEAS.search(c) for c in cities)


def record(source: str, raw_id, title, category, cities, description, requirement,
           posted_at, url, experience="", education="", department="") -> dict:
    cn, en = COMPANIES[source]
    cities = [_city(c) for c in (cities if isinstance(cities, list) else [cities]) if c]
    return {
        "job_id": f"{source}:{raw_id}",
        "source": source,
        "company": cn,
        "company_en": en,
        "title": _clean(title),
        "category": _clean(category),
        "department": _clean(department),
        "cities": cities,
        "city": cities[0] if cities else "",
        "experience": _clean(experience),
        "education": _clean(education),
        "description": _clean(description),
        "requirement": _clean(requirement),
        "posted_at": posted_at or "",
        "url": url,
    }


# ---------------------------------------------------------------- 各来源
def fetch_tencent(s: requests.Session, max_pages: int) -> Iterator[dict]:
    size, page, total = 100, 1, None
    while total is None or page <= min(max_pages, math.ceil(total / size)):
        r = s.get("https://careers.tencent.com/tencentcareer/api/post/Query",
                  params={"timestamp": int(time.time() * 1000), "pageIndex": page, "pageSize": size,
                          "language": "zh-cn", "area": "cn"}, timeout=TIMEOUT).json()
        data = r.get("Data") or {}
        total = int(data.get("Count") or 0)
        posts = data.get("Posts") or []
        if not posts:
            break
        for p in posts:
            if p.get("CountryName") not in (None, "", "中国"):
                continue
            yield record("tencent", p.get("PostId"), p.get("RecruitPostName"), p.get("CategoryName"),
                         [p.get("LocationName")], p.get("Responsibility"), p.get("Requirement", ""),
                         _cn_date(p.get("LastUpdateTime", "")),
                         p.get("PostURL") or f"https://careers.tencent.com/jobdesc.html?postId={p.get('PostId')}",
                         experience=p.get("RequireWorkYearsName", ""), department=p.get("BGName", ""))
        page += 1
        time.sleep(SLEEP)


def fetch_baidu(s: requests.Session, max_pages: int) -> Iterator[dict]:
    size, page, total = 10, 1, None   # 接口只接受小分页
    while total is None or page <= min(max_pages * 10, math.ceil(total / size)):
        r = s.post("https://talent.baidu.com/httservice/getPostListNew",
                   data={"recruitType": "SOCIAL", "pageSize": size, "curPage": page, "keyWord": ""},
                   headers={"Referer": "https://talent.baidu.com/jobs/social-list"}, timeout=TIMEOUT).json()
        data = r.get("data") or {}
        total = int(data.get("total") or 0)
        rows = data.get("list") or []
        if not rows:
            break
        for p in rows:
            cities = _pick(p, "workPlace", "workPlaceName", "workCity", default="")
            cities = re.split(r"[,，、/]", cities) if isinstance(cities, str) else cities
            yield record("baidu", p.get("jobId") or p.get("postId"), p.get("name"), p.get("postType"), cities,
                         p.get("workContent"), p.get("serviceCondition"),
                         _cn_date(_pick(p, "publishDate", "updateDate")),
                         f"https://talent.baidu.com/jobs/detail/SOCIAL/{p.get('postId')}",
                         experience=p.get("workYears", ""), education=p.get("education", ""),
                         department=p.get("orgName", ""))
        page += 1
        time.sleep(SLEEP)


def fetch_meituan(s: requests.Session, max_pages: int) -> Iterator[dict]:
    size, page, pages = 100, 1, None
    while pages is None or page <= min(max_pages, pages):
        body = {"page": {"pageNo": page, "pageSize": size}, "jobShareType": "1", "keywords": "", "cityList": [],
                "department": [], "jfJgList": [], "jobType": [{"code": "3", "subCode": []}], "typeCode": [], "specialCode": []}
        r = s.post("https://zhaopin.meituan.com/api/official/job/getJobList", json=body,
                   headers={"Referer": "https://zhaopin.meituan.com/web/social"}, timeout=TIMEOUT).json()
        data = r.get("data") or {}
        pages = int((data.get("page") or {}).get("totalPage") or 0)
        rows = data.get("list") or []
        if not rows:
            break
        for p in rows:
            jid = p.get("jobUnionId")
            yield record("meituan", jid, p.get("name"), f"{p.get('jobFamily') or ''}/{p.get('jobFamilyGroup') or ''}",
                         [c.get("name") for c in p.get("cityList") or []], p.get("jobDuty"),
                         _pick(p, "jobRequirement", "requirement", "highLight"),
                         _ms_to_date(_pick(p, "refreshTime", "firstPostTime", "updateTime", default=None)),
                         f"https://zhaopin.meituan.com/web/position/detail?jobUnionId={jid}",
                         experience=p.get("workYear") or "",
                         department="/".join(d.get("name", "") for d in p.get("department") or []))
        page += 1
        time.sleep(SLEEP)


def fetch_netease(s: requests.Session, max_pages: int) -> Iterator[dict]:
    size, page, pages = 100, 1, None
    while pages is None or page <= min(max_pages, pages):
        r = s.post("https://hr.163.com/api/hr163/position/queryPage", json={"currentPage": page, "pageSize": size},
                   headers={"Referer": "https://hr.163.com/job-list.html"}, timeout=TIMEOUT).json()
        data = r.get("data") or {}
        pages = int(data.get("pages") or 0)
        rows = data.get("list") or []
        if not rows:
            break
        for p in rows:
            yield record("netease", p.get("id"), p.get("name"), p.get("firstPostTypeName"),
                         p.get("workPlaceNameList") or [], p.get("description"), p.get("requirement"),
                         _ms_to_date(p.get("updateTime")), f"https://hr.163.com/job-detail.html?id={p.get('id')}",
                         experience=p.get("reqWorkYearsName", ""), education=p.get("reqEducationName", ""),
                         department=_pick(p, "productName", "firstDepName"))
        page += 1
        time.sleep(SLEEP)


def fetch_jd(s: requests.Session, max_pages: int) -> Iterator[dict]:
    size, ref = 100, {"Referer": "https://zhaopin.jd.com/web/job/job_info_list/3"}
    form = {"workCityJson": "[]", "jobTypeJson": "[]", "jobSearch": ""}
    total = int(s.post("https://zhaopin.jd.com/web/job/job_count", data=form, headers=ref, timeout=TIMEOUT).text.strip() or 0)
    for page in range(1, min(max_pages, math.ceil(total / size)) + 1):
        rows = s.post("https://zhaopin.jd.com/web/job/job_list", data={**form, "pageIndex": page, "pageSize": size},
                      headers=ref, timeout=TIMEOUT).json()
        if not rows:
            break
        for p in rows:
            cities = _pick(p, "workCity", "workCityName", default="")
            cities = re.split(r"[,，、/]", cities) if isinstance(cities, str) else cities
            yield record("jd", p.get("positionId") or p.get("id"), _pick(p, "positionNameOpen", "positionName"),
                         p.get("jobType"), cities, p.get("workContent"), p.get("qualification"),
                         p.get("formatPublishTime") or _ms_to_date(p.get("publishTime")),
                         "https://zhaopin.jd.com/web/job/job_info_list/3",
                         department=p.get("positionDeptName", ""))
        time.sleep(SLEEP)


def fetch_bytedance(s: requests.Session, max_pages: int) -> Iterator[dict]:
    h = {"Referer": "https://jobs.bytedance.com/society/position", "Origin": "https://jobs.bytedance.com",
         "portal-channel": "office", "portal-platform": "pc", "website-path": "society",
         "Content-Type": "application/json", "accept-language": "zh-CN"}
    tok = s.post("https://jobs.bytedance.com/api/v1/csrf/token", json={"portal_entrance": 1}, headers=h,
                 timeout=TIMEOUT).json()["data"]["token"]
    s.cookies.set("atsx-csrf-token", tok, domain="jobs.bytedance.com")
    h["x-csrf-token"] = tok
    size, page, total = 100, 0, None
    while total is None or (page < max_pages and page * size < total):
        body = {"keyword": "", "limit": size, "offset": page * size, "job_category_id_list": [], "tag_id_list": [],
                "location_code_list": [], "subject_id_list": [], "recruitment_id_list": [], "portal_type": 2,
                "job_function_id_list": [], "storefront_id_list": [], "portal_entrance": 1}
        data = s.post("https://jobs.bytedance.com/api/v1/search/job/posts", json=body, headers=h,
                      timeout=TIMEOUT).json().get("data") or {}
        total = int(data.get("count") or 0)
        rows = data.get("job_post_list") or []
        if not rows:
            break
        for p in rows:
            city = (p.get("city_info") or {}).get("name", "")
            cities = [c.get("name") for c in p.get("city_list") or [] if c.get("name")] or [city]
            cat = p.get("job_category") or {}
            parent = (cat.get("parent") or {}).get("name", "")
            yield record("bytedance", p.get("id"), p.get("title"), f"{parent}/{cat.get('name', '')}".strip("/"),
                         cities, p.get("description"), p.get("requirement"),
                         _ms_to_date(p.get("publish_time")),
                         f"https://jobs.bytedance.com/experienced/position/{p.get('id')}/detail",
                         department=(p.get("job_subject") or {}).get("name", {}).get("zh_cn", "")
                         if isinstance((p.get("job_subject") or {}).get("name"), dict) else "")
        page += 1
        time.sleep(SLEEP)


def _epoch_to_date(v) -> str:
    """飞书系 publish_time 有的是毫秒有的是秒，自动判断。"""
    try:
        v = int(v)
        if v > 10 ** 12:
            v //= 1000
        return dt.datetime.fromtimestamp(v, dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def fetch_feishu(source: str) -> Callable[[requests.Session, int], Iterator[dict]]:
    slug = FEISHU_PORTALS[source]
    base = f"https://{slug}.jobs.feishu.cn"

    def _fetch(s: requests.Session, max_pages: int) -> Iterator[dict]:
        # 注意：不能带 website-path/portal-channel 等字节站点专用头，否则报 site not exist
        h = {"Content-Type": "application/json", "accept-language": "zh-CN"}
        tok = s.post(f"{base}/api/v1/csrf/token", json={"portal_entrance": 1}, headers=h,
                     timeout=TIMEOUT).json()["data"]["token"]
        s.cookies.set("atsx-csrf-token", tok, domain=f"{slug}.jobs.feishu.cn")
        h["x-csrf-token"] = tok
        size, page, total = 100, 0, None
        while total is None or (page < max_pages and page * size < total):
            body = {"keyword": "", "limit": size, "offset": page * size, "job_category_id_list": [],
                    "tag_id_list": [], "location_code_list": [], "subject_id_list": [],
                    "recruitment_id_list": [], "portal_type": 2, "job_function_id_list": [],
                    "storefront_id_list": [], "portal_entrance": 1}
            data = s.post(f"{base}/api/v1/search/job/posts", json=body, headers=h,
                          timeout=TIMEOUT).json().get("data") or {}
            total = int(data.get("count") or 0)
            rows = data.get("job_post_list") or []
            if not rows:
                break
            for p in rows:
                cities = [c.get("name") for c in p.get("city_list") or [] if c.get("name")]
                if not cities and (p.get("city_info") or {}).get("name"):
                    cities = [p["city_info"]["name"]]
                cat = p.get("job_category") or {}
                parent = (cat.get("parent") or {}).get("name", "")
                subj = (p.get("job_subject") or {}).get("name", "")
                yield record(source, p.get("id"), p.get("title"),
                             f"{parent}/{cat.get('name', '')}".strip("/"), cities,
                             p.get("description"), p.get("requirement"),
                             _epoch_to_date(p.get("publish_time")),
                             f"{base}/experienced/position/{p.get('id')}/detail",
                             department=subj if isinstance(subj, str) else "")
            page += 1
            time.sleep(SLEEP)

    return _fetch


def fetch_ali_group(source: str) -> Callable[[requests.Session, int], Iterator[dict]]:
    """阿里系子集团招聘门户（同一套 new-careers-portal 平台）。

    反爬机制：Spring 标准 XSRF——先 GET 列表页拿 XSRF-TOKEN cookie，
    再以 ?_csrf=<cookie> 调 /position/search 即可，纯 requests 可复现。
    """
    host = ALI_GROUP_HOSTS[source]
    base = f"https://{host}"

    def _fetch(s: requests.Session, max_pages: int) -> Iterator[dict]:
        list_url = f"{base}/off-campus/position-list?lang=zh"
        s.get(list_url, headers={"Referer": base + "/"}, timeout=TIMEOUT)
        token = s.cookies.get("XSRF-TOKEN")
        if not token:
            raise RuntimeError(f"{host} 未下发 XSRF-TOKEN cookie")
        size, page, total = 20, 1, None
        while total is None or page <= min(max_pages, math.ceil(total / size)):
            body = {"channel": "group_official_site", "language": "zh", "batchId": "", "categories": "",
                    "deptCodes": [], "key": "", "pageIndex": page, "pageSize": size, "regions": "",
                    "subCategories": "", "shareType": "", "shareId": "", "myReferralShareCode": ""}
            d = s.post(f"{base}/position/search?_csrf={token}", json=body,
                       headers={"Content-Type": "application/json", "Referer": list_url},
                       timeout=TIMEOUT).json().get("content") or {}
            total = int(d.get("totalCount") or 0)
            rows = d.get("datas") or []
            if not rows:
                break
            for p in rows:
                cities = [str(c) for c in (p.get("workLocations") or []) if c]
                cats = p.get("categories") or []
                cat = "/".join(str(c.get("name", "")) for c in cats if isinstance(c, dict))
                yield record(source, p.get("id"), p.get("name"), cat, cities,
                             _pick(p, "description", "jobDescription"), p.get("requirement"),
                             _ms_to_date(p.get("publishTime")),
                             f"{base}/off-campus/position-detail?positionId={p.get('id')}")
            page += 1
            time.sleep(SLEEP)

    return _fetch


# ---------------------------------------------------------------- 国聘（iguopin）
# 国企/央企/事业单位招聘主平台。公开 JSON 接口 gp-api.iguopin.com/api/jobs/v1/recom-job
# 无需签名、无需登录；字段极全：薪资（月）、学历、经验、工作地点、完整 JD 正文。
# 注意：这是聚合平台，company 用岗位的真实雇主名而非"国聘"。
IGUOPIN_URL = "https://gp-api.iguopin.com/api/jobs/v1/recom-job"
IGUOPIN_KEYWORDS = ["软件", "开发", "算法", "数据", "工程师", "测试", "运维", "网络", "安全",
                    "人工智能", "Java", "Python", "前端", "后端", "大数据", "云计算", "嵌入式",
                    "系统", "信息", "智能", "芯片", "通信", "自动化", "电气", "电子"]


def fetch_iguopin(s: requests.Session, max_pages: int) -> Iterator[dict]:
    seen = set()
    headers = {"Content-Type": "application/json", "Referer": "https://www.iguopin.com/job/list",
               "Origin": "https://www.iguopin.com"}
    for kw in IGUOPIN_KEYWORDS:
        for page in range(1, min(max_pages, 20) + 1):  # 每词最多 400 条
            body = {"search": {"page": page, "page_size": 20, "keyword": kw},
                    "recom": {"update_time": True, "company_nature": True, "hot_job": True}}
            rows = None
            for attempt in range(3):  # 限流码 code!=200 时退避重试
                d = s.post(IGUOPIN_URL, json=body, headers=headers, timeout=TIMEOUT).json()
                if d.get("code") == 200:
                    rows = (d.get("data") or {}).get("list") or []
                    break
                time.sleep(4 + attempt * 3)
            if rows is None:
                print(f"[cn_jobs] iguopin {kw} p{page}: rate-limited, skip rest of keyword", flush=True)
                break
            if not rows:
                break
            new = 0
            for p in rows:
                if p["job_id"] in seen:
                    continue
                seen.add(p["job_id"])
                new += 1
                cities = [d_["area_cn"].split("-")[0] for d_ in p.get("district_list") or [] if d_.get("area_cn")]
                j = record("iguopin", p["job_id"], p["job_name"],
                           f"{p.get('category_cn') or ''}/{p.get('nature_cn') or ''}".strip("/"),
                           cities, p.get("contents"), p.get("contents"),
                           (p.get("start_time") or "")[:10],
                           f"https://www.iguopin.com/job/detail?id={p['job_id']}",
                           experience=p.get("experience_cn", ""), education=p.get("education_cn", ""),
                           department=p.get("department_cn", ""))
                j["company"] = (p.get("company_name") or "").strip() or "国聘平台"
                j["company_en"] = ""
                j["recruitment_type"] = p.get("nature_cn", "")
                if p.get("min_wage") and p.get("max_wage") and not p.get("is_negotiable"):
                    j["salary_min"], j["salary_max"] = p["min_wage"], p["max_wage"]
                    j["salary_note"] = f"{p.get('wage_unit_cn', '元/月')}×{p.get('months', 12)}个月"
                yield j
            if new == 0:  # 整页都是已见岗位，后续页大概率也重复
                break
            time.sleep(SLEEP)


# ---------------------------------------------------------------- 中国公共招聘网（mohrss）
# 人社部官方平台，覆盖全国中小企业/地方企业。服务端渲染列表页内嵌岗位 JSON（HTML 转义），
# 按关键词翻页抓取；字段含月薪上下限、发布日期、原始详情链接。company 用真实雇主名。
MOHRSS_URL = "http://job.mohrss.gov.cn/cjobs/jobinfolist/listJobinfolist"
MOHRSS_CITY_URL = "http://job.mohrss.gov.cn/cjobs/childcity/listChildcity"
MOHRSS_CITYMAP = OUT_DIR / "mohrss_citymap.json"
MOHRSS_KEYWORDS = ["软件", "开发", "算法", "数据", "工程师", "测试", "运维", "网络", "安全",
                   "人工智能", "Java", "Python", "前端", "后端", "大数据", "云计算", "嵌入式"]
_MOHRSS_ITEM_RE = re.compile(r'(\[\{"[^"]+":.*?\}\])', re.S)


def _mohrss_citymap(s: requests.Session) -> dict[int, str]:
    """adcode 前 4 位 -> 城市名；缓存到本地，缺失才请求。"""
    if MOHRSS_CITYMAP.exists():
        try:
            return {int(k): v for k, v in json.loads(MOHRSS_CITYMAP.read_text(encoding="utf-8")).items()}
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    rows = s.post(MOHRSS_CITY_URL, data={"id": ""}, timeout=TIMEOUT).json()
    m = {}
    for x in rows:
        try:
            code, name = int(x["CITYCODE"]), x.get("CITYNAME") or ""
            if name:
                m[code // 100 * 100] = name
        except (KeyError, TypeError, ValueError):
            continue
    try:
        MOHRSS_CITYMAP.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return m


def fetch_mohrss(s: requests.Session, max_pages: int) -> Iterator[dict]:
    citymap = _mohrss_citymap(s)
    seen = set()
    for kw in MOHRSS_KEYWORDS:
        for page in range(1, min(max_pages, 40) + 1):  # 每词最多 800 条
            try:
                r = s.get(MOHRSS_URL, params={"pageNo": page, "orderType": "score", "textfield": kw},
                          timeout=TIMEOUT)
                m = _MOHRSS_ITEM_RE.search(html.unescape(r.text))
                rows = json.loads(m.group(1)) if m else []
            except (ValueError, requests.RequestException) as e:
                print(f"[cn_jobs] mohrss {kw} p{page}: {type(e).__name__}, skip rest of keyword", flush=True)
                break
            if not rows:
                break
            new = 0
            for p in rows:
                jid = p.get("acb200")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                new += 1
                try:
                    code = int(p.get("aab301") or 0)
                except (TypeError, ValueError):
                    code = 0
                prov = code // 10000
                if prov in (11, 12, 31, 50):
                    city = {11: "北京", 12: "天津", 31: "上海", 50: "重庆"}[prov]
                else:
                    # 码表只有 165 个热门城市；查不到时退到区/县名，再退到省
                    city = citymap.get(code // 100 * 100, "") or p.get("aab302") or p.get("area_") or ""
                j = record("mohrss", jid, p.get("aca112"), p.get("aca111_") or "",
                           [city] if city else [], p.get("acb22a"), p.get("acb22a"),
                           (p.get("s_aae397") or "")[:10],
                           html.unescape(p.get("ace760") or "") or "http://job.mohrss.gov.cn/",
                           department=p.get("org_") or "")
                j["company"] = (p.get("aab004") or "").strip() or "中国公共招聘网"
                j["company_en"] = ""
                try:
                    lo, hi = int(p.get("acb241") or 0), int(p.get("acb242") or 0)
                    if 0 < lo <= hi <= 1000000:
                        j["salary_min"], j["salary_max"], j["salary_note"] = lo, hi, "元/月"
                except (TypeError, ValueError):
                    pass
                yield j
            if new == 0:
                break
            time.sleep(SLEEP)


FETCHERS: dict[str, Callable[[requests.Session, int], Iterable[dict]]] = {
    "tencent": fetch_tencent, "bytedance": fetch_bytedance, "baidu": fetch_baidu,
    "meituan": fetch_meituan, "netease": fetch_netease, "jd": fetch_jd,
}
FETCHERS.update({src: fetch_feishu(src) for src in FEISHU_PORTALS})
FETCHERS.update({src: fetch_ali_group(src) for src in ALI_GROUP_HOSTS})
FETCHERS["iguopin"] = fetch_iguopin
FETCHERS["mohrss"] = fetch_mohrss


# ---------------------------------------------------------------- 落盘
def _read_jsonl_gz(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_jsonl_gz(path: Path, rows: Iterable[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)


def update_ledger(today: str, jobs: list[dict], ok_sources: set[str]) -> list[dict]:
    """合并当日快照：新岗位记 first_seen；本次成功采集的来源里消失的岗位标记 active=False。"""
    path = OUT_DIR / "jobs_ledger.jsonl.gz"
    ledger = {r["job_id"]: r for r in _read_jsonl_gz(path)}
    seen = set()
    for j in jobs:
        seen.add(j["job_id"])
        old = ledger.get(j["job_id"])
        ledger[j["job_id"]] = {**j, "first_seen": old["first_seen"] if old else today, "last_seen": today, "active": True}
    for jid, r in ledger.items():
        if r["source"] in ok_sources and jid not in seen and r.get("active"):
            r["active"] = False
    rows = sorted(ledger.values(), key=lambda r: r["job_id"])
    _write_jsonl_gz(path, rows)
    return rows


def update_company_daily(today: str, ledger: list[dict], ok_sources: set[str]) -> dict:
    path = OUT_DIR / "company_daily.json"
    daily = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for src in ok_sources:
        rows = [r for r in ledger if r["source"] == src]
        cn, en = COMPANIES[src]
        entry = daily.setdefault(src, {"company": cn, "company_en": en, "days": {}})
        entry["days"][today] = {
            "open_roles": sum(1 for r in rows if r["active"]),
            "new_roles": sum(1 for r in rows if r["first_seen"] == today),
            "closed_roles": sum(1 for r in rows if not r["active"] and r["last_seen"] != today
                                and r["last_seen"] == max((d for d in entry["days"] if d < today), default="")),
        }
    path.write_text(json.dumps(daily, ensure_ascii=False, indent=1), encoding="utf-8")
    return daily


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", default=",".join(FETCHERS), help="逗号分隔：" + ",".join(FETCHERS))
    ap.add_argument("--max-pages", type=int, default=200, help="每个来源最多翻页数（调试用）")
    ap.add_argument("--keep-non-it", action="store_true", help="不过滤非技术岗位（调试用）")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "snapshots").mkdir(exist_ok=True)
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    jobs, stats, ok = {}, {}, set()
    for name in [x.strip() for x in args.sources.split(",") if x.strip()]:
        t0, n_all, n_it = time.time(), 0, 0
        try:
            for j in FETCHERS[name](_session(), args.max_pages):
                n_all += 1
                if not is_domestic(j["cities"]):
                    continue
                if args.keep_non_it or is_it_job(j["title"], j["category"]):
                    n_it += 1
                    jobs[j["job_id"]] = j
            ok.add(name)
            stats[name] = {"status": "ok", "fetched": n_all, "it_jobs": n_it, "seconds": round(time.time() - t0, 1)}
        except Exception as e:  # 单个来源失败不影响其它来源
            stats[name] = {"status": "failed", "error": f"{type(e).__name__}: {e}"[:300], "fetched": n_all}
        print(f"[cn_jobs] {name}: {stats[name]}", flush=True)

    rows = sorted(jobs.values(), key=lambda r: r["job_id"])
    _write_jsonl_gz(OUT_DIR / "snapshots" / f"{today}.jsonl.gz", rows)
    ledger = update_ledger(today, rows, ok)
    update_company_daily(today, ledger, ok)
    with open(OUT_DIR / "collect_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"date": today, "at": dt.datetime.now().isoformat(timespec="seconds"),
                            "total_it_jobs": len(rows), "sources": stats}, ensure_ascii=False) + "\n")
    print(f"[cn_jobs] done: {len(rows)} IT jobs from {len(ok)}/{len(stats)} sources -> {OUT_DIR}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
