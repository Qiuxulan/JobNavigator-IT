# -*- coding: utf-8 -*-
"""v4 全量资源链接重检（v5 任务第 3 步）。

对 data/gold/learning_resources_v4.json 的全部 URL 重新做可达性检查
（HEAD，403/405 退回 GET），结果写入 linkcheck 缓存
/data/shichaojian/JNIT/raw/courses/_linkcheck/link_status_v5.json
（与 v4 缓存分离，保留历史）。

仅缓存确定性结果（2xx/3xx ok，404/410 dead）；超时/5xx 视为 transient，
记录为 unknown 但不缓存，便于下次重试。
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

PROJECT_ROOT = "/mnt/afs/JobNavigator-IT"
V4 = os.path.join(PROJECT_ROOT, "data/gold/learning_resources_v4.json")
CACHE = "/data/shichaojian/JNIT/raw/courses/_linkcheck/link_status_v5.json"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 25
WORKERS = 8

lock = threading.Lock()


def check(url, cache):
    ok, status = False, None
    try:
        r = requests.head(url, timeout=TIMEOUT, headers={"User-Agent": UA},
                          allow_redirects=True)
        if r.status_code in (403, 405, 400):
            r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA},
                             stream=True)
        status = r.status_code
        ok = 200 <= status < 400
        r.close()
    except requests.RequestException:
        ok, status = False, None
    rec = {"ok": ok, "status": status,
           "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with lock:
        # 只缓存确定性结果；transient 不缓存
        if ok or status in (404, 410):
            cache[url] = rec
        else:
            cache[url + "#transient"] = rec  # 另存观察，不覆盖确定性结论
    return rec


def main():
    data = json.load(open(V4, encoding="utf-8"))
    urls = sorted({r["url"] for r in data["resources"]})
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))
    else:
        cache = {}
    todo = [u for u in urls if u not in cache]
    print(f"total={len(urls)} cached={len(urls) - len(todo)} todo={len(todo)}",
          flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for rec in ex.map(lambda u: check(u, cache), todo):
            done += 1
            if done % 100 == 0:
                with lock:
                    json.dump(cache, open(CACHE, "w", encoding="utf-8"),
                              ensure_ascii=False, indent=1)
                print(f"{done}/{len(todo)} dead_so_far="
                      f"{sum(1 for v in cache.values() if not v['ok'])}",
                      flush=True)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with lock:
        json.dump(cache, open(CACHE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    dead = [u for u, v in cache.items() if not v.get("ok") and not u.endswith("#transient")]
    transient = [u for u in cache if u.endswith("#transient")]
    print(f"DONE total={len(urls)} ok={len(urls) - len(dead)} dead={len(dead)} "
          f"transient={len(transient)}", flush=True)


if __name__ == "__main__":
    main()
