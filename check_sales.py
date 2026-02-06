import requests
import json
import os
import time
import re
from bs4 import BeautifulSoup
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

def translate_to_korean(text):
    """영어를 한국어로 번역 (크롤링 실패 시 비상용)"""
    try:
        if len(text) < 2: return text
        # 이미 한글이면 패스
        if any(ord(c) > 12592 for c in text[:20]): return text
        
        translator = GoogleTranslator(source='auto', target='ko')
        # 너무 길면 잘라서 번역
        return translator.translate(text[:900]) 
    except:
        return text

def extract_best_link(raw_text):
    """
    원본 텍스트에서 'category', 'sale', 'fests'가 포함된 '진짜 상점 링크'를 찾아냅니다.
    """
    # 1. 가장 우선순위: category, sale, fests 링크
    # [url=https://store.steampowered.com/...] 형식 파싱
    patterns = [
        r'store\.steampowered\.com/category/[a-zA-Z0-9_/%]+',
        r'store\.steampowered\.com/sale/[a-zA-Z0-9_/%]+',
        r'store\.steampowered\.com/fests/[a-zA-Z0-9_/%]+'
    ]
    
    for pat in patterns:
        match = re.search(pat, raw_text)
        if match:
            return "https://" + match.group(0).replace('"', '').replace(']', '')
            
    return None

def extract_youtube_id(raw_text):
    """원본 텍스트에서 유튜브 ID 추출"""
    # [previewyoutube=ID;full]
    match = re.search(r'previewyoutube=([a-zA-Z0-9_-]+)', raw_text)
    if match: return match.group(1)
    return None

def clean_raw_text(text):
    """지저분한 태그 제거"""
    text = re.sub(r'\[previewyoutube=.*?\]\[/previewyoutube\]', '', text)
    text = re.sub(r'\{STEAM_CLAN_IMAGE\}.+?(\s|\[|$)', '', text)
    text = re.sub(r'\[url=.*?\]', '', text)
    text = re.sub(r'\[/url\]', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\n\s*\n', '\n\n', text).strip()
    return text

def scrape_official_korean(url):
    """공식 한국어 페이지 크롤링 시도"""
    print(f"🕵️‍♂️ 크롤링 시도: {url}")
    cookies = {'Steam_Language': 'koreana', 'birthtime': '946684801', 'lastagecheckage': '1-0-2000'}
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, cookies=cookies, headers=headers, timeout=5)
        if response.status_code != 200: return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        content_div = soup.select_one('.event_body') or soup.select_one('#news_detail_body')
        
        if content_div:
            return content_div.get_text(separator="\n", strip=True)
    except:
        pass
    return None

def fetch_steam_sales_news():
    print("📡 스팀 뉴스 API 스캔 중...")
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=593110&count=10&format=json"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        news_items = data['appnews']['newsitems']
        
        sales_news = []
        for item in news_items:
            title = item['title']
            
            if any(k.lower() in title.lower() for k in EXCLUDE_KEYWORDS): continue
            
            if any(k.lower() in title.lower() for k in KEYWORDS):
                print(f"🎉 발견: {title}")
                raw_content = item.get('contents', '')
                news_url = item.get('url') or f"https://store.steampowered.com/news/app/593110/view/{item['gid']}"

                # 1. [링크] 원본 데이터에서 '진짜 상점 링크' 찾기 (가장 중요!)
                real_link = extract_best_link(raw_content)
                if not real_link:
                    real_link = news_url # 못 찾으면 그냥 뉴스 링크 사용
                
                # 2. [이미지] 원본 데이터에서 유튜브 ID 찾기
                youtube_id = extract_youtube_id(raw_content)
                
                # 3. [텍스트] 한국어 설명 만들기
                # (A) 크롤링 먼저 시도
                korean_text = scrape_official_korean(news_url)
                
                # (B) 크롤링 실패 시 -> 원본 청소 후 번역기 가동
                if not korean_text or len(korean_text) < 10:
                    print("⚠️ 크롤링 실패/차단됨 -> 번역기 모드로 전환")
                    clean_english = clean_raw_text(raw_content)
                    korean_text = translate_to_korean(clean_english)

                # 4. 제목도 번역
                korean_title = translate_to_korean(title)

                # 최종 정리 (길이 제한)
                if len(korean_text) > 250: korean_text = korean_text[:250] + "..."

                sales_news.append({
                    "id": item['gid'],
                    "title": korean_title,
                    "desc": korean_text,
                    "link": real_link,  # 추출한 진짜 링크
                    "youtube_id": youtube_id,
                    "date": item['date']
                })
        
        return sales_news[::-1]
        
    except Exception as e:
        print(f"❌ 에러: {e}")
        return []

def send_discord_alert(news):
    print(f"🚀 전송: {news['title']}")
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    embed = DiscordEmbed(
        title=f"🎪 {news['title']}",
        description=f"{news['desc']}\n\n[👉 축제 상점 페이지 바로가기]({news['link']})",
        color='FFD700'
    )
    
    if news['youtube_id']:
        embed.set_image(url=f"https://img.youtube.com/vi/{news['youtube_id']}/maxresdefault.jpg")
    else:
        embed.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/2048px-Steam_icon_logo.svg.png")
    
    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("--- 스팀 세일 봇 (하이브리드 버전) ---")
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
        print("완료.")
    else:
        print("새로운 소식 없음.")

if __name__ == "__main__":
    run()