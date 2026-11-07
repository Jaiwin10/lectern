"""Research step: collect real web pages, books and YouTube videos.

Providers, best first:
  web    -> Tavily (TAVILY_API_KEY), else MDN Web Docs + Wikipedia (no key)
  books  -> Google Books (GOOGLE_API_KEY), else Open Library (no key)
  videos -> YouTube Data API (YOUTUBE_API_KEY), else Tavily limited to youtube.com,
            else the public YouTube results page.
            Every video is then confirmed to exist through YouTube oEmbed.

Search queries are built from the title and objective without an LLM call, so
the step uses no LLM quota and gives the same result for the same input.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

from .config import settings
from .sources import domain_of, rate

# Wikimedia rejects requests that advertise br/zstd encoding, which httpx does by default.
UA = {"User-Agent": "LecternLessonTool/1.0 (local educational research tool)", "Accept-Encoding": "gzip"}
STOPWORDS = set(
    """a an and are as at be between by can define describe difference differentiate distinguish do does
    explain for from how identify in into is it its learn learners list of on or outline student students
    that the their them these this to understand use using what when which why will with your you""".split()
)
MAX_WEB = 8
SOURCE_CHARS = 3000


class ResearchError(RuntimeError):
    pass


def keywords(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9+#.\-]*", text.lower())
    out: list[str] = []
    for w in words:
        w = w.strip(".-")
        if len(w) > 2 or re.fullmatch(r"\d\w*", w):
            if w not in STOPWORDS and w not in out:
                out.append(w)
    return out


def build_queries(title: str, objective: str) -> list[str]:
    objective_terms = " ".join(keywords(objective)[:10])
    queries = [title, f"{title} {objective_terms}".strip(), f"{title} explained with examples"]
    return list(dict.fromkeys(q for q in queries if q))


def _get(url: str, **kwargs: Any) -> httpx.Response:
    headers = {**UA, **kwargs.pop("headers", {})}
    return httpx.get(url, headers=headers, timeout=kwargs.pop("timeout", 25), follow_redirects=True, **kwargs)


# ---------------------------------------------------------------- web pages

def _tavily(query: str, include_domains: list[str] | None = None, max_results: int = 6) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "chunks_per_source": 3,
        "include_answer": False,
    }
    if include_domains:
        payload["include_domains"] = include_domains
    resp = httpx.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
        json=payload,
        timeout=40,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def _web_tavily(queries: list[str]) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for q in queries:
        for r in _tavily(q):
            url = r.get("url", "")
            if not url or url in found or "youtube.com" in url:
                continue
            found[url] = {
                "title": r.get("title") or url,
                "url": url,
                "content": (r.get("content") or "").strip(),
                "score": float(r.get("score") or 0),
                "query": q,
                "provider": "Tavily",
            }
    return list(found.values())


def select_relevant(text: str, terms: list[str], limit: int = SOURCE_CHARS) -> str:
    """Keep the paragraphs that mention the lesson's terms, in their original order."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?==)", text) if len(p.strip()) > 40]
    if sum(len(p) for p in paragraphs) <= limit:
        return "\n\n".join(paragraphs)
    scored = sorted(
        range(len(paragraphs)),
        key=lambda i: (-sum(1 for t in terms if re.search(rf"\b{re.escape(t)}", paragraphs[i].lower())), i),
    )
    keep, size = set(), 0
    for i in [0] + scored:  # the lead paragraph gives context, so keep it
        if i in keep or size + len(paragraphs[i]) > limit:
            continue
        keep.add(i)
        size += len(paragraphs[i])
    return "\n\n".join(paragraphs[i] for i in sorted(keep))


def _topic_queries(title: str, objective: str) -> list[str]:
    """Short queries such as 'http post' work better on site search than full sentences."""
    title_kw = keywords(title)
    lead = title_kw[0] if title_kw else ""
    extra = [k for k in keywords(objective) if k not in title_kw][:5]
    return [title] + [f"{lead} {k}".strip() for k in extra]


