#!/usr/bin/env python3
"""네이버 블로그 '인증 사례' 중 인증서가 확인된 글만 게시합니다.

자동으로 RSS에서 후보를 찾지만, 사진 속 인증서의 존재/진위는 RSS로
확인할 수 없으므로 approved_certificate_posts.json에 승인된 URL만 공개합니다.
후보는 certificate_candidates.json에 기록됩니다.
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
RSS_URL = f'https://rss.blog.naver.com/{BLOG_ID}.xml'
OUTPUT = Path('blog_cases.json')
APPROVALS = Path('approved_certificate_posts.json')
CANDIDATES = Path('certificate_candidates.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; ConCertificationCaseSync/3.0)'}
NEGATIVE = re.compile(r'부적합|불합격|실패|초과|개선|디버깅|시험\s*(?:데이터|결과|진행|방법|과정)|방사\s*시험|내성\s*시험|측정\s*(?:결과|그래프)|안내|절차|방법|비용|견적|주의사항|가이드|예정|진행\s*중', re.I)
POSITIVE = re.compile(r'인증\s*(?:완료|획득|취득|성공|사례)|적합\s*(?:등록|인증)\s*(?:완료|필증)|인증서|등록필증|certificate\s*(?:issued|granted)', re.I)


def clean(value):
    return html.unescape(re.sub(r'<[^>]+>', '', value or '')).strip()


def normalized(value):
    return ''.join(re.findall(r'[가-힣a-zA-Z0-9]+', clean(value))).casefold()


def post_key(url):
    """PC/모바일 URL의 같은 게시글을 동일하게 취급."""
    parsed = urlparse(url)
    if parsed.hostname not in ('blog.naver.com', 'm.blog.naver.com'):
        return None
    parts = [p for p in parsed.path.split('/') if p]
    if len(parts) >= 2 and parts[0].lower() == BLOG_ID.lower() and parts[1].isdigit():
        return parts[1]
    qs = parse_qs(parsed.query)
    if qs.get('blogId', [''])[0].lower() == BLOG_ID.lower():
        log_no = qs.get('logNo', [''])[0]
        if log_no.isdigit():
            return log_no
    return None


def read_approved():
    if not APPROVALS.exists():
        APPROVALS.write_text('[]\n', encoding='utf-8')
        print(f'{APPROVALS} 생성됨: 인증서 확인 후 게시글 URL을 추가해야 공개됩니다.', flush=True)
    raw = json.loads(APPROVALS.read_text(encoding='utf-8'))
    if not isinstance(raw, list):
        raise ValueError('승인 목록은 URL 문자열의 JSON 배열이어야 합니다.')
    result = set()
    for value in raw:
        if not isinstance(value, str) or not post_key(value):
            raise ValueError(f'올바르지 않은 인증서 승인 URL: {value!r}')
        result.add(post_key(value))
    return result


def main():
    approved_ids = read_approved()
    req = urllib.request.Request(RSS_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as response:
        root = ET.fromstring(response.read())
    entries = []
    for item in root.findall('./channel/item'):
        categories = [clean(''.join(c.itertext())) for c in item.findall('category')]
        if not any('인증사례' in normalized(c) for c in categories):
            continue
        title = clean(item.findtext('title'))
        url = clean(item.findtext('link'))
        key = post_key(url)
        if not title or not key:
            continue
        try:
            date = parsedate_to_datetime(clean(item.findtext('pubDate'))).astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError):
            continue
        entries.append({'title': title, 'url': url, 'date': date, '_id': key})

    if not entries:
        raise RuntimeError('RSS에서 인증 사례 카테고리를 찾지 못했습니다. 기존 파일을 보존합니다.')
    entries.sort(key=lambda e: e['date'], reverse=True)
    candidates = [{'title': e['title'], 'url': e['url'], 'date': e['date']} for e in entries if not NEGATIVE.search(e['title']) and POSITIVE.search(e['title'])]
    CANDIDATES.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    selected = [{'title': e['title'], 'url': e['url'], 'date': e['date']} for e in entries if e['_id'] in approved_ids and not NEGATIVE.search(e['title'])]
    print(f'인증 사례 카테고리 {len(entries)}건 / 제목상 완료 후보 {len(candidates)}건 / 인증서 확인 승인 {len(selected)}건', flush=True)
    for entry in selected:
        print(f'게시 승인: {entry["title"]}', flush=True)
    if not approved_ids:
        print('승인 목록이 비어 있습니다. 실제 인증서가 있는 글을 확인하여 approved_certificate_posts.json에 URL을 추가하세요.', flush=True)
        # 이전의 잘못 선별된 글이 홈페이지에 남지 않도록 공개 목록은 비웁니다.
    OUTPUT.write_text(json.dumps(selected[:30], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'오류: {exc}', file=sys.stderr, flush=True)
        sys.exit(1)
