import os
import requests
import urllib.parse
from datetime import datetime, timedelta
import re
import xml.etree.ElementTree as ET

# 1. API 키 처리
SERVICE_KEY = os.getenv("G2B_API_KEY", "").strip()
if "%" in SERVICE_KEY:
    SERVICE_KEY = urllib.parse.unquote(SERVICE_KEY)

# 2. 엔지코릭스 선행개발Lab 관심 키워드
CATEGORY_RULES = {
    "선행개발/AI": ["AI", "인공지능", "LLM", "머신러닝", "알고리즘", "지능형", "데이터", "플랫폼"],
    "소부장/공정": ["소부장", "소재", "부품", "장비", "스마트", "공정", "반도체", "센서", "배터리", "이차전지", "제조"],
    "바이오/신소재": ["바이오", "헬스", "의료", "신소재", "화학"],
    "용역입찰": ["용역", "ISP", "구축", "유지보수", "시스템", "소프트웨어", "SW", "개발", "연구", "실증", "기획"]
}

ALL_KEYWORDS = [kw for kws in CATEGORY_RULES.values() for kw in kws]

def classify_category(title):
    for cat, kws in CATEGORY_RULES.items():
        if any(k.lower() in title.lower() for k in kws):
            return cat
    return "용역입찰"

def calculate_dday(close_dt_str):
    try:
        clean_str = re.sub(r'[^0-9]', '', str(close_dt_str))[:8]
        if len(clean_str) == 8:
            close_date = datetime.strptime(clean_str, "%Y%m%d").date()
            today = datetime.now().date()
            diff = (close_date - today).days
            if diff < 0:
                return "마감", "dday-urgent"
            elif diff == 0:
                return "D-Day", "dday-urgent"
            elif diff <= 7:
                return f"D-{diff}", "dday-urgent"
            elif diff <= 14:
                return f"D-{diff}", "dday-normal"
            else:
                return f"D-{diff}", "dday-safe"
    except Exception:
        pass
    return "진행중", "dday-safe"

def fetch_g2b_data():
    today = datetime.today()
    start_date = (today - timedelta(days=30)).strftime("%Y%m%d0000")
    end_date = today.strftime("%Y%m%d2359")
    
    # 조달청 나라장터 최신/구버전 엔드포인트 동시 대응
    urls = [
        "https://apis.data.go.kr/1230000/BidPublicInfoService04/getBidPblancListInfoServcPPSSrch01",
        "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch"
    ]
    
    items = []
    if not SERVICE_KEY:
        return items

    for url in urls:
        try:
            params = {
                "serviceKey": SERVICE_KEY,
                "numOfRows": "100",
                "pageNo": "1",
                "inqryDiv": "1",
                "inqryBgnDt": start_date,
                "inqryEndDt": end_date,
                "type": "json"
            }
            res = requests.get(url, params=params, timeout=10)
            
            # JSON 응답 파싱
            if "application/json" in res.headers.get("Content-Type", "") or res.text.strip().startswith("{"):
                data = res.json()
                raw_items = data.get("response", {}).get("body", {}).get("items", [])
                if isinstance(raw_items, dict):
                    raw_items = raw_items.get("item", [])
                if isinstance(raw_items, dict):
                    raw_items = [raw_items]

                for item in raw_items:
                    bid_name = item.get("bidNtceNm", "")
                    matched = [k for k in ALL_KEYWORDS if k.lower() in bid_name.lower()]
                    if matched:
                        category = classify_category(bid_name)
                        bid_no = item.get("bidNtceNo", "")
                        search_query = urllib.parse.quote(f"나라장터 {bid_no} {bid_name}")
                        portal_url = f"https://search.naver.com/search.naver?query={search_query}"

                        price = item.get("presmptPrce", 0)
                        try:
                            price_val = float(price)
                            if price_val >= 100000000:
                                budget_str = f"{price_val / 100000000:.1f} 억원"
                            elif price_val > 0:
                                budget_str = f"{int(price_val / 10000):,} 만원"
                            else:
                                budget_str = "규격서 참조"
                        except Exception:
                            budget_str = "규격서 참조"

                        close_dt = item.get("bidClseDt", "-")
                        dday_label, dday_class = calculate_dday(close_dt)

                        items.append({
                            "org": item.get("dminsttNm") or item.get("orderInsttNm") or "조달청",
                            "bid_no": bid_no,
                            "category": category,
                            "cat_class": "cat-rd" if "AI" in category or "소부장" in category else "cat-bid",
                            "title": bid_name,
                            "tags": " ".join([f"#{k}" for k in matched[:4]]),
                            "budget": budget_str,
                            "budget_sub": "(추정가격)",
                            "close_date": close_dt,
                            "dday_text": dday_label,
                            "dday_class": dday_class,
                            "url": portal_url
                        })
            
            if items:
                break
        except Exception as e:
            print(f"API 요청 실패 ({url}): {e}")

    return items

