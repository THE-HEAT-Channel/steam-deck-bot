import requests
import json
import os
import time
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 =================
# 변수 이름이 맞는지 확인하세요 (NEWSALES)
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
        if len(history) > 500:
            history = history[-500:]
        json.dump(history, f, ensure_ascii=False)

def fetch_new_releases():
    url = "https://store.steampowered.com/search/?sort_by=Released_DESC&category1=998&l=koreana&cc=kr"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"차단됨: {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("#search_resultsRows > a")
        
        games = []
        # 최신 15개 확인
        for row in rows[:15]:
            try:
                # [수정 1] 앱 ID가 '123,456' 처럼 여러 개일 경우 첫 번째만 가져오기 (이미지 깨짐 방지)
                raw_appid = row.get('data-ds-appid')
                if not raw_appid: continue
                appid = raw_appid.split(',')[0] 
                
                title = row.select_one(".title").text.strip()
                link = row['href']
                
                price_text = "가격 정보 없음"
                price_el = row.select_one(".discount_final_price") or row.select_one(".search_price")
                if price_el:
                    price_text = price_el.text.strip()
                    if "Free" in price_text or "무료" in price_text: price_text = "무료"
                
                # [수정 2] 이미지를 더 확실하게 가져오기 (HTML 태그에서 직접 추출 시도)
                img_url = ""
                img_tag = row.select_one(".search_capsule img")
                if img_tag:
                    img_url = img_tag.get('src')
                    # 고해상도 이미지가 있으면 그걸로 교체 (srcset)
                    srcset = img_tag.get('srcset')
                    if srcset:
                        # "url 1x, url 2x" 형태이므로 2x(고화질) 우선 시도
                        img_url = srcset.split(',')[0].split(' ')[0]
                
                # HTML에서 못 찾았으면 기본 URL 생성
                if not img_url:
                    img_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"

                games.append({
                    "id": str(appid),
                    "title": title,
                    "link": link,
                    "price": price_text,
                    "img": img_url
                })
            except Exception as e:
                continue
        
        return games[::-1]
        
    except Exception as e:
        print(f"에러 발생: {e}")
        return []

def send_discord_alert(game):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    embed = DiscordEmbed(title=f"🆕 스팀 신작 출시: {game['title']}", 
                         description=f"**가격:** {game['price']}\n[상점 페이지 구경하기]({game['link']})", 
                         color='00b0f4')
    
    # [수정 3] set_thumbnail 대신 set_image 사용 -> 이미지가 하단에 꽉 차게 나옴
    if game['img']:
        embed.set_image(url=game['img'])
        
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
            time.sleep(1)
            
    if msg_count > 0:
        save_history(updated_history)
        print("업데이트 완료.")
    else:
        print("새로운 신작 없음.")

if __name__ == "__main__":
    run()
