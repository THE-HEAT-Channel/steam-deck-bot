import requests
import json
import os
import time
import re
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 =================
# 세일 알림용 웹훅 주소를 따로 쓰셔도 되고, 기존 것을 쓰셔도 됩니다.
# 여기서는 'DISCORD_WEBHOOK_SALES'라는 이름의 환경변수를 사용한다고 가정합니다.
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_SALES')

# 만약 별도 웹훅을 안 만들었다면, 기존 'DISCORD_WEBHOOK'을 쓰도록 자동 대치
if not WEBHOOK_URL:
    WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK')

if not WEBHOOK_URL:
    print("⚠️ 오류: 웹훅 URL이 없습니다.")
    exit()

HISTORY_FILE = "sent_sales.json"

# 🔥 감시할 키워드 (이 단어가 제목에 있어야 알림을 보냄)
KEYWORDS = [
    "Sale", "Fest", "Festival", "Edition", # 영문 키워드
    "세일", "축제", "페스티벌", "대전", "할인", "넥스트 페스트" # 한글 키워드
]

# 🚫 제외할 키워드 (사운드트랙, 단순 패치노트 등 방지)
EXCLUDE_KEYWORDS = ["Soundtrack", "OST", "Patch", "Hotfix"]
# =======================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding='utf-8') as f:
            try: return json.load(f)
            except: return []
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding='utf-8') as f:
        # 최근 50개만 저장
        if len(history) > 50: history = history[-50:]
        json.dump(history, f, ensure_ascii=False)

def fetch_steam_sales_news():
    # AppID 593110은 스팀 공식 뉴스 채널입니다.
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=593110&count=10&format=json"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200: return []
        
        data = response.json()
        news_items = data['appnews']['newsitems']
        
        sales_news = []
        for item in news_items:
            title = item['title']
            
            # 1. 제외 키워드 확인
            if any(k.lower() in title.lower() for k in EXCLUDE_KEYWORDS):
                continue

            # 2. 포함 키워드 확인 (세일, 페스티벌 등)
            if any(k.lower() in title.lower() for k in KEYWORDS):
                
                # 링크 처리: url이 없으면 기본 뉴스 페이지로
                link = item.get('url', '')
                if not link:
                    link = f"https://store.steampowered.com/news/app/593110/view/{item['gid']}"
                
                # 본문 내용 미리보기 (HTML 태그 제거)
                content = item.get('contents', '')
                # 정규식으로 HTML 태그 제거 및 길이 제한
                clean_content = re.sub('<[^<]+?>', '', content)[:150] + "..."

                sales_news.append({
                    "id": item['gid'],
                    "title": title,
                    "link": link,
                    "desc": clean_content,
                    "date": item['date']
                })
        
        # 최신순 정렬 되어있으므로 뒤집어서 과거->현재 순으로 처리
        return sales_news[::-1]
        
    except Exception as e:
        print(f"뉴스 가져오기 실패: {e}")
        return []

def send_discord_alert(news):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    embed = DiscordEmbed(
        title=f"💸 스팀 세일&축제 예고: {news['title']}",
        description=f"{news['desc']}\n\n[👉 이벤트 페이지 바로가기]({news['link']})",
        color='FFD700' # 금색 (특별함 강조)
    )
    
    # 이미지: 스팀 공식 뉴스 썸네일은 API가 직접 안 주므로, 기본 '세일' 느낌의 이미지를 넣거나 생략
    # 여기선 깔끔하게 텍스트 위주로 가거나, 스팀 로고 사용
    embed.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/2048px-Steam_icon_logo.svg.png")
    
    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("🛒 스팀 세일/축제 감시 시작...")
    history = load_history()
    sales_news = fetch_steam_sales_news()
    
    updated_history = history[:]
    msg_count = 0
    
    for news in sales_news:
        if news['id'] not in history:
            print(f"🎉 발견: {news['title']}")
            send_discord_alert(news)
            updated_history.append(news['id'])
            msg_count += 1
            time.sleep(1)
            
    if msg_count > 0:
        save_history(updated_history)
        print("전송 완료.")
    else:
        print("새로운 세일 소식 없음.")

if __name__ == "__main__":
    run()