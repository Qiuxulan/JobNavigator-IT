"""Google News 跳转链接解码。

news.google.com/rss/articles/CBMi... 是编码链接，新版（2024-07 起）token 内嵌
AU_yqL 前缀的混淆 ID，离线 base64 无法还原原文 URL。这里实现社区已验证的
batchexecute RPC 方案（garturlreq => garturlres）：

1. GET ``/rss/articles/{id}?hl=en-US&gl=US&ceid=US%3Aen`` 取页面内嵌的
   ``data-n-a-sg``（signature）与 ``data-n-a-ts``（timestamp）；
2. POST ``/_/DotsSplashUi/data/batchexecute``，f.req 为三层嵌套的
   ``[[["Fbv4je", <garturlreq json>, null, <req_id>]]]``，可批量。

注意：Google 该端点要求 HTTP/2，httpx 需装 h2（``pip install h2``），否则 POST
返回 400。解码失败一律返回 None，由调用方保留原始跳转链接并标 resolved=False。

参考：googlenewsdecoder 0.2.1（SSubhajitDutta/GoogleNewsDecoder）、
huksley decodeGoogleNewsUrl gist。
"""

from __future__ import annotations

import json
import re
from urllib.parse import quote

import httpx

_GARTURLREQ_CTX = [
    ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
     None, None, None, None, None, 0, 1],
    "X",
    "X",
    1,
    [1, 1, 1],
    1,
    1,
    None,
    0,
    0,
    None,
    0,
]

BATCHEXECUTE_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
RSS_ARTICLE_PAGE = "https://news.google.com/rss/articles/{article_id}?hl=en-US&gl=US&ceid=US%3Aen"

_SIG_RE = re.compile(r'data-n-a-sg="([^"]+)"')
_TS_RE = re.compile(r'data-n-a-ts="([^"]+)"')


class GoogleNewsDecoder:
    """解码 Google News 文章跳转链接。批量接口：先收参数再一次 RPC。"""

    def __init__(self, timeout: float = 20.0):
        # http2=True 是硬性要求：HTTP/1.1 POST batchexecute 会被 Google 拒绝(400)。
        self._client = httpx.Client(
            follow_redirects=True, timeout=timeout, http2=True
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GoogleNewsDecoder":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def fetch_params(self, article_id: str) -> tuple[str, int] | None:
        """取 article_id 的 (signature, timestamp)；失败返回 None。"""
        try:
            resp = self._client.get(RSS_ARTICLE_PAGE.format(article_id=article_id))
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        sig = _SIG_RE.search(resp.text)
        ts = _TS_RE.search(resp.text)
        if not sig or not ts:
            return None
        ts_raw = ts.group(1)
        return sig.group(1), int(ts_raw) if ts_raw.isdigit() else ts_raw

    def decode_batch(self, items: list[tuple[str, str, int]]) -> dict[str, str]:
        """批量解码。items 为 (article_id, signature, timestamp)。

        返回 {article_id: decoded_url}；未解出的 id 不出现在结果里。
        """
        envelopes = []
        for req_id, (article_id, sig, ts) in enumerate(items):
            inner = ["garturlreq", _GARTURLREQ_CTX, article_id, ts, sig]
            envelopes.append(
                ["Fbv4je", json.dumps(inner, separators=(",", ":")), None, str(req_id)]
            )
        # f.req 需要三层嵌套 [[["Fbv4je", ...]]]（少一层会被拒 400）。
        body = "f.req=" + quote(json.dumps([envelopes], separators=(",", ":")))
        try:
            resp = self._client.post(
                BATCHEXECUTE_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                content=body,
            )
        except httpx.HTTPError:
            return {}
        if resp.status_code != 200:
            return {}
        text = resp.text
        if "\n\n" in text:
            text = text.split("\n\n", 1)[1]
        try:
            rows = json.loads(text)
        except json.JSONDecodeError:
            return {}
        out: dict[str, str] = {}
        for row in rows:
            if not (isinstance(row, list) and len(row) >= 3):
                continue
            if row[0] != "wrb.fr" or not isinstance(row[2], str):
                continue
            try:
                payload = json.loads(row[2])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, list) and payload and payload[0] == "garturlres":
                # req_id 在 row 尾部（从后往前取第一个非 None 的单元格）
                req_id = None
                for cell in reversed(row[3:]):
                    if cell is not None:
                        req_id = str(cell)
                        break
                url = payload[1]
                if isinstance(url, str) and url.startswith("http"):
                    if req_id is not None and req_id.isdigit() and int(req_id) < len(items):
                        out[items[int(req_id)][0]] = url
                    else:
                        remaining = [a for a, _, _ in items if a not in out]
                        if len(remaining) == 1:
                            out[remaining[0]] = url
        return out
