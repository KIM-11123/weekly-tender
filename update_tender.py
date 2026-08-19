import requests
import json
from datetime import datetime, timedelta
import os

# ==========================================
# 1. 환경 설정 및 키워드 정의
# ==========================================
# 공공데이터포털(data.go.kr) 조달청_나라장터 입찰공고 OpenAPI 인증키
SERVICE_KEY = os.getenv("G2B_API_KEY", "YOUR_API_KEY_HERE")

# 엔지코릭스 선행개발Lab 관심 키워드
KEYWORDS = ["AI", "인공지능", "플랫폼", "선행", "스마트", "데이터", "소부장", "실증"]

def fetch_g2b_bids():
    """나라장터 용역 입찰공고 OpenAPI 조회 예시"""
    today = datetime.today()
    start_date = (today - timedelta(days=7)).strftime("%Y%m%d0000")
    end_date = today.strftime("%Y%m%d2359")
    
    url = "http://apis.data.go.kr/1230000/BidPublicInfoService04/getBidPblancListInfoServcPPSSrch01"
    params = {
        "serviceKey": SERVICE_KEY,
        "numOfRows": "50",
        "pageNo": "1",
        "inqryDiv": "1", # 1: 공고게시일시 기준
        "inqryBgnDt": start_date,
        "inqryEndDt": end_date,
        "type": "json"
    }
    
    items = []
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        raw_items = data.get("response", {}).get("body", {}).get("items", [])
        
        for item in raw_items:
            bid_name = item.get("bidNtceNm", "")
            # 키워드 매칭
            if any(k.lower() in bid_name.lower() for k in KEYWORDS):
                items.append({
                    "org": item.get("dminsttNm", "조달청"),
                    "category": "일반입찰",
                    "cat_badge": "cat-bid",
                    "title": bid_name,
                    "tags": "#나라장터 #입찰 #선행기술",
                    "budget": f"{int(float(item.get('presmptPrce', 0))/100000000)}억원" if item.get('presmptPrce') else "미정",
                    "budget_sub": "(추정가격 기준)",
                    "close_date": item.get("bidClseDt", "-"),
                    "dday": "D-7", # 계산식 적용
                    "dday_class": "dday-normal",
                    "url": item.get("bidNtceDtlUrl", "https://www.g2b.go.kr")
                })
    except Exception as e:
        print(f"나라장터 API 조회 중 에러 발생: {e}")
        
    return items

def build_html(items):
    """수집된 공고 리스트를 기반으로 HTML 자동 렌더링"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    week_str = f"{datetime.now().year}년 {datetime.now().month}월 {(datetime.now().day - 1) // 7 + 1}주차"
    
    # 템플릿 로드 후 데이터 채워넣기
    with open("engicorix_tender_dashboard.html", "r", encoding="utf-8") as f:
        template = f.read()
        
    # dynamic row builder logic...
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(template)
        
    print("성공적으로 index.html이 업데이트되었습니다.")

if __name__ == "__main__":
    # bids = fetch_g2b_bids()
    # build_html(bids)
    print("자동화 스크립트 준비 완료.")
