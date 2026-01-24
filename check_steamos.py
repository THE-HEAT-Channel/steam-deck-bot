import requests
import json
import os
import time
from discord_webhook import DiscordWebhook, DiscordEmbed
from bs4 import BeautifulSoup

# ================= 설정 =================
WEBHOOK_URL = os.environ.get('WEBHOOK_PRIVATE')

if not WEBHOOK_URL:
    print("⚠️ 오류: WEBHOOK_PRIVATE 설정이 필요합니다.")
    exit()

HISTORY_FILE = "sent_steamos.json"
# 감시 키워드
KEYWORDS = ["Preview", "SteamOS", "Client Update", "Beta", "Stable"]
# =======================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding='utf-8') as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False)

def fetch_steamos_news():
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=1675200&count=10&format=json"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        news_items = data['appnews']['newsitems']
        
        updates = []
        for item in news_items:
            title = item['title']
            
            # 키워드 체크
            if any(k.lower() in title.lower() for k in KEYWORDS):
                # 이미지나 요약 없이 기본 정보만 저장
                updates.append({
                    "id": item['gid'],
                    "title": title,
                    "url": item['url'],
                    "date": item['date']
                })
        return updates[::-1]
    except Exception as e:
        print(f"뉴스 가져오기 실패: {e}")
        return []

def send_private_alert(update):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    title_text = update['title']
    
    # [구분 로직] 제목에 따라 색상과 아이콘 변경
    if "SteamOS" in title_text:
        # SteamOS 업데이트 (파란색)
        category_icon = "💿"
        category_name = "SteamOS 시스템 업데이트"
        color = '00B0F4' 
        
    elif "Client" in title_text:
        # 클라이언트 업데이트 (초록색)
        category_icon = "🎮"
        category_name = "Steam 클라이언트 업데이트"
        color = '00FF00' 
        
    else:
        # 그 외 (드라이버 등 - 회색)
        category_icon = "📢"
        category_name = "기타 업데이트"
        color = 'CCCCCC'

    # [심플한 메시지] 요약 없이 제목과 링크만 전송
    embed = DiscordEmbed(
        title=f"{category_icon} {category_name}",
        description=f"**{title_text}**\n\n[👉 패치노트 원문 보기]({update['url']})",
        color=color
    )
    
    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("스팀OS 감시 시작 (심플 모드)...")
    history = load_history()
    updates = fetch_steamos_news()
    
    updated_history = history[:]
    msg_count = 0
    
    for update in updates:
        if update['id'] not in history:
            print(f"발견: {update['title']}")
            send_private_alert(update)
            updated_history.append(update['id'])
            msg_count += 1
            time.sleep(1)
            
    if msg_count > 0:
        save_history(updated_history)
        print("전송 완료.")
    else:
        print("새로운 업데이트 없음.")

if __name__ == "__main__":
    run()
