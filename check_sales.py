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
    print("⚠️ 오류: 웹훅 URL이 없습니다.")
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
    """스팀의 지저분한 BBCode 태그를 정리하고, 유튜브 ID를 추출합니다."""
    video_id = None
    
    # 1. 유튜브 영상 태그가 있다면 ID 추출 (썸네일용)
    # 예: [previewyoutube=4P-0Ol3scWk;full]
    yt_match = re.search(r'\[previewyoutube=([a-zA-Z0-9_-]+);', text)
    if yt_match:
        video_id = yt_match.group(1)

    # 2. 태그 정리
    # [previewyoutube] 전체 제거
    text = re.sub(r'\[previewyoutube=.*?\]\[/previewyoutube\]', '', text)
    # [p], [br] -> 줄바꿈
    text = text.replace('[p]', '\n').replace('[/p]', '').replace('[br]', '\n')
    # [list], [*] -> 목록 스타일
    text = text.replace('[list]', '').replace('[/list]', '').replace('[*]', '• ')
    # [url=...] -> 링크 텍스트만 남기기 (디스코드에서 깨짐 방지) 또는 제거
    text = re.sub(r'\[url=.*?\](.*?)\[/url\]', r'\1', text)
    # 나머지 [tag] 형태 모두 제거
    text = re.sub(r'\[.*?\]', '', text)
    
    # 3. 다중 공백 및 줄바꿈 정리
    text = re.sub(r'\n\s*\n', '\n\n', text).strip()
    
    return text, video_id

def fetch_steam_sales_news():
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=593110&count=10&format=json"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200: return []
        
        data = response.json()
        news_items = data['appnews']['newsitems']
        
        sales_news = []
        for item in news_items:
            title = item['title']
            raw_content = item.get('contents', '')
            
            if any(k.lower() in title.lower() for k in EXCLUDE_KEYWORDS):
                continue

            if any(k.lower() in title.lower() for k in KEYWORDS):
                link = item.get('url', '')
                if not link:
                    link = f"https://store.steampowered.com/news/app/593110/view/{item['gid']}"
                
                # 텍스트 정리 및 비디오 ID 추출
                cleaned_desc, vid_id = clean_steam_text(raw_content)
                
                # 설명이 너무 길면 자르기
                if len(cleaned_desc) > 200:
                    cleaned_desc = cleaned_desc[:200] + "..."

                sales_news.append({
                    "id": item['gid'],
                    "title": title,
                    "link": link,
                    "desc": cleaned_desc,
                    "video_id": vid_id, # 유튜브 ID 추가
                    "date": item['date']
                })
        
        return sales_news[::-1]
        
    except Exception as e:
        print(f"뉴스 가져오기 실패: {e}")
        return []

def send_discord_alert(news):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    embed = DiscordEmbed(
        title=f"💸 스팀 세일&축제 예고: {news['title']}",
        description=f"{news['desc']}\n\n[👉 이벤트 페이지 바로가기]({news['link']})",
        color='FFD700'
    )
    
    # [이미지 처리 로직]
    if news['video_id']:
        # 1순위: 유튜브 썸네일이 있으면 그걸 사용 (가장 깔끔함)
        img_url = f"https://img.youtube.com/vi/{news['video_id']}/maxresdefault.jpg"
        embed.set_image(url=img_url)
    else:
        # 2순위: 없으면 스팀 기본 로고 (썸네일로 작게 표시)
        embed.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/2048px-Steam_icon_logo.svg.png")
    
    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("🛒 스팀 세일/축제 감시 시작 (텍스트 정리 버전)...")
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