def update_html():
    bids = fetch_g2b_data()
    print(f"실제 공고 수집 결과: {len(bids)}건")

    template_file = "engicorix_tender_dashboard.html"
    if not os.path.exists(template_file):
        template_file = "index.html"

    with open(template_file, "r", encoding="utf-8") as f:
        html = f.read()

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    week_str = f"{now.year}년 {now.month}월 {(now.day - 1) // 7 + 1}주차"

    total_cnt = len(bids)
    urgent_cnt = sum(1 for b in bids if "urgent" in b["dday_class"])
    ai_cnt = sum(1 for b in bids if b["category"] in ["선행개발/AI", "소부장/공정"])

    # 상단 숫자 카드 동기화
    html = re.sub(r'class="value text-blue">.*?<span', f'class="value text-blue">{total_cnt} <span', html)
    html = re.sub(r'class="value text-red">.*?<span', f'class="value text-red">{urgent_cnt} <span', html)
    html = re.sub(r'color:var\(--accent-purple\);">(.*?)<span', f'color:var(--accent-purple);">{ai_cnt} <span', html)
    html = re.sub(r'기준 주차:.*?</div>', f'기준 주차:</strong> {week_str}</div>', html)
    html = re.sub(r'최근 동기화:.*?</div>', f'최근 동기화:</strong> {now_str} (매주 자동 갱신)</div>', html)

    # 테이블 행 생성
    if bids:
        rows_html = ""
        for b in bids:
            rows_html += f"""
        <tr data-category="{b['category']}">
          <td>
            <span class="badge-org">{b['org'][:10]}</span>
            <span class="badge-category {b['cat_class']}">{b['category']}</span>
          </td>
          <td class="title-cell">
            <a href="{b['url']}" target="_blank" class="title-link">
              {b['title']}
            </a>
            <div class="tags-list">{b['tags']}</div>
            <div style="font-size:12px; color:#64748b; margin-top:4px;">
              공고번호: <strong style="color:#0f766e;">{b['bid_no']}</strong> 
              <button onclick="copyBidNo('{b['bid_no']}')" style="margin-left:6px; padding:2px 8px; font-size:11px; cursor:pointer; border-radius:4px; border:1px solid #cbd5e1; background:#f8fafc;">번호복사</button>
            </div>
          </td>
          <td><strong>{b['budget']}</strong><br><span style="font-size:12px; color:#64748b;">{b['budget_sub']}</span></td>
          <td>
            <span class="dday-tag {b['dday_class']}">{b['dday_text']}</span>
            <div style="font-size:12px; color:#64748b; margin-top:2px;">{b['close_date']}</div>
          </td>
          <td>
            <a href="{b['url']}" target="_blank" class="btn-action">공고문 열기 ↗</a>
          </td>
        </tr>"""
    else:
        rows_html = """
        <tr>
          <td colspan="5" style="text-align:center; padding:40px; color:#64748b;">
            현재 수집된 신규 관심 공고가 없거나 공공데이터포털 동기화 중입니다.
          </td>
        </tr>"""

    html = re.sub(r'<tbody>.*?</tbody>', f'<tbody>{rows_html}\n      </tbody>', html, flags=re.DOTALL)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("배포 완료!")

if __name__ == "__main__":
    update_html()
