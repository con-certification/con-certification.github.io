#!/usr/bin/env python3
"""네이버 블로그 인증 사례 중 '인증 완료/인증서'로 명시된 글만 보수적으로 동기화.

주의: 이미지의 실제 내용은 판독하지 않는다. 인증서 유무의 최종 보증은 불가능하다.
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

BLOG_ID = 'con_certification'
CATEGORY_NAME = '인증 사례'
OUT = Path('blog_cases.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'}

# 보수적인 자동 필터. 제목만으로 인증서 이미지를 100% 확인할 수는 없다.
POSITIVE = re.compile(r'(인증\s*(?:완료|획득|취득|성공|사례)|적합\s*(?:등록|인증)\s*(?:완료|필증)|인증서|등록필증|certificate\s*(?:issued|granted)|certification\s*(?:completed|approved))', re.I)
NEGATIVE = re.compile(r'(부적합|불합격|실패|초과|개선|디버깅|시험\s*(?:데이터|결과|진행|방법|과정)|방사\s*시험|내성\s*시험|측정\s*(?:결과|그래프)|안내|절차|방법|비용|견적|필요한가|해야\s*하나|알아보기|주의사항|가이드|예정|진행\s*중|신청)', re.I)

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode('utf-8', errors='replace')

def clean(s):
    return html.unescape(re.sub(r'<[^>]*>', '', s or '')).strip()

def ids_from_page(page):
    patterns = [
        rf'(?:blogId={BLOG_ID}(?:&amp;|&)logNo=|/{BLOG_ID}/)(\d{{6,}})',
        r'"logNo"\s*:\s*"?(\d{6,})',
        r'logNo\s*[=:]\s*["\']?(\d{6,})',
    ]
    ids = set()
    for p in patterns:
        ids.update(re.findall(p, page, re.I))
    return ids

def category_number(page):
    for m in re.finditer(re.escape(CATEGORY_NAME), page):
        vicinity = page[max(0, m.start()-600):m.end()+600]
        for pat in [r'categoryNo(?:=|%3D|["\']\s*:\s*["\']?)(\d+)', r'categoryNo\\?"?\s*:\s*\\?"?(\d+)']:
            found = re.findall(pat, vicinity, re.I)
            if found:
                return found[-1]
    return None

def main():
    root = ET.fromstring(fetch(f'https://rss.blog.naver.com/{BLOG_ID}.xml'))
    feed = []
    categories = set()
    for item in root.findall('./channel/item'):
        cats = [clean(c.text) for c in item.findall('category')]
        categories.update(cats)
        title = clean(item.findtext('title'))
        url = clean(item.findtext('link'))
        pub = clean(item.findtext('pubDate'))
        match = re.search(r'(?:logNo=|/' + BLOG_ID + r'/)(\d{6,})', url)
        try:
            date = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            continue
        if title and url.startswith(('https://blog.naver.com/', 'https://m.blog.naver.com/')):
            feed.append({'title': title, 'url': url, 'date': date, 'id': match.group(1) if match else None, 'categories': cats})
    print(f'RSS 게시글 {len(feed)}건 / 카테고리 정보: {sorted(categories)[:12]}', flush=True)
    selected = [x for x in feed if any(CATEGORY_NAME in c for c in x['categories'])]
    if not selected:
        category_no = None
        for url in [f'https://m.blog.naver.com/PostList.naver?blogId={BLOG_ID}', f'https://blog.naver.com/PostList.naver?blogId={BLOG_ID}', f'https://m.blog.naver.com/{BLOG_ID}']:
            try:
                category_no = category_number(fetch(url))
                if category_no:
                    break
            except Exception as exc:
                print(f'카테고리 탐색 경고: {exc}', flush=True)
        if not category_no:
            raise RuntimeError('인증 사례 categoryNo 자동 탐색 실패. 카테고리 주소 확인이 필요합니다.')
        print(f'인증 사례 categoryNo={category_no}', flush=True)
        ids = set()
        for page_no in range(1, 6):
            page = fetch(f'https://m.blog.naver.com/PostList.naver?blogId={BLOG_ID}&categoryNo={category_no}&currentPage={page_no}')
            found = ids_from_page(page)
            ids.update(found)
            print(f'카테고리 {page_no}페이지: ID {len(found)}건', flush=True)
            if page_no > 1 and not found:
                break
        selected = [x for x in feed if x['id'] in ids]
    if not selected:
        raise RuntimeError('인증 사례 카테고리 글을 확인하지 못했습니다. 기존 JSON을 보존합니다.')

    included = []
    for x in selected:
        title = x['title']
        if NEGATIVE.search(title) or not POSITIVE.search(title):
            print(f'제외: {title}', flush=True)
            continue
        included.append({'title': title, 'url': x['url'], 'date': x['date']})
        print(f'인증 완료 후보: {title}', flush=True)
    if not included:
        raise RuntimeError('인증 완료로 명시된 글이 없습니다. 기존 JSON을 보존합니다.')
    included.sort(key=lambda x: x['date'], reverse=True)
    OUT.write_text(json.dumps(included[:30], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'인증 완료 후보 {len(included)}건 저장. 실제 인증서 이미지 검증은 수행하지 않았습니다.', flush=True)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'오류: {exc}', file=sys.stderr, flush=True)
        sys.exit(1)
