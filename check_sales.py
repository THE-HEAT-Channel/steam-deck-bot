import requests
import json
import os
import time
import re
from discord_webhook import DiscordWebhook, DiscordEmbed
from deep_translator import GoogleTranslator

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

def extract_image_and_clean(text):
    """
    1. 본문에서 이미지 URL을 찾습니다.
    2. 지저분한 태그를 제거합니다.
    """
    image_url = None
    
    # 1. 유튜브 썸네일 찾기 (최우선)
    yt_match = re.search(r'\[previewyoutube=([a-zA-Z0-9_-]+);', text)
    if yt_match:
        image_url = f"https://img.youtube.com/vi/{yt_match.group(1)}/maxresdefault.jpg"

    # 2. 스팀 전용 이미지 태그 찾기 ({STEAM_CLAN_IMAGE}...)
    if not image_url:
        clan_match = re.search(r'\{STEAM_CLAN_IMAGE\}(.+?)(\s|\[|$)', text)
        if clan_match:
            # 스팀 CDN 주소와 결합
            image_url = f"https://clan.cloudflare.steamstatic.com/images/{clan_match.group(1)}"

    # 3. 일반 이미지 태그 ([img]...[/img]) 찾기
    if not image_url:
        img_match = re.search(r'\[img\](.*?)\[/img\]', text)
        if img_match:
            image_url = img_match.group(1)

    # --- 텍스트 청소 ---
    text = re.sub(r'\[previewyoutube=.*?\]\[/previewyoutube\]', '', text)
    text = re.sub(r'\{STEAM_CLAN_IMAGE\}.+?(\s|\[|$)', '', text) # 이미지 태그 제거
    text = re.sub(r'\[img\].*?\[/img\]', '', text) # 이미지 태그 제거
    text = text.replace('[p]', '\n').replace('[/p]', '').replace('[br]', '\n')
    text = text.replace('[list]', '').replace('[/list]', '').replace('[*]', '• ')
    text = re.sub(r'\[url=.*?\](.*?)\[/url\]', r'\1', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\n\s*\n', '\n\n', text).strip()
    
    return text, image_url

def translate_to_korean(text):
    """영어 텍스트를 한국어로 번역합니다."""
    try:
        # 너무 짧거나 이미 한글이 많으면 스킵
        if len(text) < 2: return text
        if any(ord(c) > 12592 for c in text[:10]): return text # 한글 포함 여부 대략 체크
        
        translator = GoogleTranslator(source='auto', target='ko')
        return translator.translate(text)
    except Exception as e:
        print(f"⚠️ 번역 실패: {e}")
        return text # 실패하면 원문 반환

def fetch_steam_sales_news():
    print("📡 스팀 뉴스 서버에 접속 중...")
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=593110&count=10&format=json"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200: return []
        
        data = response.json()
        news_items = data['appnews']['newsitems']
        
        sales_news = []
        for item in news_items:
            title = item['title']
            
            # 키워드 체크
            if any(k.lower() in title.lower() for k in EXCLUDE_KEYWORDS): continue
            
            if any(k.lower() in title.lower() for k in KEYWORDS):
                print(f"🎉 발견: {title}")
                link = item.get('url', '')
                if not link:
                    link = f"https://store.steampowered.com/news/app/593110/view/{item['gid']}"
                
                raw_content = item.get('contents', '')
                
                # 1. 이미지 추출 및 태그 청소
                cleaned_desc, img_url = extract_image_and_clean(raw_content)
                
                # 2. 길이 자르기 (번역 효율을 위해)
                if len(cleaned_desc) > 300: cleaned_desc = cleaned_desc[:300] + "..."
                
                # 3. 한국어 번역 수행
                korean_desc = translate_to_korean(cleaned_desc)
                
                # 4. 제목도 번역 (선택 사항 - 필요 없으면 주석 처리)
                korean_title = translate_to_korean(title)

                sales_news.append({
                    "id": item['gid'],
                    "title": korean_title, # 한국어 제목
                    "original_title": title,
                    "link": link,
                    "desc": korean_desc,   # 한국어 설명
                    "image": img_url,      # 추출된 이미지
                    "date": item['date']
                })
        
        return sales_news[::-1]
        
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        return []

def send_discord_alert(news):
    print(f"🚀 전송: {news['title']}")
    try:
        webhook = DiscordWebhook(url=WEBHOOK_URL)
        
        embed = DiscordEmbed(
            title=f"💸 {news['title']}",
            description=f"{news['desc']}\n\n[👉 이벤트 페이지 바로가기]({news['link']})",
            color='FFD700'
        )
        
        # 이미지가 있으면 크게 설정, 없으면 스팀 로고
        if news['image']:
            embed.set_image(url=news['image'])
        else:
            embed.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/2048px-Steam_icon_logo.svg.png")
        
        webhook.add_embed(embed)
        webhook.execute()
    except Exception as e:
        print(f"❌ 전송 실패: {e}")

def run():
    print("--- 스팀 세일 봇 (한국어/이미지 버전) ---")
    history = load_history()
    sales_news = fetch_steam_sales_news()
    
    updated_history = history[:]
    msg_count = 0
    
    for news in sales_news:
        if news['id'] not in history:
            send_discord_alert(news)
            updated_history.append(news['id'])
            msg_count += 1
            time.sleep(1)
            
    if msg_count > 0:
        save_history(updated_history)
        print("전송 완료.")
    else:
        print("새로운 소식 없음.")

if __name__ == "__main__":
    run()