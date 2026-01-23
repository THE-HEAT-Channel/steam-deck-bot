import requests
import os
import time
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 =================
# 1회성 채우기용이므로 메인 봇 웹훅(DISCORD_WEBHOOK)을 사용합니다.
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK')

if not WEBHOOK_URL:
    print("⚠️ 오류: 웹훅 URL이 없습니다. Secrets 설정(DISCORD_WEBHOOK)을 확인하세요.")
    exit()

STATUS_KOREAN = {
    "Verified": "완벽 호환",
    "Playable": "플레이 가능",
    "Unsupported": "지원되지 않음"
}
# =======================================

def fetch_top_games(status_name, category_code, limit=10):
    url = f"https://store.steampowered.com/search/?filter=topsellers&category1=998&deck_compatibility={category_code}&l=koreana&cc=kr"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"차단됨: {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("#search_resultsRows > a")
        
        games = []
        count = 0
        
        for row in rows:
            if count >= limit: break
            
            try:
                # [안전장치] 번들 등으로 ID가 여러 개일 경우 첫 번째만 사용
                raw_appid = row.get('data-ds-appid')
                if not raw_appid: continue
                appid = raw_appid.split(',')[0]
                
                title = row.select_one(".title").text.strip()
                link = row['href']
                
                # [이미지] 큰 이미지를 위해 스팀 페이지에서 직접 추출 시도
                img_url = ""
                img_tag = row.select_one(".search_capsule img")
                if img_tag:
                    img_url = img_tag.get('src')
                    srcset = img_tag.get('srcset')
                    if srcset:
                        # 고해상도 이미지 우선
                        img_url = srcset.split(',')[0].split(' ')[0]
                
                # 실패시 기본 헤더 이미지 사용
                if not img_url:
                    img_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"
                
                # 가격 파싱
                price_text = "가격 정보 없음"
                price_el = row.select_one(".discount_final_price") or row.select_one(".search_price")
                if price_el:
                    price_text = price_el.text.strip()
                    if "Free" in price_text or "무료" in price_text: price_text = "무료"
                
                # 평가 파싱
                review_sentiment = "평가 없음"
                review_count = 0
                review_summary = row.select_one(".search_review_summary")
                if review_summary:
                    raw_tooltip = review_summary.get('data-tooltip-html', '')
                    parts = raw_tooltip.split('<br>')
                    if parts: review_sentiment = parts[0].strip()
                    
                    import re
                    match = re.search(r'([0-9,]+)개', raw_tooltip)
                    if match:
                        review_count = int(match.group(1).replace(',', ''))

                games.append({
                    "id": str(appid),
                    "title": title,
                    "link": link,
                    "reviews": review_count,
                    "sentiment": review_sentiment,
                    "price": price_text,
                    "status": status_name,
                    "img": img_url # 이미지 추가
                })
                count += 1
                
            except Exception:
                continue
                
        return games
        
    except Exception as e:
        print(f"에러 발생: {e}")
        return []

def send_discord_alert(game):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    kr_status = STATUS_KOREAN.get(game['status'], game['status'])
    
    if game['status'] == "Verified":
        color = '00ff00'
        status_icon = "🟢"
    elif game['status'] == "Playable":
        color = 'ffff00'
        status_icon = "🟡"
    else:
        color = 'ff0000'
        status_icon = "🔴"

    title = f"{status_icon} 인기 게임 스팀덱 현황: {game['title']}"
    desc = (
        f"**상태:** {kr_status}\n"
        f"**가격:** {game['price']}\n"
        f"**평가:** {game['sentiment']} ({game['reviews']}개)\n"
        f"[스팀 상점 페이지 바로가기]({game['link']})"
    )

    embed = DiscordEmbed(title=title, description=desc, color=color)
    
    # [변경됨] 썸네일 대신 큰 이미지 사용 (set_image)
    if game.get('img'):
        embed.set_image(url=game['img'])
        
    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("📢 인기 게임 리스트 채우기 시작 (큰 이미지 버전)...")
    
    # 인기 순위 상위 10개씩
    verified_games = fetch_top_games("Verified", 3, limit=10)
    playable_games = fetch_top_games("Playable", 2, limit=10)
    
    all_games = verified_games + playable_games
    print(f"총 {len(all_games)}개의 게임을 전송합니다.")
    
    for game in all_games:
        print(f"전송 중: {game['title']}")
        send_discord_alert(game)
        time.sleep(2) 

if __name__ == "__main__":
    run()
