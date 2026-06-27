import os
import json
import re
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

# ── 設定 ──────────────────────────────────────────────
PROJECT = "kohpriv"
PUBLISH_TAG = "公開"          # このタグがついたページだけ公開
OUTPUT_DIR = Path("docs")
# ──────────────────────────────────────────────────────

SID = os.environ.get("COSENSE_SID", "")
HEADERS = {
    "Cookie": f"connect.sid={SID}",
    "User-Agent": "Mozilla/5.0",
}

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode())

def get_all_pages():
    """全ページのリストを取得（100件ずつ）"""
    pages = []
    skip = 0
    while True:
        url = f"https://scrapbox.io/api/pages/{PROJECT}?limit=100&skip={skip}"
        data = fetch(url)
        pages.extend(data["pages"])
        if len(pages) >= data["count"]:
            break
        skip += len(data["pages"])
    return pages

def get_page_detail(title):
    """ページの詳細（本文）を取得"""
    encoded = urllib.parse.quote(title)
    url = f"https://scrapbox.io/api/pages/{PROJECT}/{encoded}"
    return fetch(url)

def has_publish_tag(page):
    """公開タグがあるか確認"""
    links = page.get("links", [])
    tags = page.get("relatedPages", {}).get("links1hop", [])
    # linksかタイトル直下のタグを確認
    all_tags = links + [p.get("title","") for p in tags]
    return PUBLISH_TAG in all_tags or any(
        line.get("text","").strip() == f"#{PUBLISH_TAG}"
        for line in page.get("lines", [])
    )

def cosense_to_html(lines, all_titles):
    """CosenseのテキストをHTMLに変換"""
    html_lines = []
    in_code = False
    code_lang = ""

    for line_obj in lines[1:]:  # 1行目はタイトルなのでスキップ
        text = line_obj.get("text", "")

        # コードブロック
        if text.strip().startswith("code:"):
            in_code = True
            code_lang = text.strip()[5:]
            html_lines.append(f'<pre><code class="language-{code_lang}">')
            continue
        if in_code:
            if text == "" or not text.startswith(" "):
                html_lines.append("</code></pre>")
                in_code = False
            else:
                html_lines.append(text[1:].replace("&","&amp;").replace("<","&lt;"))
                continue

        # インデントレベル
        indent = len(text) - len(text.lstrip())
        text = text.strip()

        if not text:
            html_lines.append('<div class="empty-line"></div>')
            continue

        # 箇条書き（インデントあり）
        if indent > 0:
            text = convert_inline(text, all_titles)
            html_lines.append(f'<li style="margin-left:{indent*1.5}em">{text}</li>')
            continue

        # 見出し（[]で囲まれた太字）
        heading_match = re.match(r'^\[(\*+)\s(.+)\]$', text)
        if heading_match:
            level = min(len(heading_match.group(1)), 3)
            content = convert_inline(heading_match.group(2), all_titles)
            html_lines.append(f'<h{level+1}>{content}</h{level+1}>')
            continue

        # 通常テキスト
        text = convert_inline(text, all_titles)
        html_lines.append(f'<p>{text}</p>')

    if in_code:
        html_lines.append("</code></pre>")

    return "\n".join(html_lines)

def convert_inline(text, all_titles):
    """インライン記法を変換"""
    # 外部リンク [title url]
    text = re.sub(
        r'\[([^\]]+?)\s+(https?://[^\s\]]+)\]',
        r'<a href="\2" target="_blank">\1</a>',
        text
    )
    # 外部リンク [url]
    text = re.sub(
        r'\[(https?://[^\s\]]+)\]',
        r'<a href="\1" target="_blank">\1</a>',
        text
    )
    # 内部リンク [ページ名] → 公開ページならリンク、そうでなければスパン
    def internal_link(m):
        title = m.group(1)
        if title in all_titles:
            slug = urllib.parse.quote(title)
            return f'<a href="{slug}.html" class="internal-link">{title}</a>'
        else:
            return f'<span class="unlinked">{title}</span>'
    text = re.sub(r'\[([^\]]+)\]', internal_link, text)

    # 太字 [[text]] はすでに上で処理済みなので `*text*` 形式のみ
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # タグ #tag
    text = re.sub(r'#(\S+)', r'<a href="tag-\1.html" class="tag">#\1</a>', text)

    return text

def extract_tags(lines):
    """ページからタグを抽出"""
    tags = []
    for line in lines:
        text = line.get("text","").strip()
        for tag in re.findall(r'#(\S+)', text):
            if tag not in tags:
                tags.append(tag)
    return tags

