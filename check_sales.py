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

def clean_fallback_text(text):
    """크롤링 실패 시, 원본 텍스트라도 최대한 깔끔하게 청소"""
    # 유튜브 태그 제거
    text = re.sub(r'\[previewyoutube=.*?\]\[/previewyoutube\]', '', text)
    # 이미지 태그 제거
    text = re.sub(r'\{STEAM_CLAN_IMAGE\}.+?(\s|\[|$)', '', text)
    # [url=...] 링크 태그 정리
    text = re.sub(r'\[url=(.*?)\](.*?)\[/url\]', r'\2', text)
    # 나머지 대괄호 태그 제거
    text = re.sub(r'\[.*?\]', '', text)
    return text.strip()

def scrape_steam_page(url):
    print(f"🕵️‍♂️ 페이지 접속 시도: {url}")
    
    # [핵심] 쿠키 3종 세트: 한국어 설정 + 성인 인증 통과
    cookies = {
        'Steam_Language': 'koreana',
        'birthtime': '946684801', # 2000년 1월 1일생으로 위장
        'lastagecheckage': '1-0-2000'
    }
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        response = requests.get(url, cookies=cookies, headers=headers, timeout=10)
        if response.status_code != 200: return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. 본문 찾기 (여러 클래스 시도)
        content_div = soup.select_one('.event_body') or soup.select_one('#news_detail_body') or soup.select_one('.clan_announcement_body')
        
        if not content_div:
            return None

        # 2. 텍스트 추출
        text = content_div.get_text(separator="\n", strip=True)
        # 너무 긴 문단 정리
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        clean_text = "\n\n".join(lines[:10]) # 앞부분 10줄만 가져오기 (요약)

        # 3. 유튜브 ID 찾기 (iframe 또는 data 속성)
        youtube_id = None
        # 방법 A: iframe src에서 찾기
        iframe = content_div.find('iframe', src=re.compile('youtube'))
        if iframe:
            match = re.search(r'embed/([a-zA-Z0-9_-]+)', iframe['src'])
            if match: youtube_id = match.group(1)
        
        # 방법 B: 스팀 전용 태그에서 찾기
        if not youtube_id:
            yt_div = content_div.find('div', attrs={'data-youtube-video-id': True})
            if yt_div: youtube_id = yt_div['data-youtube-video-id']

        # 4. 상점 링크(Sale Page) 찾기
        store_link = None
        # "상점", "세일", "Fest" 등이 포함된 링크 우선 검색
        links = content_div.find_all('a', href=True)
        for link in links:
            href = link['href']
            # 세일 페이지 특징 (/sale/ 또는 /fests/)
            if "/sale/" in href or "/fests/" in href or "/category/" in href:
                store_link = href
                break 

        return {
            "text": clean_text,
            "youtube_id": youtube_id,
            "store_link": store_link
        }

    except Exception as e:
        print(f"❌ 크롤링 에러: {e}")
        return None

def fetch_steam_sales_news():
    print("📡 스팀 뉴스 API 스캔 중...")
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=593110&count=10&format=json"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200: return []
        
        data = response.json()
        news_items = data['appnews']['newsitems']
        
        sales_news = []
        for item in news_items:
            title = item['title']
            
            # 키워드 필터링
            if any(k.lower() in title.lower() for k in EXCLUDE_KEYWORDS): continue
            
            if any(k.lower() in title.lower() for k in KEYWORDS):
                print(f"🎉 타겟 발견: {title}")
                
                news_url = item.get('url', '')
                if not news_url:
                    news_url = f"https://store.steampowered.com/news/app/593110/view/{item['gid']}"
                
                # --- [크롤링 시도] ---
                scraped = scrape_steam_page(news_url)
                
                # 기본값 설정
                final_desc = clean_fallback_text(item.get('contents', ''))[:200]
                final_link = news_url
                final_youtube = None
                
                if scraped:
                    print("✅ 크롤링 성공! 데이터를 덮어씁니다.")
                    if scraped['text']: final_desc = scraped['text'][:300] + "..." # 길이 제한
                    if scraped['store_link']: final_link = scraped['store_link']
                    if scraped['youtube_id']: final_youtube = scraped['youtube_id']
                else:
                    print("⚠️ 크롤링 실패. API 원본 데이터를 청소해서 사용합니다.")

                sales_news.append({
                    "id": item['gid'],
                    "title": title,
                    "desc": final_desc,
                    "link": final_link,
                    "youtube_id": final_youtube,
                    "date": item['date']
                })
        
        return sales_news[::-1]
        
    except Exception as e:
        print(f"❌ 전체 로직 에러: {e}")
        return []

def send_discord_alert(news):
    print(f"🚀 디스코드 전송: {news['title']}")
    try:
        webhook = DiscordWebhook(url=WEBHOOK_URL)
        
        # 제목에 "축제" 느낌 추가
        embed = DiscordEmbed(
            title=f"🎪 {news['title']}",
            description=f"{news['desc']}\n\n[👉 축제 상점 페이지 바로가기]({news['link']})",
            color='FFD700'
        )
        
        # 이미지 설정
        if news['youtube_id']:
            # 유튜브 썸네일 (가장 깔끔)
            embed.set_image(url=f"https://img.youtube.com/vi/{news['youtube_id']}/maxresdefault.jpg")
        else:
            # 스팀 로고
            embed.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/2048px-Steam_icon_logo.svg.png")
        
        webhook.add_embed(embed)
        webhook.execute()
    except Exception as e:
        print(f"❌ 전송 실패: {e}")

def run():
    print("--- 스팀 세일 봇 (최종 수정판) ---")
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