def _word_hits(text: str, terms: list[str]) -> int:
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    stems = {w[:-1] if w.endswith("s") and len(w) > 4 else w for w in words}
    return sum(1 for t in terms if t in words or (t[:-1] if t.endswith("s") and len(t) > 4 else t) in stems)


def _html_text(fragment: str) -> str:
    fragment = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment, flags=re.S)
    fragment = re.sub(r"</(p|li|h\d|pre|tr|dd|dt)>", "\n\n", fragment)
    text = re.sub(r"<[^>]+>", "", fragment)
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " "), ("&amp;", "&")):
        text = text.replace(a, b)
    return re.sub(r"[ \t]+", " ", text).strip()


def _web_mdn(queries: list[str], terms: list[str], title_terms: list[str]) -> list[dict[str, Any]]:
    hits: dict[str, dict[str, Any]] = {}
    for q in queries[:6]:
        resp = _get("https://developer.mozilla.org/api/v1/search", params={"q": q, "locale": "en-US", "size": 5})
        resp.raise_for_status()
        for doc in resp.json().get("documents", []):
            if not _word_hits(doc["title"] + " " + doc.get("summary", ""), title_terms):
                continue
            # Words in the page title count double: they say what the page is about.
            score = 2 * _word_hits(doc["title"], terms) + _word_hits(doc.get("summary", ""), terms)
            if doc["mdn_url"] not in hits or hits[doc["mdn_url"]]["hits"] < score:
                hits[doc["mdn_url"]] = {"title": doc["title"], "hits": score}
    if not hits:
        return []
    best = max(h["hits"] for h in hits.values())
    chosen = sorted((u for u, h in hits.items() if h["hits"] >= min(3, best)), key=lambda u: -hits[u]["hits"])[:5]
    out = []
    for path in chosen:
        resp = _get(f"https://developer.mozilla.org{path}/index.json")
        if resp.status_code != 200:
            continue
        doc = resp.json().get("doc", {})
        sections = [_html_text((s.get("value") or {}).get("content") or "") for s in doc.get("body", [])]
        text = select_relevant("\n\n".join(s for s in sections if s), terms)
        if len(text) < 300:
            continue
        out.append({
            "title": f"{doc.get('title', hits[path]['title'])} (MDN Web Docs)",
            "url": f"https://developer.mozilla.org{path}",
            "content": text,
            "score": hits[path]["hits"] / max(len(terms), 1),
            "query": queries[0],
            "provider": "MDN Web Docs",
        })
    return out


