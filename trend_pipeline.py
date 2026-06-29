"""Transient article extraction and local-AI summarization for new trend items."""

import json
import re
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import certifi
from bs4 import BeautifulSoup


DEFAULT_MODEL = "gemma4:latest"
MIN_ARTICLE_CHARS = 500
MAX_ARTICLE_CHARS = 24000
GOOGLE_NEWS_HOST = "news.google.com"


class TrendPipelineError(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def _request_bytes(url: str, *, data: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> tuple[bytes, str, str]:
    request_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/129 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        **(headers or {}),
    }
    request = urllib.request.Request(url, data=data, headers=request_headers)
    with urllib.request.urlopen(request, context=_ssl_context(), timeout=timeout) as response:
        body = response.read(3_000_000)
        return body, response.geturl(), response.headers.get("Content-Type", "")


def canonicalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit((url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return (url or "").strip()
    tracking_names = {"oc", "gclid", "fbclid", "ref", "referrer"}
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in tracking_names
    ]
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urllib.parse.urlencode(query), ""))


class ArticleURLResolver:
    name = "direct"

    def supports(self, url: str) -> bool:
        return True

    def resolve(self, url: str) -> str:
        return canonicalize_url(url)


class GoogleNewsURLResolver(ArticleURLResolver):
    name = "google_news_batchexecute"

    def supports(self, url: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        return parsed.netloc.lower() == GOOGLE_NEWS_HOST and "/articles/" in parsed.path

    def _base64_token(self, url: str) -> str:
        parts = [part for part in urllib.parse.urlsplit(url).path.split("/") if part]
        if len(parts) < 2 or parts[-2] not in ("articles", "read"):
            raise TrendPipelineError("resolve", "지원하지 않는 Google News URL 형식입니다.")
        return parts[-1]

    def _decoding_params(self, token: str) -> tuple[str, str]:
        body, _, _ = _request_bytes(f"https://news.google.com/rss/articles/{token}")
        soup = BeautifulSoup(body, "html.parser")
        node = soup.select_one("[data-n-a-sg][data-n-a-ts]")
        if not node:
            raise TrendPipelineError("resolve", "Google News 해석용 서명 정보를 찾지 못했습니다.")
        return str(node.get("data-n-a-sg", "")), str(node.get("data-n-a-ts", ""))

    def resolve(self, url: str) -> str:
        try:
            token = self._base64_token(url)
            signature, timestamp = self._decoding_params(token)
            inner_request = [
                "garturlreq",
                [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                token,
                int(timestamp),
                signature,
            ]
            payload = ["Fbv4je", json.dumps(inner_request, separators=(",", ":"))]
            encoded = urllib.parse.urlencode({"f.req": json.dumps([[payload]], separators=(",", ":"))}).encode("utf-8")
            headers = {
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Origin": "https://news.google.com",
                "Referer": "https://news.google.com/",
            }
            body, _, _ = _request_bytes(
                "https://news.google.com/_/DotsSplashUi/data/batchexecute",
                data=encoded,
                headers=headers,
            )
            text = body.decode("utf-8", errors="ignore")
            decoded_url = self._parse_batch_response(text)
            if not decoded_url:
                raise TrendPipelineError("resolve", "Google News 응답에서 원문 URL을 찾지 못했습니다.")
            return canonicalize_url(decoded_url)
        except TrendPipelineError:
            raise
        except Exception as exc:
            raise TrendPipelineError("resolve", f"Google News 원문 URL 해석 실패: {exc}") from exc

    @staticmethod
    def _parse_batch_response(text: str) -> str:
        for chunk in text.split("\n\n"):
            chunk = chunk.strip()
            if not chunk.startswith("["):
                continue
            try:
                rows = json.loads(chunk)
            except Exception:
                continue
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, list) or len(row) < 3 or row[1] != "Fbv4je":
                    continue
                try:
                    inner = json.loads(row[2])
                    if isinstance(inner, list) and len(inner) > 1 and str(inner[1]).startswith("http"):
                        return str(inner[1])
                except Exception:
                    continue
        return ""


RESOLVERS: List[ArticleURLResolver] = [GoogleNewsURLResolver(), ArticleURLResolver()]


def resolve_article_url(url: str) -> Dict[str, Any]:
    for resolver in RESOLVERS:
        if resolver.supports(url):
            resolved = resolver.resolve(url)
            return {
                "source_url": url,
                "resolved_url": resolved,
                "resolver": resolver.name,
            }
    raise TrendPipelineError("resolve", "원문 URL 해석기를 찾지 못했습니다.")


ARTICLE_SELECTORS = (
    '[itemprop="articleBody"]',
    "article",
    ".article-body",
    ".article_body",
    ".article-view-content",
    ".article_view",
    ".article_txt",
    "#articleBody",
    "#article-view-content",
    ".news_body_area",
    ".view_cont",
    ".view-content",
    ".article-content",
    ".article_content",
    ".news-content",
    ".news_content",
    ".news-article-body",
    ".news_article_body",
    ".articleView",
    "#article-view-content-div",
)

ARTICLE_HINTS = ("article", "content", "body", "view", "news", "story")
EXCLUDED_HINTS = (
    "related", "recommend", "ranking", "popular", "footer", "header", "sidebar",
    "comment", "reply", "list", "banner", "advert", "promotion", "most-viewed",
)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _node_identity(node: Any) -> str:
    classes = " ".join(str(value) for value in (node.get("class") or []))
    return f"{node.get('id', '')} {classes}".lower()


def _paragraph_text(node: Any) -> str:
    paragraphs = node.find_all("p")
    return _normalize_text(" ".join(paragraph.get_text(" ", strip=True) for paragraph in paragraphs))


def extract_article_text(url: str) -> Dict[str, Any]:
    try:
        body, final_url, content_type = _request_bytes(url)
    except Exception as exc:
        raise TrendPipelineError("extract", f"원문 페이지 요청 실패: {exc}") from exc
    if "html" not in content_type.lower() and not body.lstrip().startswith(b"<"):
        raise TrendPipelineError("extract", f"HTML 문서가 아닙니다: {content_type or 'unknown'}")
    soup = BeautifulSoup(body, "html.parser")

    candidates: List[tuple[str, str]] = []
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(node.string or "{}")
            objects = data if isinstance(data, list) else [data]
            for obj in objects:
                if isinstance(obj, dict) and obj.get("articleBody"):
                    candidates.append(("jsonld", _normalize_text(str(obj["articleBody"]))))
        except Exception:
            continue
    for node in soup.select("script, style, nav, header, footer, aside, form, noscript"):
        node.decompose()
    for selector in ARTICLE_SELECTORS:
        for node in soup.select(selector):
            candidates.append((selector, _normalize_text(node.get_text(" ", strip=True))))

    # Conservative fallback: only containers whose id/class explicitly looks like
    # article content. Arbitrary long divs often include related-news lists.
    for node in soup.select("main, section, div"):
        identity = _node_identity(node)
        if not identity.strip() or not any(hint in identity for hint in ARTICLE_HINTS):
            continue
        if any(hint in identity for hint in EXCLUDED_HINTS):
            continue
        text = _paragraph_text(node)
        if len(text) >= MIN_ARTICLE_CHARS:
            candidates.append((f"hinted_block:{identity.strip()[:80]}", text))

    candidates = [(method, text) for method, text in candidates if len(text) >= MIN_ARTICLE_CHARS]
    if not candidates:
        raise TrendPipelineError("extract", "기사 본문 후보를 찾지 못했습니다.")
    # Prefer a sufficiently long structured body over a broader enclosing node.
    candidates.sort(key=lambda candidate: (candidate[0] == "jsonld", len(candidate[1])), reverse=True)
    method, text = candidates[0]
    return {
        "resolved_url": canonicalize_url(final_url),
        "body_text": text[:MAX_ARTICLE_CHARS],
        "body_chars": len(text),
        "extractor": method,
        "content_type": content_type,
    }


def _extract_json_object(text: str) -> Dict[str, Any]:
    cleaned = (text or "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise TrendPipelineError("summarize", "Gemma 응답에서 JSON을 찾지 못했습니다.")
    try:
        return json.loads(cleaned[start:end + 1])
    except Exception as exc:
        raise TrendPipelineError("summarize", f"Gemma JSON 해석 실패: {exc}") from exc


def _supported_evidence(points: Any, article_text: str) -> List[str]:
    if not isinstance(points, list):
        return []
    normalized = re.sub(r"[^0-9a-zA-Z가-힣]+", " ", article_text.lower())
    supported = []
    for raw_point in points[:4]:
        point = _normalize_text(str(raw_point or ""))
        tokens = [token for token in re.sub(r"[^0-9a-zA-Z가-힣]+", " ", point.lower()).split() if len(token) >= 2]
        matches = [token for token in tokens if token in normalized]
        if len(matches) >= 2 or any(len(token) >= 7 for token in matches):
            supported.append(point)
    return supported


def summarize_article_with_ollama(
    *,
    title: str,
    source: str,
    keyword: str,
    article_text: str,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 600,
) -> Dict[str, Any]:
    prompt = f"""
다음은 기술·경쟁 동향 모니터링을 위해 수집한 기사 원문입니다.
원문에 직접 적힌 사실만 사용해 한국어로 요약하세요. 추측하거나 원문에 없는 의미를 추가하지 마세요.

키워드: {keyword}
제목: {title}
출처: {source}
원문:
{article_text[:MAX_ARTICLE_CHARS]}

JSON만 반환하세요:
{{
  "title": "원문 의미를 유지한 간결한 한국어 제목",
  "summary": "핵심 사실과 변화가 드러나는 자연스러운 한국어 3~5문장",
  "evidence_points": ["원문에서 직접 확인되는 사실 1", "원문에서 직접 확인되는 사실 2"]
}}
"""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "system": "원문에 있는 사실만 요약하는 한국어 기술 뉴스 편집자입니다. JSON만 반환하세요.",
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = json.load(response)
    except Exception as exc:
        raise TrendPipelineError("summarize", f"Ollama 호출 실패: {exc}") from exc

    result = _extract_json_object(str(raw.get("response", "")))
    summary = _normalize_text(str(result.get("summary", "")))
    evidence = _supported_evidence(result.get("evidence_points", []), article_text)
    if len(summary) < 80:
        raise TrendPipelineError("summarize", "Gemma 요약이 너무 짧거나 비어 있습니다.")
    if not evidence:
        raise TrendPipelineError("summarize", "원문과 대조 가능한 근거 문장을 생성하지 못했습니다.")
    return {
        "title": _normalize_text(str(result.get("title", ""))) or title,
        "summary": summary,
        "source": source,
        "evidence_points": evidence,
        "summary_model": f"ollama:{model}",
        "runtime": {
            "total_duration_ns": int(raw.get("total_duration") or 0),
            "prompt_eval_count": int(raw.get("prompt_eval_count") or 0),
            "eval_count": int(raw.get("eval_count") or 0),
        },
    }


def enrich_and_summarize_trend(article: Dict[str, Any], keyword: str, model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    resolved = resolve_article_url(article.get("link", ""))
    extracted = extract_article_text(resolved["resolved_url"])
    summary = summarize_article_with_ollama(
        title=article.get("title", ""),
        source=article.get("source", "") or "News",
        keyword=keyword,
        article_text=extracted["body_text"],
        model=model,
    )
    return {
        **summary,
        "source_url": article.get("link", ""),
        "original_url": extracted["resolved_url"],
        "resolver": resolved["resolver"],
        "content_status": "summarized",
        "content_chars": extracted["body_chars"],
        "content_extractor": extracted["extractor"],
    }
