import os
import requests
import urllib.parse
from datetime import datetime, timedelta
import re

# 1. API 키 처리
SERVICE_KEY = os.getenv("G2B_API_KEY", "").strip()
if "%" in SERVICE_KEY:
    SERVICE_KEY = urllib.parse.unquote(SERVICE_KEY)

CATEGORY_RULES = {
    "선행개발/AI": ["AI", "인공지능", "LLM", "딥러닝", "머신러닝", "알고리즘", "지능형"],
    "소부장/공정": ["소부장", "소재", "부품", "장비", "스마트", "공정", "반도체", "센서", "배터리", "이차전지", "제조"],
    "바이오/신소재": ["바이오", "헬스", "의료", "신소재", "화학"],
    "용역입찰": ["용역", "ISP", "구축", "유지보수", "플랫폼", "데이터", "시스템", "소프트웨어", "SW", "개발", "연구", "실증"]
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
        return items

    try:
        res = requests.get(url, params=params, timeout=15)
        data = res.json()
        raw_items = data.get("response", {}).get("body", {}).get("items", [])
        
        if isinstance(raw_items, dict):
            raw_items = [raw_items]

        for item in raw_items:
            bid_name = item.get("bidNtceNm", "")
            matched = [k for k in ALL_KEYWORDS if k.lower() in bid_name.lower()]
            
            if matched:
                category = classify_category(bid_name)
                bid_no = item.get("bidNtceNo", "")
                
                # 메인 튕김 방지용 원문 검색 포털 링크 (가장 직관적으로 공고문 도달)
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
    except Exception as e:
        print(f"공고 수집 예외: {e}")
        
    return items

def update_html():
    bids = fetch_real_bids()
    print(f"수집된 공고: {len(bids)}건")

    template_file = "engicorix_tender_dashboard.html"
    if not os.path.exists(template_file):
        template_file = "index.html"

    with open(template_file, "r", encoding="utf-8") as f:
        html = f.read()

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    week_str = f"{now.year}년 {now.month}월 {(now.day - 1) // 7 + 1}주차"

    if bids:
        total_cnt = len(bids)
        urgent_cnt = sum(1 for b in bids if "urgent" in b["dday_class"])
        ai_cnt = sum(1 for b in bids if b["category"] in ["선행개발/AI", "소부장/공정"])

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
        
        html = re.sub(r'<tbody>.*?</tbody>', f'<tbody>{rows_html}\n      </tbody>', html, flags=re.DOTALL)

    # JavaScript (복사 알림 + 필터링 + 검색 기능)
    js_script = """
<script>
  function copyBidNo(text) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      alert("공고번호 [" + text + "] 가 복사되었습니다!\\n나라장터 검색창에 붙여넣기(Ctrl+V)하세요.");
    }).catch(() => {
      prompt("아래 공고번호를 복사하세요:", text);
    });
  }

  function filterTable(category, btnElement) {
    const buttons = document.querySelectorAll('.tag-btn');
    buttons.forEach(btn => btn.classList.remove('active'));
    if (btnElement) {
      btnElement.classList.add('active');
    }

    const rows = document.querySelectorAll('#announcementTable tbody tr');
    rows.forEach(row => {
      const rowCat = row.getAttribute('data-category');
      if (category === 'all' || rowCat === category) {
        row.style.display = '';
      } else {
        row.style.display = 'none';
      }
    });
  }

  function searchTable() {
    const input = document.getElementById('searchInput').value.toLowerCase();
    const rows = document.querySelectorAll('#announcementTable tbody tr');

    rows.forEach(row => {
      const text = row.innerText.toLowerCase();
      row.style.display = text.includes(input) ? '' : 'none';
    });
  }
</script>
"""
    html = html.replace("onclick=\"filterTable('all')\"", "onclick=\"filterTable('all', this)\"")
    html = html.replace("onclick=\"filterTable('AI')\"", "onclick=\"filterTable('선행개발/AI', this)\"")
    html = html.replace("onclick=\"filterTable('제조/소부장')\"", "onclick=\"filterTable('소부장/공정', this)\"")
    html = html.replace("onclick=\"filterTable('바이오')\"", "onclick=\"filterTable('바이오/신소재', this)\"")
    html = html.replace("onclick=\"filterTable('용역입찰')\"", "onclick=\"filterTable('용역입찰', this)\"")

    if "<script>" in html:
        html = re.sub(r'<script>.*?</script>', js_script, html, flags=re.DOTALL)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("완벽 대응 index.html 생성 완료!")

if __name__ == "__main__":
    update_html()