def _web_wikipedia(queries: list[str], terms: list[str], title_terms: list[str]) -> list[dict[str, Any]]:
    api = "https://en.wikipedia.org/w/api.php"
    titles: list[str] = []
    errors: list[Exception] = []
    for q in queries[:3]:
        try:
            resp = _get(api, params={"action": "query", "list": "search", "srsearch": q, "srlimit": 4, "format": "json"})
            resp.raise_for_status()
        except httpx.HTTPError as exc:  # one failed query should not sink the rest
            errors.append(exc)
            continue
        time.sleep(0.3)  # stay well inside Wikimedia's rate limits
        for hit in resp.json().get("query", {}).get("search", []):
            if hit["title"] not in titles and _word_hits(hit["title"] + " " + hit.get("snippet", ""), title_terms) > 0:
                titles.append(hit["title"])
    out = []
    for rank, title in enumerate(titles[:6]):
        try:
            resp = _get(
                api,
                params={"action": "query", "prop": "extracts", "explaintext": 1, "titles": title, "format": "json", "redirects": 1},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            errors.append(exc)
            continue
        time.sleep(0.3)
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            text = select_relevant((page.get("extract") or "").strip(), terms)
            if len(text) < 300:
                continue
            out.append({
                "title": f"{page['title']} (Wikipedia)",
                "url": "https://en.wikipedia.org/wiki/" + page["title"].replace(" ", "_"),
                "content": text,
                "score": 1 - rank * 0.1,
                "query": queries[0],
                "provider": "Wikipedia",
            })
    if not out and errors:
        raise errors[0]
    return out


def _rank_web(items: list[dict[str, Any]], terms: list[str]) -> list[dict[str, Any]]:
    """Reliable first, then relevant. Limit pages per domain for variety (looser for the
    single-site fallbacks, where every page shares a domain)."""
    for item in items:
        item.update({k: v for k, v in rate(item["url"]).items()})
        text = (item["title"] + " " + item["content"]).lower()
        item["relevance"] = sum(1 for t in terms if t in text) / max(len(terms), 1)
    items = [i for i in items if i["relevance"] > 0 and len(i["content"]) >= 200]
    items.sort(key=lambda i: (i["rank"], -(i["relevance"] + i["score"])))
    per_domain: dict[str, int] = {}
    chosen = []
    for item in items:
        d = domain_of(item["url"])
        if per_domain.get(d, 0) >= (2 if item["provider"] == "Tavily" else 4):
            continue
        per_domain[d] = per_domain.get(d, 0) + 1
        chosen.append(item)
        if len(chosen) == MAX_WEB:
            break
    return chosen


# ---------------------------------------------------------------- books

def _books_google(query: str) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"q": query, "maxResults": 10, "printType": "books", "langRestrict": "en", "orderBy": "relevance"}
    if settings.google_api_key:
        params["key"] = settings.google_api_key
    resp = _get("https://www.googleapis.com/books/v1/volumes", params=params)
    resp.raise_for_status()
    out = []
    for item in resp.json().get("items", []):
        info = item.get("volumeInfo", {})
        if not info.get("title") or not info.get("authors"):
            continue
        out.append({
            "title": info["title"] + (f": {info['subtitle']}" if info.get("subtitle") else ""),
            "authors": info.get("authors", []),
            "year": (info.get("publishedDate") or "")[:4],
            "publisher": info.get("publisher", ""),
            "url": info.get("infoLink") or info.get("canonicalVolumeLink") or "",
            "description": re.sub(r"<[^>]+>", "", info.get("description") or "")[:1200],
            "provider": "Google Books",
        })
    return out


def _books_openlibrary(query: str) -> list[dict[str, Any]]:
    resp = _get(
        "https://openlibrary.org/search.json",
        params={"q": query, "limit": 10, "fields": "title,author_name,first_publish_year,key,publisher"},
    )
    resp.raise_for_status()
    return [
        {
            "title": d.get("title", ""),
            "authors": d.get("author_name", [])[:3],
            "year": str(d.get("first_publish_year") or ""),
            "publisher": (d.get("publisher") or [""])[0],
            "url": f"https://openlibrary.org{d['key']}",
            "description": "",
            "provider": "Open Library",
        }
        for d in resp.json().get("docs", [])
        if d.get("title") and d.get("author_name")
    ]


def _rank_books(books: list[dict[str, Any]], title_terms: list[str]) -> list[dict[str, Any]]:
    def score(b: dict[str, Any]) -> float:
        return _word_hits(b["title"], title_terms) * 2 + _word_hits(b.get("description", ""), title_terms)

    def relevant(b: dict[str, Any]) -> bool:
        # The main subject word (e.g. "http", "git") must be in the book title.
        return _word_hits(b["title"], title_terms[:1]) > 0 or _word_hits(b["title"], title_terms) >= 2

    ranked = sorted((b for b in books if relevant(b)), key=score, reverse=True)
    seen, out = set(), []
    for b in ranked:
        key = b["title"].lower()[:40]
        if key not in seen:
            seen.add(key)
            out.append(b)
    return out[:4]


# ---------------------------------------------------------------- videos

