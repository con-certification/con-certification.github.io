#!/usr/bin/env python3
"""네이버 블로그 RSS의 '인증 사례' 카테고리만 추출."""
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import timezone

RSS_URL = "https://rss.blog.naver.com/con_certification.xml"
TARGET = "인증 사례"
OUTPUT = Path("blog_cases.json")
req = urllib.request.Request(RSS_URL, headers={"User-Agent":"Mozilla/5.0 (compatible; ConCertificationBlogSync/1.0)"})
with urllib.request.urlopen(req, timeout=25) as response:
    data = response.read()
root = ET.fromstring(data)
items = []
for item in root.findall("./channel/item"):
    categories = ["".join(e.itertext()).strip() for e in item.findall("category")]
    # 카테고리 정보가 없는 게시글은 임의로 '인증 사례'라고 판단하지 않음
    if not any(TARGET in c for c in categories):
        continue
    title = (item.findtext("title") or "").strip()
    url = (item.findtext("link") or "").strip()
    pub = (item.findtext("pubDate") or "").strip()
    if not title or not url.startswith(("https://blog.naver.com/","https://m.blog.naver.com/")):
        continue
    try:
        date = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        continue
    items.append({"title":title,"url":url,"date":date})
items.sort(key=lambda x:x["date"],reverse=True)
OUTPUT.write_text(json.dumps(items[:30],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(f"인증 사례 {len(items)}건 발견 / RSS 전체 {len(root.findall('./channel/item'))}건")
