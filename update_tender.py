import os
import requests
import urllib.parse
from datetime import datetime, timedelta
import re

# 1. API 키 처리 (Decoding/Encoding 키 대응)
SERVICE_KEY = os.getenv("G2B_API_KEY", "").strip()
if "%" in SERVICE_KEY:
    SERVICE_KEY = urllib.parse.unquote(SERVICE_KEY)

# 2. 엔지코릭스 관심 키워드
KEYWORDS = ["AI", "인공지능", "플랫폼", "데이터", "스마트", "소부장", "센서", "반도체", "개발", "실증", "연구", "소프트웨어", "시스템"]

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

def fetch_real_bids():
    today = datetime.today()
    start_date = (today - timedelta(days=14)).strftime("%Y%m%d0000")
    end_date = today.strftime("%Y%m%d2359")
    
    url = "https://apis.data.go.kr/1230000/BidPublicInfoService04/getBidPblancListInfoServcPPSSrch01"
    params = {
        "serviceKey": SERVICE_KEY,
        "numOfRows": "100",
        "pageNo": "1",
        "inqryDiv": "1",
        "inqryBgnDt": start_date,
        "inqryEndDt": end_date,
        "type": "json"
    }
    
    items = []
    if not SERVICE_KEY:
        print("경고: G2B_API_KEY가 비어있습니다.")
        return items

    try:
        res = requests.get(url, params=params, timeout=15)
        data = res.json()
        raw_items = data.get("response", {}).get("body", {}).get("items", [])
        
        if isinstance(raw_items, dict):
            raw_items = [raw_items]

        for item in raw_items:
            bid_name = item.get("bidNtceNm", "")
            matched = [k for k in KEYWORDS if k.lower() in bid_name.lower()]
            if matched:
                price = item.get("presmptPrce", 0)
                try:
                    price_val = float(price)
                    if price_val >= 100000000:
                        budget_str = f"{price_val / 100000000:.1f} 억원"
                    elif price_val > 0:
                        budget_str = f"{int(price_val / 10000):,} 만원"
                    else:
                        budget_str = "사업비 규격서 참조"
                except Exception:
                    budget_str = "사업비 규격서 참조"

                close_dt = item.get("bidClseDt", "-")
                dday_label, dday_class = calculate_dday(close_dt)

                items.append({
                    "org": item.get("dminsttNm") or item.get("orderInsttNm") or "조달청",
                    "category": "용역입찰",
                    "cat_class": "cat-bid",
                    "title": bid_name,
                    "tags": " ".join([f"#{k}" for k in matched[:4]]) or "#선행기술",
                    "budget": budget_str,
                    "budget_sub": "(추정가격 기준)",
                    "close_date": close_dt,
                    "dday_text": dday_label,
                    "dday_class": dday_class,
                    "url": item.get("bidNtceDtlUrl") or "https://www.g2b.go.kr"
                })
    except Exception as e:
        print(f"API 요청/파싱 예외 발생 (기본 템플릿 유지 모드로 진행): {e}")
        
    return items

def update_html():
    bids = fetch_real_bids()
    print(f"관심 공고 수집 결과: {len(bids)}건")
    
    # 템플릿 파일 탐색 (둘 중 존재하는 파일 자동 선택)
    template_file = "engicorix_tender_dashboard.html"
    if not os.path.exists(template_file):
        template_file = "index.html"
        
    if not os.path.exists(template_file):
        print(f"에러: {template_file}을 찾을 수 없습니다.")
        return

    with open(template_file, "r", encoding="utf-8") as f:
        html = f.read()

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    week_str = f"{now.year}년 {now.month}월 {(now.day - 1) // 7 + 1}주차"

    if bids:
        total_cnt = len(bids)
        urgent_cnt = sum(1 for b in bids if "urgent" in b["dday_class"])
        ai_cnt = sum(1 for b in bids if "AI" in b["tags"] or "인공지능" in b["tags"])

        html = re.sub(r'class="value text-blue">.*?<span', f'class="value text-blue">{total_cnt} <span', html)
        html = re.sub(r'class="value text-red">.*?<span', f'class="value text-red">{urgent_cnt} <span', html)
        html = re.sub(r'color:var\(--accent-purple\);">(.*?)<span', f'color:var(--accent-purple);">{ai_cnt} <span', html)
        html = re.sub(r'기준 주차:.*?</div>', f'기준 주차:</strong> {week_str}</div>', html)
        html = re.sub(r'최근 동기화:.*?</div>', f'최근 동기화:</strong> {now_str} (매주 자동 갱신)</div>', html)

        rows_html = ""
        for b in bids:
            rows_html += f"""
        <tr data-category="{b['category']}">
          <td>
            <span class="badge-org">{b['org'][:12]}</span>
            <span class="badge-category {b['cat_class']}">{b['category']}</span>
          </td>
          <td class="title-cell">
            <a href="{b['url']}" target="_blank" class="title-link">
              {b['title']}
            </a>
            <div class="tags-list">{b['tags']}</div>
          </td>
          <td><strong>{b['budget']}</strong><br><span style="font-size:12px; color:#64748b;">{b['budget_sub']}</span></td>
          <td>
            <span class="dday-tag {b['dday_class']}">{b['dday_text']}</span>
            <div style="font-size:12px; color:#64748b; margin-top:2px;">{b['close_date']}</div>
          </td>
          <td>
            <a href="{b['url']}" target="_blank" class="btn-action">나라장터 공고문 ↗</a>
          </td>
        </tr>"""
        
        html = re.sub(r'<tbody>.*?</tbody>', f'<tbody>{rows_html}\n      </tbody>', html, flags=re.DOTALL)
    else:
        # 실시간 데이터 수집 전이어도 시간 정보는 갱신
        html = re.sub(r'최근 동기화:.*?</div>', f'최근 동기화:</strong> {now_str} (매주 자동 갱신)</div>', html)

    # index.html로 최종 저장
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("index.html 정상 빌드 완료!")

if __name__ == "__main__":
    update_html()