def render_page(title, body_html, tags, related, updated):
    """1ページ分のHTMLを生成"""
    tag_html = " ".join(
        f'<a href="tag-{urllib.parse.quote(t)}.html" class="tag">#{t}</a>'
        for t in tags if t != PUBLISH_TAG
    )
    related_html = ""
    if related:
        links = "\n".join(
            f'<li><a href="{urllib.parse.quote(r)}.html">{r}</a></li>'
            for r in related
        )
        related_html = f'<section class="related"><h3>関連ページ</h3><ul>{links}</ul></section>'

    date_str = datetime.fromtimestamp(updated).strftime("%Y年%m月%d日") if updated else ""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<div class="layout">
  <nav class="sidebar">
    <a href="/index.html" class="home-link">🏠 トップ</a>
    <div id="sidebar-related">{related_html}</div>
  </nav>
  <main class="content">
    <header class="page-header">
      <h1>{title}</h1>
      <div class="meta">
        {f'<span class="date">{date_str}</span>' if date_str else ''}
        <div class="tags">{tag_html}</div>
      </div>
    </header>
    <article>
{body_html}
    </article>
  </main>
</div>
</body>
</html>"""

def render_index(pages_info):
    """トップページ（一覧）を生成"""
    items = ""
    for p in sorted(pages_info, key=lambda x: x["updated"], reverse=True):
        slug = urllib.parse.quote(p["title"])
        date_str = datetime.fromtimestamp(p["updated"]).strftime("%Y.%m.%d") if p["updated"] else ""
        tags = " ".join(
            f'<a href="tag-{urllib.parse.quote(t)}.html" class="tag">#{t}</a>'
            for t in p["tags"] if t != PUBLISH_TAG
        )
        desc = p.get("descriptions", [""])[0] if p.get("descriptions") else ""
        items += f"""
<article class="page-card">
  <div class="page-card-meta">{date_str}</div>
  <h2><a href="{slug}.html">{p["title"]}</a></h2>
  {f'<p class="desc">{desc}</p>' if desc else ''}
  <div class="tags">{tags}</div>
</article>"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>公開ノート</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<div class="index-layout">
  <header class="site-header">
    <h1 class="site-title">公開ノート</h1>
  </header>
  <main class="index-main">
{items}
  </main>
</div>
</body>
</html>"""

def render_tag_page(tag, pages_info):
    """タグページを生成"""
    items = ""
    for p in pages_info:
        slug = urllib.parse.quote(p["title"])
        items += f'<li><a href="{slug}.html">{p["title"]}</a></li>\n'
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>#{tag}</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<div class="index-layout">
  <header class="site-header">
    <a href="/index.html" class="home-link">← トップ</a>
    <h1 class="site-title">#{tag}</h1>
  </header>
  <main class="index-main">
    <ul class="tag-page-list">{items}</ul>
  </main>
</div>
</body>
</html>"""

