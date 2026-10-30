#!/usr/bin/env python3
"""네이버 RSS의 인증 완료 글 중 인증서 사진이 OCR로 확인된 글만 자동 공개.

주의: 자동 판별은 보수적이며 일부 실제 인증서를 놓칠 수 있음.
기존 approved_certificate_posts.json의 수동 승인은 계속 인정.
"""
import html
import io
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from PIL import Image, ImageEnhance, ImageOps
import pytesseract

BLOG_ID = 'con_certification'
RSS_URL = f'https://rss.blog.naver.com/{BLOG_ID}.xml'
OUTPUT = Path('blog_cases.json')
CANDIDATES = Path('certificate_candidates.json')
APPROVALS = Path('approved_certificate_posts.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'}
NEGATIVE = re.compile(r'부적합|불합격|실패|초과|개선|디버깅|시험\s*(?:데이터|결과|진행|방법|과정)|방사\s*시험|내성\s*시험|측정\s*(?:결과|그래프)|안내|절차|방법|비용|견적|주의사항|가이드|예정|진행\s*중', re.I)
POSITIVE = re.compile(r'인증\s*(?:완료|획득|취득|성공|사례)|적합\s*(?:등록|인증)\s*(?:완료|필증)|인증서|등록필증|certificate\s*(?:issued|granted)', re.I)
# 문서 상단/본문의 등록증 명칭과 KC 로고/영문 등록증 표제를 함께 확인.
DOC_WORDS = re.compile(r'적합등록|적합인증|방송통신기자재|등록필증|인증서|certificate\s+of\s+(?:conformity|registration)|registration\s+of\s+(?:broadcasting|broadcast|radio|electromagnetic)|conformity\s+assessment', re.I)
DOC_ENGLISH = re.compile(r'registration|certificate|conformity|broadcasting|electromagnetic', re.I)


def clean(value):
    return html.unescape(re.sub(r'<[^>]+>', '', value or '')).strip()


def normalized(value):
    return ''.join(re.findall(r'[가-힣a-zA-Z0-9]+', clean(value))).casefold()


def post_key(url):
    parsed = urlparse(url)
    if parsed.hostname not in ('blog.naver.com', 'm.blog.naver.com'):
        return None
    parts = [p for p in parsed.path.split('/') if p]
    if len(parts) >= 2 and parts[0].lower() == BLOG_ID.lower() and parts[1].isdigit():
        return parts[1]
    qs = parse_qs(parsed.query)
    if qs.get('blogId', [''])[0].lower() == BLOG_ID.lower():
        n = qs.get('logNo', [''])[0]
        return n if n.isdigit() else None
    return None


def get(url, limit=8_000_000):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=18) as r:
        if r.headers.get('Content-Length') and int(r.headers['Content-Length']) > limit:
            raise ValueError('이미지 크기 제한 초과')
        data = r.read(limit + 1)
        if len(data) > limit:
            raise ValueError('이미지 크기 제한 초과')
        return data


def image_urls(fragment):
    fragment = html.unescape(fragment or '')
    urls = re.findall(r'<img\b[^>]*?\b(?:data-src|data-lazy-src|src)\s*=\s*["\']([^"\']+)', fragment, re.I)
    urls += re.findall(r'<meta\b[^>]*?content=["\'](https?://[^"\']+)["\'][^>]*>', fragment, re.I)
    result = []
    for u in urls:
        u = html.unescape(u).replace('&amp;', '&')
        if u.startswith('//'):
            u = 'https:' + u
        if u.startswith('http') and u not in result:
            result.append(u)
    return result


def fetch_post_images(key):
    # RSS에 이미지가 빠져 있을 때 모바일 본문을 보조적으로 검사.
    for url in [f'https://m.blog.naver.com/{BLOG_ID}/{key}', f'https://blog.naver.com/PostView.naver?blogId={BLOG_ID}&logNo={key}']:
        try:
            page = get(url, 2_000_000).decode('utf-8', 'ignore')
            images = image_urls(page)
            if images:
                return images
        except Exception as exc:
            print(f'본문 이미지 조회 실패 {key}: {exc}', flush=True)
    return []


