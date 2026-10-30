#!/usr/bin/env python3
"""네이버 블로그 RSS에서 '인증 사례' 카테고리의 인증 완료 후보만 동기화.

'인증 사례 ⭐', NBSP 등 카테고리 표기 차이를 허용한다.
주의: 인증서 이미지의 진위/존재를 직접 확인하지 않는다.
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
OUT = Path('blog_cases.json')
RSS_URL = f'https://rss.blog.naver.com/{BLOG_ID}.xml'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; ConCertificationCaseSync/2.0)'}

# 인증 완료를 나타내는 명확한 제목만 후보로 채택한다.
POSITIVE = re.compile(
    r'(인증\s*(?:완료|획득|취득|성공|사례)|'
    r'적합\s*(?:등록|인증)\s*(?:완료|필증)|'
    r'인증서|등록필증|certificate\s*(?:issued|granted)|'
    r'certification\s*(?:completed|approved))', re.I)
NEGATIVE = re.compile(
    r'(부적합|불합격|실패|초과|개선|디버깅|'
    r'시험\s*(?:데이터|결과|진행|방법|과정)|'
    r'방사\s*시험|내성\s*시험|측정\s*(?:결과|그래프)|'
    r'안내|절차|방법|비용|견적|필요한가|해야\s*하나|'
    r'알아보기|주의사항|가이드|예정|진행\s*중|신청)', re.I)


def clean(value):
    return html.unescape(re.sub(r'<[^>]+>', '', value or '')).strip()


def normalized(value):
    # NBSP/일반 공백/별표/이모지 등이 섞여도 '인증사례'를 인식한다.
    return ''.join(re.findall(r'[가-힣a-zA-Z0-9]+', clean(value))).casefold()


def main():
    req = urllib.request.Request(RSS_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as response:
        root = ET.fromstring(response.read())

    items = root.findall('./channel/item')
    print(f'RSS 전체 {len(items)}건', flush=True)
    matches = []
    category_names = set()
    for item in items:
        cats = [clean(''.join(cat.itertext())) for cat in item.findall('category')]
        category_names.update(cats)
        if not any('인증사례' in normalized(cat) for cat in cats):
            continue
        title = clean(item.findtext('title'))
        url = clean(item.findtext('link'))
        pub_date = clean(item.findtext('pubDate'))
        if not title or not url.startswith(('https://blog.naver.com/', 'https://m.blog.naver.com/')):
            continue
        try:
            date = parsedate_to_datetime(pub_date).astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError):
            continue
        matches.append({'title': title, 'url': url, 'date': date})

    print(f'RSS 카테고리: {sorted(category_names)}', flush=True)
    print(f'인증 사례 카테고리 {len(matches)}건 발견', flush=True)
    if not matches:
        raise RuntimeError('RSS에서 인증 사례 카테고리를 찾지 못했습니다. 기존 JSON은 보존합니다.')

    approved = []
    for entry in matches:
        title = entry['title']
        if NEGATIVE.search(title):
            print(f'제외(시험/부적합 등): {title}', flush=True)
        elif not POSITIVE.search(title):
            print(f'제외(완료 확인 불가): {title}', flush=True)
        else:
            approved.append(entry)
            print(f'인증 완료 후보: {title}', flush=True)

    if not approved:
        raise RuntimeError('제목에서 인증 완료를 확인할 수 있는 사례가 없습니다. 기존 JSON은 보존합니다.')
    approved.sort(key=lambda entry: entry['date'], reverse=True)
    OUT.write_text(json.dumps(approved[:30], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'완료 후보 {len(approved)}건 저장 (인증서 이미지 자체는 검증하지 않음)', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'오류: {exc}', file=sys.stderr, flush=True)
        sys.exit(1)