CSS = """
:root {
  --bg: #fafaf8;
  --surface: #ffffff;
  --border: #e8e4de;
  --text: #2d2a26;
  --text-muted: #8a8480;
  --accent: #5b7fa6;
  --accent-light: #eef2f7;
  --tag-bg: #f0ede8;
  --tag-text: #5a5550;
  --link: #5b7fa6;
  --link-internal: #2d6a4f;
  --radius: 6px;
  --font: 'Hiragino Kaku Gothic ProN', 'Noto Sans JP', sans-serif;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  line-height: 1.8;
  font-size: 16px;
}

/* ── レイアウト ── */
.layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  min-height: 100vh;
  max-width: 1100px;
  margin: 0 auto;
}

.index-layout {
  max-width: 760px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

/* ── サイドバー ── */
.sidebar {
  padding: 2rem 1.25rem;
  border-right: 1px solid var(--border);
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
}

.home-link {
  display: block;
  font-weight: 600;
  color: var(--text);
  text-decoration: none;
  margin-bottom: 1.5rem;
  font-size: 0.95rem;
}

.home-link:hover { color: var(--accent); }

/* ── メインコンテンツ ── */
.content {
  padding: 2.5rem 3rem;
  max-width: 760px;
}

/* ── ページヘッダー ── */
.page-header h1 {
  font-size: 1.75rem;
  font-weight: 700;
  margin-bottom: 0.5rem;
  line-height: 1.4;
}

.meta {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border);
}

.date { color: var(--text-muted); font-size: 0.85rem; }

/* ── 本文 ── */
article p {
  margin-bottom: 1rem;
}

article h2, article h3, article h4 {
  font-weight: 700;
  margin: 1.75rem 0 0.5rem;
  line-height: 1.4;
}

article h2 { font-size: 1.3rem; }
article h3 { font-size: 1.1rem; }

article li {
  margin-bottom: 0.4rem;
  list-style: disc;
}

article pre {
  background: #f4f1ec;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
  overflow-x: auto;
  margin: 1rem 0;
  font-size: 0.88rem;
  line-height: 1.6;
}

article a { color: var(--link); text-decoration: underline; }
article a.internal-link { color: var(--link-internal); }
article a.internal-link:hover { background: #e8f4ee; border-radius: 3px; }
article span.unlinked { color: var(--text-muted); }

.empty-line { height: 0.6rem; }

/* ── タグ ── */
.tags { display: flex; flex-wrap: wrap; gap: 0.4rem; }

.tag {
  display: inline-block;
  background: var(--tag-bg);
  color: var(--tag-text);
  border-radius: 999px;
  padding: 0.15rem 0.7rem;
  font-size: 0.8rem;
  text-decoration: none;
}

.tag:hover { background: var(--accent-light); color: var(--accent); }

/* ── 関連ページ ── */
.related { margin-top: 1.5rem; }
.related h3 {
  font-size: 0.85rem;
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.related ul { list-style: none; }
.related li { margin-bottom: 0.4rem; }
.related a {
  font-size: 0.9rem;
  color: var(--text);
  text-decoration: none;
  display: block;
  padding: 0.2rem 0.4rem;
  border-radius: var(--radius);
}
.related a:hover { background: var(--accent-light); color: var(--accent); }

/* ── トップページ ── */
.site-header {
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border);
}

.site-title {
  font-size: 1.5rem;
  font-weight: 700;
}

.page-card {
  padding: 1.25rem 0;
  border-bottom: 1px solid var(--border);
}

.page-card:last-child { border-bottom: none; }

.page-card-meta {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-bottom: 0.25rem;
}

.page-card h2 {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 0.3rem;
}

.page-card h2 a {
  color: var(--text);
  text-decoration: none;
}

.page-card h2 a:hover { color: var(--accent); }

.page-card .desc {
  font-size: 0.9rem;
  color: var(--text-muted);
  margin-bottom: 0.4rem;
}

.tag-page-list { list-style: none; }
.tag-page-list li { margin-bottom: 0.5rem; }
.tag-page-list a { color: var(--link); }

/* ── レスポンシブ ── */
@media (max-width: 700px) {
  .layout {
    grid-template-columns: 1fr;
  }
  .sidebar {
    position: static;
    height: auto;
    border-right: none;
    border-bottom: 1px solid var(--border);
    padding: 1rem;
  }
  .content { padding: 1.5rem 1rem; }
}
"""

def build():
    print("📥 ページ一覧を取得中...")
    all_pages = get_all_pages()
    print(f"   全 {len(all_pages)} ページ取得")

    OUTPUT_DIR.mkdir(exist_ok=True)

    # CSSを書き出し
    (OUTPUT_DIR / "style.css").write_text(CSS, encoding="utf-8")

    # 公開対象ページを特定
    print(f"🔍 #{PUBLISH_TAG} タグのページを絞り込み中...")
    publish_pages = []
    for p in all_pages:
        detail = get_page_detail(p["title"])
        if has_publish_tag(detail):
            publish_pages.append(detail)
            print(f"   ✓ {p['title']}")

    print(f"\n📝 公開対象: {len(publish_pages)} ページ")

    # 公開ページのタイトル一覧（内部リンク解決用）
    all_titles = {p["title"] for p in publish_pages}

    # タグ→ページ の対応を構築
    tag_map = {}
    pages_info = []
    for page in publish_pages:
        tags = extract_tags(page["lines"])
        pages_info.append({
            "title": page["title"],
            "tags": tags,
            "updated": page.get("updated", 0),
            "descriptions": page.get("descriptions", []),
        })
        for tag in tags:
            tag_map.setdefault(tag, []).append(page["title"])

    # 各ページのHTMLを生成
    for page in publish_pages:
        title = page["title"]
        tags = extract_tags(page["lines"])

        # 関連ページ（リンクしているページのうち公開対象のもの）
        related = [
            l for l in page.get("links", [])
            if l in all_titles and l != title
        ][:8]

        body_html = cosense_to_html(page["lines"], all_titles)
        html = render_page(title, body_html, tags, related, page.get("updated", 0))
        slug = urllib.parse.quote(title)
        (OUTPUT_DIR / f"{slug}.html").write_text(html, encoding="utf-8")

    # タグページを生成
    for tag, titles in tag_map.items():
        if tag == PUBLISH_TAG:
            continue
        tag_pages_info = [p for p in pages_info if p["title"] in titles]
        html = render_tag_page(tag, tag_pages_info)
        slug = urllib.parse.quote(tag)
        (OUTPUT_DIR / f"tag-{slug}.html").write_text(html, encoding="utf-8")

    # トップページを生成
    html = render_index(pages_info)
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")

    print(f"\n✅ 完了！{len(publish_pages)} ページを docs/ に出力しました")

if __name__ == "__main__":
    build()
