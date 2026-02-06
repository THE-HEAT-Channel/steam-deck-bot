import requests
import json
import os
import time
import re
from bs4 import BeautifulSoup
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

def scrape_official_korean_content(url):
    """
    뉴스 링크로 직접 접속해서 공식 한국어 내용, 유튜브, 실제 상점 링크를 가져옵니다.
    """
    print(f"🕵️‍♂️ 공식 페이지 정밀 분석 중: {url}")
    
    # 1. 한국어 설정으로 접속 (쿠키 설정)
    cookies = {'Steam_Language': 'koreana'}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        response = requests.get(url, cookies=cookies, headers=headers, timeout=10)
        if response.status_code != 200: return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 2. 본문 내용 추출 (공식 한국어)
        # 스팀 뉴스 본문은 보통 'event_body' 또는 'detail_body' 클래스에 있음
        content_div = soup.select_one('.event_body') or soup.select_one('#news_detail_body')
        
        official_text = ""
        youtube_id = None
        store_link = None
        
        if content_div:
            # (A) 텍스트 추출 (깔끔하게)
            official_text = content_div.get_text(separator="\n", strip=True)
            # 너무 길면 자르기 (디스코드 제한)
            if len(official_text) > 300: official_text = official_text[:300] + "..."
            
            # (B) 유튜브 ID 추출
            # iframe이나 data 속성에서 찾기
            iframe = content_div.find('iframe', src=re.compile('youtube'))
            if iframe:
                # src="https://www.youtube.com/embed/VIDEO_ID?..."
                match = re.search(r'embed/([a-zA-Z0-9_-]+)', iframe['src'])
                if match: youtube_id = match.group(1)
            
            # (C) 실제 상점/세일 페이지 링크 추출
            # href에 'store.steampowered.com/sale' 또는 'category' 등이 포함된 링크 찾기
            links = content_div.find_all('a', href=True)
            for link in links:
                href = link['href']
                # 세일 페이지나 페스티벌 페이지 특징
                if "/sale/" in href or "/fests/" in href or "/category/" in href:
                    store_link = href
                    break # 첫 번째 발견된 링크가 보통 메인 이벤트 링크임

        return {
            "text": official_text,
            "youtube_id": youtube_id,
            "store_link": store_link
        }

    except Exception as e:
        print(f"❌ 크롤링 실패: {e}")
        return None

def fetch_steam_sales_news():
    print("📡 스팀 뉴스 API 확인 중...")
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=593110&count=10&format=json"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200: return []
        
        data = response.json()
        news_items = data['appnews']['newsitems']
        
        sales_news = []
        for item in news_items:
            title = item['title']
            
            if any(k.lower() in title.lower() for k in EXCLUDE_KEYWORDS): continue
            
            if any(k.lower() in title.lower() for k in KEYWORDS):
                print(f"🎉 발견: {title}")
                
                # 뉴스 원문 링크
                news_url = item.get('url', '')
                if not news_url:
                    news_url = f"https://store.steampowered.com/news/app/593110/view/{item['gid']}"
                
                # 🔥 [핵심] 링크로 직접 들어가서 정보 긁어오기
                scraped_data = scrape_official_korean_content(news_url)
                
                description = item.get('contents', '') # 기본값 (실패 시 사용)
                youtube_id = None
                real_store_link = news_url # 기본값은 뉴스 링크
                
                if scraped_data:
                    if scraped_data['text']: description = scraped_data['text']
                    if scraped_data['youtube_id']: youtube_id = scraped_data['youtube_id']
                    if scraped_data['store_link']: real_store_link = scraped_data['store_link']
                
                sales_news.append({
                    "id": item['gid'],
                    "title": title,
                    "desc": description,
                    "link": real_store_link, # 뉴스 링크 대신 실제 상점 링크!
                    "youtube_id": youtube_id,
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
        
        # 설명이 너무 길면 한 번 더 자르기 (안전장치)
        clean_desc = news['desc'].replace('[', '').replace(']', '') # 남은 대괄호 제거
        if len(clean_desc) > 250: clean_desc = clean_desc[:250] + "..."

        embed = DiscordEmbed(
            title=f"💸 {news['title']}",
            description=f"{clean_desc}\n\n[👉 축제 상점 페이지 바로가기]({news['link']})",
            color='FFD700'
        )
        
        # 1. 유튜브 썸네일 (최우선)
        if news['youtube_id']:
            embed.set_image(url=f"https://img.youtube.com/vi/{news['youtube_id']}/maxresdefault.jpg")
        # 2. 없으면 스팀 로고
        else:
            embed.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/2048px-Steam_icon_logo.svg.png")
        
        webhook.add_embed(embed)
        webhook.execute()
    except Exception as e:
        print(f"❌ 전송 실패: {e}")

def run():
    print("--- 스팀 세일 봇 (공식 웹 크롤링 버전) ---")
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