import requests
import json
import os
import time
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 =================
# 나만 보는 개인 채널 웹훅 (WEBHOOK_PRIVATE)
WEBHOOK_URL = os.environ.get('WEBHOOK_PRIVATE')

if not WEBHOOK_URL:
    print("⚠️ 오류: WEBHOOK_PRIVATE 시크릿이 설정되지 않았습니다.")
    exit()

HISTORY_FILE = "sent_steamos.json"

# [핵심] 감시할 키워드 (Preview, Beta가 포함되면 감지!)
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
    # 스팀덱(AppID: 1675200)의 공식 뉴스 피드 가져오기
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=1675200&count=10&format=json"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        news_items = data['appnews']['newsitems']
        
        updates = []
        for item in news_items:
            title = item['title']
            # 키워드가 하나라도 포함되어 있으면 감지
            if any(k.lower() in title.lower() for k in KEYWORDS):
                # 스팀덱 기본 헤더 이미지 사용
                img_url = "https://cdn.cloudflare.steamstatic.com/steam/apps/1675200/header.jpg"

                updates.append({
                    "id": item['gid'],
                    "title": title,
                    "url": item['url'],
                    "date": item['date'],
                    "img": img_url
                })
        
        # 최신순 정렬 뒤집기 (과거 -> 최신 순 전송)
        return updates[::-1]
    except Exception as e:
        print(f"뉴스 가져오기 실패: {e}")
        return []

def send_private_alert(update):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    # 미리보기(Preview)나 베타(Beta)는 눈에 띄게 색상 변경 (보라색)
    # 정식 버전은 파란색
    if "Preview" in update['title'] or "Beta" in update['title']:
        color = 'ff00ff' # 🟣 보라색 (테스트 버전)
        title_prefix = "🧪 스팀OS 테스트/프리뷰:"
    else:
        color = '00b0f4' # 🔵 파란색 (정식 버전)
        title_prefix = "📢 스팀OS 정식 소식:"

    embed = DiscordEmbed(title=f"{title_prefix} {update['title']}", 
                         description=f"주인님, 새로운 업데이트 소식입니다.\n[패치노트 확인하기]({update['url']})", 
                         color=color)
    
    # 이미지를 큼지막하게 표시 (set_image)
    embed.set_image(url=update['img'])
    
    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("스팀OS 감시 시작...")
    history = load_history()
    updates = fetch_steamos_news()
    
    updated_history = history[:]
    msg_count = 0
    
    for update in updates:
        if update['id'] not in history:
            print(f"새 업데이트 발견: {update['title']}")
            send_private_alert(update)
            updated_history.append(update['id'])
            msg_count += 1
            time.sleep(1)
            
    if msg_count > 0:
        save_history(updated_history)
        print("알림 전송 완료.")
    else:
        print("새로운 업데이트 없음.")

if __name__ == "__main__":
    run()