def is_certificate_image(url):
    try:
        data = get(url)
        im = Image.open(io.BytesIO(data)).convert('RGB')
        w, h = im.size
        if w < 250 or h < 250:
            return False
        # 증서는 세로형 문서가 일반적. 매우 넓은 배너와 가로 그래프 제외.
        if w / h > 1.45:
            return False
        if max(w, h) > 2100:
            im.thumbnail((2100, 2100))
        im = ImageEnhance.Contrast(ImageOps.grayscale(im)).enhance(1.8)
        im = ImageOps.autocontrast(im)
        if im.width < 1100:
            im = im.resize((int(im.width * 1.8), int(im.height * 1.8)))
        # 국문/영문 문서 명칭을 실제 이미지에서 읽어 확인한다.
        content = pytesseract.image_to_string(im, lang='kor+eng', config='--psm 11')
        compact = re.sub(r'\s+', '', content)
        korean = bool(re.search(r'적합등록|적합인증|방송통신기자재|등록필증', compact))
        english = bool(DOC_ENGLISH.search(content) and re.search(r'KC|KCC|R-R-|R-C-|MSIP|NationalRadio', content, re.I))
        return korean or english
    except Exception as exc:
        print(f'이미지 확인 실패: {url[:90]} / {exc}', flush=True)
        return False


def read_approved():
    if not APPROVALS.exists():
        return set()
    raw = json.loads(APPROVALS.read_text(encoding='utf-8'))
    if not isinstance(raw, list):
        raise ValueError('승인 목록은 URL 문자열 배열이어야 합니다.')
    return {post_key(v) for v in raw if isinstance(v, str) and post_key(v)}


def main():
    approved = read_approved()
    root = ET.fromstring(get(RSS_URL, 3_000_000))
    entries = []
    for item in root.findall('./channel/item'):
        categories = [clean(''.join(c.itertext())) for c in item.findall('category')]
        if not any('인증사례' in normalized(c) for c in categories):
            continue
        title, url = clean(item.findtext('title')), clean(item.findtext('link'))
        key = post_key(url)
        if not title or not key:
            continue
        try:
            date = parsedate_to_datetime(clean(item.findtext('pubDate'))).astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError):
            continue
        description = item.findtext('description') or ''
        entries.append({'title': title, 'url': url, 'date': date, '_id': key, '_description': description})
    if not entries:
        raise RuntimeError('RSS에서 인증 사례 카테고리를 찾지 못했습니다. 기존 파일 보존.')
    entries.sort(key=lambda e: e['date'], reverse=True)
    candidates = [e for e in entries if not NEGATIVE.search(e['title']) and POSITIVE.search(e['title'])]
    CANDIDATES.write_text(json.dumps([{'title':e['title'],'url':e['url'],'date':e['date']} for e in candidates], ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    selected = []
    for e in candidates:
        if e['_id'] in approved:
            verified = True
            print('수동 승인:', e['title'], flush=True)
        else:
            urls = image_urls(e['_description'])
            if not urls:
                urls = fetch_post_images(e['_id'])
            verified = False
            for image_url in urls[:12]:
                if is_certificate_image(image_url):
                    verified = True
                    print('이미지 OCR 인증서 확인:', e['title'], flush=True)
                    break
            if not verified:
                print('인증서 미확인, 제외:', e['title'], flush=True)
        if verified:
            selected.append({'title':e['title'],'url':e['url'],'date':e['date']})
    # 접근 차단 등으로 이번 실행에서 이미지를 못 읽으면 기존 공개 사례를 보존.
    old = []
    if OUTPUT.exists():
        try:
            old = json.loads(OUTPUT.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            pass
    ids = {post_key(e['url']) for e in selected}
    for e in old:
        if isinstance(e, dict) and post_key(e.get('url', '')) not in ids and not NEGATIVE.search(e.get('title', '')):
            selected.append(e)
    selected.sort(key=lambda e:e['date'], reverse=True)
    OUTPUT.write_text(json.dumps(selected[:30], ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'인증 사례 {len(entries)}건 / 후보 {len(candidates)}건 / 홈페이지 공개 {len(selected)}건', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('오류:', exc, file=sys.stderr, flush=True)
        sys.exit(1)
