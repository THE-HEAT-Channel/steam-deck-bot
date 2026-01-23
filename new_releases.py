import requests
import json
import os
import time
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 =================
# [중요] 아까 만든 'DISCORD_WEBHOOK_NEW' 비밀키를 사용합니다.
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_NEWSALES')

if not WEBHOOK_URL:
    print("⚠️ 오류: 신작 알림용 웹훅 URL이 없습니다. Secrets 설정을 확인하세요.")
    exit()

HISTORY_FILE = "sent_new_releases.json"
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
        # 최근 500개만 저장 (용량 관리)
        if len(history) > 500:
            history = history[-500:]
        json.dump(history, f, ensure_ascii=False)

def fetch_new_releases():
    # 정렬: 출시일 순(Released_DESC), 카테고리: 게임(category1=998)
    # 언어: 한국어, 통화: KRW
    url = "https://store.steampowered.com/search/?sort_by=Released_DESC&category1=998&l=koreana&cc=kr"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"차단됨: {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("#search_resultsRows > a")
        
        games = []
        # 최신 15개만 확인 (너무 많이 긁으면 과거 게임까지 알림 갈 수 있음)
        for row in rows[:15]:
            try:
                appid = row.get('data-ds-appid')
                if not appid: continue
                
                title = row.select_one(".title").text.strip()
                link = row['href']
                
                # 가격 파싱
                price_text = "가격 정보 없음"
                price_el = row.select_one(".discount_final_price") or row.select_one(".search_price")
                if price_el:
                    price_text = price_el.text.strip()
                    if "Free" in price_text or "무료" in price_text: price_text = "무료"
                
                # 이미지 (헤더 이미지)
                img_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"

                # 태그(장르) 파싱 - 있으면 좋음
                tags = []
                # (스팀 검색 페이지는 태그 정보를 간단하게만 줌, 생략 가능하지만 일단 시도)
                
                games.append({
                    "id": str(appid),
                    "title": title,
                    "link": link,
                    "price": price_text,
                    "img": img_url
                })
            except Exception:
                continue
        
        # 최신순 정렬되어 있으므로, 역순(과거->최신)으로 뒤집어서 알림 보내면 더 자연스러움
        return games[::-1]
        
    except Exception as e:
        print(f"에러 발생: {e}")
        return []

def send_discord_alert(game):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    embed = DiscordEmbed(title=f"🆕 스팀 신작 출시: {game['title']}", 
                         description=f"**가격:** {game['price']}\n[상점 페이지 구경하기]({game['link']})", 
                         color='00b0f4') # 하늘색
    
    embed.set_thumbnail(url=game['img'])
    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("신작 스캔 시작...")
    history = load_history()
    new_games = fetch_new_releases()
    
    updated_history = history[:]
    msg_count = 0
    
    for game in new_games:
        if game['id'] not in history:
            print(f"발견: {game['title']}")
            send_discord_alert(game)
            updated_history.append(game['id'])
            msg_count += 1
            time.sleep(1) # 도배 방지
            
    if msg_count > 0:
        save_history(updated_history)
        print("업데이트 완료.")
    else:
        print("새로운 신작 없음.")

if __name__ == "__main__":
    run()
