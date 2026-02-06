import requests
import json
import os
import time
import re
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 =================
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_SALES')
if not WEBHOOK_URL:
    WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK')

if not WEBHOOK_URL:
    print("⚠️ [오류] 웹훅 URL이 없습니다. Secrets를 확인하세요!")
    exit()

HISTORY_FILE = "sent_sales.json"

KEYWORDS = [
    "Sale", "Fest", "Festival", "Edition", 
    "세일", "축제", "페스티벌", "대전", "할인", "넥스트 페스트"
]

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
        if len(history) > 50: history = history[-50:]
        json.dump(history, f, ensure_ascii=False)

def clean_steam_text(text):
    video_id = None
    yt_match = re.search(r'\[previewyoutube=([a-zA-Z0-9_-]+);', text)
    if yt_match: video_id = yt_match.group(1)
    text = re.sub(r'\[previewyoutube=.*?\]\[/previewyoutube\]', '', text)
    text = text.replace('[p]', '\n').replace('[/p]', '').replace('[br]', '\n')
    text = text.replace('[list]', '').replace('[/list]', '').replace('[*]', '• ')
    text = re.sub(r'\[url=.*?\](.*?)\[/url\]', r'\1', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\n\s*\n', '\n\n', text).strip()
    return text, video_id

def fetch_steam_sales_news():
    print("📡 스팀 뉴스 서버에 접속 중...") # 디버그 로그
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=593110&count=10&format=json"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200: 
            print(f"❌ 접속 실패: 상태 코드 {response.status_code}")
            return []
        
        data = response.json()
        news_items = data['appnews']['newsitems']
        print(f"✅ 뉴스 {len(news_items)}개를 가져왔습니다. 분석 시작!")

        sales_news = []
        for item in news_items:
            title = item['title']
            
            # [디버그] 어떤 글을 검사 중인지 출력
            print(f"🧐 검사 중: {title}")

            if any(k.lower() in title.lower() for k in EXCLUDE_KEYWORDS):
                print(f"  -> 🚫 제외됨 (제외 키워드 포함)")
                continue

            if any(k.lower() in title.lower() for k in KEYWORDS):
                print(f"  -> 🎉 당첨! (키워드 매칭 성공)")
                link = item.get('url', '')
                if not link:
                    link = f"https://store.steampowered.com/news/app/593110/view/{item['gid']}"
                
                raw_content = item.get('contents', '')
                cleaned_desc, vid_id = clean_steam_text(raw_content)
                if len(cleaned_desc) > 200: cleaned_desc = cleaned_desc[:200] + "..."

                sales_news.append({
                    "id": item['gid'],
                    "title": title,
                    "link": link,
                    "desc": cleaned_desc,
                    "video_id": vid_id,
                    "date": item['date']
                })
            else:
                print(f"  -> 💨 패스 (세일/축제 키워드 없음)")
        
        return sales_news[::-1]
        
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        return []

def send_discord_alert(news):
    print(f"🚀 디스코드 전송 시도: {news['title']}")
    try:
        webhook = DiscordWebhook(url=WEBHOOK_URL)
        embed = DiscordEmbed(
            title=f"💸 스팀 세일&축제 예고: {news['title']}",
            description=f"{news['desc']}\n\n[👉 이벤트 페이지 바로가기]({news['link']})",
            color='FFD700'
        )
        if news['video_id']:
            embed.set_image(url=f"https://img.youtube.com/vi/{news['video_id']}/maxresdefault.jpg")
        else:
            embed.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/2048px-Steam_icon_logo.svg.png")
        
        webhook.add_embed(embed)
        webhook.execute()
        print("✅ 전송 성공!")
    except Exception as e:
        print(f"❌ 전송 실패: {e}")

def run():
    print("--- [디버그 모드] 스팀 세일 봇 시작 ---")
    history = load_history()
    print(f"📂 기존 기록 {len(history)}개 로드됨.")
    
    sales_news = fetch_steam_sales_news()
    
    updated_history = history[:]
    msg_count = 0
    
    for news in sales_news:
        if news['id'] not in history:
            send_discord_alert(news)
            updated_history.append(news['id'])
            msg_count += 1
            time.sleep(1)
        else:
            print(f"💤 이미 보낸 소식이라 건너뜀: {news['title']}")
            
    if msg_count > 0:
        save_history(updated_history)
        print(f"💾 {msg_count}건 전송 완료 및 저장.")
    else:
        print("🤷‍♂️ 새로 보낼 소식이 없습니다. (파일 변경 안 함 -> Push 안 함)")

if __name__ == "__main__":
    run()