# Learners here are taught in English, so skip videos labelled as another language.
OTHER_LANGUAGE = re.compile(
    r"\b(tamil|hindi|telugu|malayalam|kannada|bangla|bengali|urdu|marathi|gujarati|punjabi|nepali|"
    r"español|espanol|spanish|português|portugues|french|français|deutsch|german|arabic|indonesia|"
    r"türkçe|turkish|русский|vietnamese|tiếng)\b",
    re.I,
)
NON_LATIN = re.compile(r"[\u0400-\u04ff\u0590-\u06ff\u0900-\u0dff\u0e00-\u0eff\u3040-\u9fff\uac00-\ud7af]")
VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})")


def _iso_duration(value: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _videos_youtube_api(query: str) -> list[dict[str, Any]]:
    key = settings.google_api_key
    resp = _get(
        "https://www.googleapis.com/youtube/v3/search",
        params={"part": "snippet", "q": query, "type": "video", "maxResults": 12, "relevanceLanguage": "en",
                "videoEmbeddable": "true", "safeSearch": "strict", "key": key},
    )
    resp.raise_for_status()
    ids = [i["id"]["videoId"] for i in resp.json().get("items", []) if i.get("id", {}).get("videoId")]
    if not ids:
        return []
    detail = _get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet,contentDetails,statistics", "id": ",".join(ids), "key": key},
    )
    detail.raise_for_status()
    out = []
    for v in detail.json().get("items", []):
        seconds = _iso_duration(v["contentDetails"].get("duration", ""))
        if not 120 <= seconds <= 40 * 60:  # skip shorts and very long streams
            continue
        out.append({
            "video_id": v["id"],
            "title": v["snippet"]["title"],
            "channel": v["snippet"].get("channelTitle", ""),
            "duration_sec": seconds,
            "views": int(v.get("statistics", {}).get("viewCount", 0) or 0),
            "published": v["snippet"].get("publishedAt", "")[:10],
            "provider": "YouTube Data API",
        })
    return out


