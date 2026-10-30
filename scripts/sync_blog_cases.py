#!/usr/bin/env python3
"""네이버 블로그 '인증 사례 ⭐' 카테고리 글 전체를 홈페이지 목록으로 동기화.
RSS는 최근 일부 글만 제공하므로 이전에 수집한 글은 보존한다.
"""
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BLOG_ID = 'con_certification'
OUTPUT = Path('blog_cases.json')
RSS = f'https://rss.blog.naver.com/{BLOG_ID}.xml'


def clean(s):
    return html.unescape(re.sub(r'<[^>]+>', '', s or '')).strip()


def is_category(s):
    return '인증사례' in re.sub(r'[^가-힣a-zA-Z0-9]', '', clean(s))


def post_id(url):
    parsed = urlparse(url)
    if parsed.hostname not in ('blog.naver.com', 'm.blog.naver.com'):
        return None
    parts = parsed.path.strip('/').split('/')
    if len(parts) >= 2 and parts[0].lower() == BLOG_ID and parts[1].isdigit():
        return parts[1]
    q = parse_qs(parsed.query)
    if q.get('blogId', [''])[0].lower() == BLOG_ID:
        n = q.get('logNo', [''])[0]
        return n if n.isdigit() else None
    return None


def main():
    req = urllib.request.Request(RSS, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        root = ET.fromstring(response.read())
    found = {}
    for item in root.findall('./channel/item'):
        if not any(is_category(''.join(c.itertext())) for c in item.findall('category')):
            continue
        title, url = clean(item.findtext('title')), clean(item.findtext('link'))
        key = post_id(url)
        if not key or not title:
            continue
        try:
            date = parsedate_to_datetime(clean(item.findtext('pubDate'))).astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError):
            continue
        found[key] = {'title': title, 'url': f'https://blog.naver.com/{BLOG_ID}/{key}', 'date': date}
    if not found:
        raise RuntimeError('RSS 인증 사례 카테고리 0건: 기존 파일을 변경하지 않습니다.')
    # RSS에서 사라진 예전 인증 사례도 기존에 수집된 것은 보존합니다.
    old_count = 0
    if OUTPUT.exists():
        old = json.loads(OUTPUT.read_text(encoding='utf-8'))
        if isinstance(old, list):
            for entry in old:
                if not isinstance(entry, dict):
                    continue
                key = post_id(str(entry.get('url', '')))
                if key and key not in found and all(entry.get(k) for k in ('title', 'date')):
                    found[key] = {k: entry[k] for k in ('title', 'url', 'date')}
                    old_count += 1
    result = sorted(found.values(), key=lambda x: x['date'], reverse=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'RSS 인증 사례 {len(found)-old_count}건 / 기존 보존 {old_count}건 / 총 {len(result)}건 저장', flush=True)
    print('참고: RSS는 최신 글 일부만 제공하며, 이전에 수집되지 않은 오래된 글은 자동 복원되지 않습니다.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('오류:', exc, file=sys.stderr, flush=True)
        sys.exit(1)