def _video_ids_tavily(query: str) -> list[str]:
    ids = []
    for r in _tavily(query, include_domains=["youtube.com"], max_results=10):
        m = VIDEO_ID.search(r.get("url", ""))
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def _video_ids_results_page(query: str) -> list[str]:
    resp = _get(
        "https://www.youtube.com/results",
        params={"search_query": query, "hl": "en", "gl": "US"},
        headers={"Accept-Language": "en-US,en;q=0.9", "User-Agent": "Mozilla/5.0"},
    )
    resp.raise_for_status()
    return list(dict.fromkeys(re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', resp.text)))[:15]


def verify_video(video_id: str) -> dict[str, Any] | None:
    """oEmbed answers only for videos that exist and may be embedded."""
    try:
        resp = _get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=12,
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()
    return {"title": data.get("title", ""), "channel": data.get("author_name", "")}


def _collect_videos(title: str, terms: list[str], notes: list[str]) -> list[dict[str, Any]]:
    query = f"{title} tutorial explained"
    candidates: list[dict[str, Any]] = []
    if settings.google_api_key:
        try:
            candidates = _videos_youtube_api(query)
        except httpx.HTTPError as exc:
            notes.append(f"YouTube Data API failed ({exc.__class__.__name__}); used fallback search.")
    if not candidates:
        ids: list[str] = []
        if settings.tavily_api_key:
            try:
                ids = _video_ids_tavily(query)
            except httpx.HTTPError:
                ids = []
        if not ids:
            try:
                ids = _video_ids_results_page(query)
            except httpx.HTTPError as exc:
                notes.append(f"Could not search YouTube ({exc.__class__.__name__}).")
        candidates = [{"video_id": i, "provider": "YouTube search"} for i in ids]

    title_terms = keywords(title)
    scored = []
    for c in candidates[:15]:
        meta = verify_video(c["video_id"])
        if meta is None:
            continue
        c["title"] = c.get("title") or meta["title"]
        c["channel"] = c.get("channel") or meta["channel"]
        if OTHER_LANGUAGE.search(c["title"]) or NON_LATIN.search(c["title"]):
            continue
        text = c["title"].lower()
        title_hits = sum(1 for t in title_terms if t in text)
        all_hits = sum(1 for t in terms if t in text)
        if title_hits == 0:
            continue
        c["relevance"] = title_hits * 2 + all_hits + min(c.get("views", 0), 5_000_000) / 5_000_000
        scored.append(c)
        if len(scored) >= 8:
            break
    scored.sort(key=lambda c: c["relevance"], reverse=True)
    out = []
    for c in scored[:4]:
        out.append({
            "video_id": c["video_id"],
            "title": c["title"],
            "channel": c.get("channel", ""),
            "url": f"https://www.youtube.com/watch?v={c['video_id']}",
            "duration_sec": c.get("duration_sec"),
            "views": c.get("views"),
            "published": c.get("published"),
            "verified": True,
            "provider": c["provider"],
        })
    return out


# ---------------------------------------------------------------- entry point

def run_research(title: str, objective: str) -> dict[str, Any]:
    queries = build_queries(title, objective)
    terms = keywords(title + " " + objective)
    notes: list[str] = []
    providers: dict[str, str] = {}

    raw: list[dict[str, Any]] = []
    if settings.tavily_api_key:
        try:
            raw = _web_tavily(queries)
            providers["web"] = "Tavily"
        except httpx.HTTPError as exc:
            notes.append(f"Tavily search failed ({exc}); fell back to Wikipedia.")
    else:
        notes.append("No TAVILY_API_KEY set, so web research uses MDN Web Docs and Wikipedia only.")
    if not raw:
        topic_queries = _topic_queries(title, objective)
        queries = topic_queries  # record what was actually searched
        used = []
        for name, fn in (("MDN Web Docs", _web_mdn), ("Wikipedia", _web_wikipedia)):
            try:
                found = fn(topic_queries, terms, keywords(title))
            except (httpx.HTTPError, ValueError) as exc:
                notes.append(f"{name} search failed ({exc.__class__.__name__}).")
                continue
            if found:
                raw += found
                used.append(name)
        if not raw and len(notes) and all("failed" in n for n in notes[-2:]):
            raise ResearchError("Web research failed: no search service could be reached. Check your connection and retry.")
        providers["web"] = " + ".join(used)
    web = _rank_web(raw, terms)
    if not web:
        raise ResearchError("No relevant web sources were found. Try a more specific title or objective, then retry.")

    books: list[dict[str, Any]] = []
    title_kw = keywords(title) or [title]
    # Long queries often match nothing in catalogues, so we fall back to shorter ones.
    book_queries = list(dict.fromkeys([" ".join(title_kw), " ".join(title_kw[:2]), title_kw[0]]))
    for name, fn in (("Google Books", _books_google), ("Open Library", _books_openlibrary)):
        for bq in book_queries:
            try:
                books = _rank_books(fn(bq), title_kw)
            except (httpx.HTTPError, ValueError) as exc:
                code = getattr(getattr(exc, "response", None), "status_code", "")
                notes.append(f"{name} search failed{f' (HTTP {code})' if code else ''}.")
                break
            if books:
                break
        if books:
            providers["books"] = name
            break
    if not books:
        notes.append("No closely matching books were found.")

    videos = _collect_videos(title, terms, notes)
    providers["videos"] = videos[0]["provider"] if videos else "none"
    if not videos:
        notes.append("No relevant YouTube videos could be verified.")

    return {
        "queries": queries,
        "web": [
            {
                "id": f"S{i}",
                "kind": "web",
                "title": w["title"],
                "url": w["url"],
                "domain": domain_of(w["url"]),
                "tier": w["tier"],
                "tier_label": w["label"],
                "content": w["content"][:SOURCE_CHARS],
                "provider": w["provider"],
                "query": w.get("query"),
            }
            for i, w in enumerate(web, 1)
        ],
        "books": [{"id": f"B{i}", "kind": "book", **b} for i, b in enumerate(books, 1)],
        "videos": [{"id": f"V{i}", "kind": "video", **v} for i, v in enumerate(videos, 1)],
        "notes": notes,
        "providers": providers,
        "collected_at": time.time(),
    }
