import requests
import json
import os
import time
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 (SETTINGS) =================
WEBHOOK_URL = "https://discord.com/api/webhooks/1464325575505215499/MRwIZuOSNWzHqtZAeKVnKTa9GsgReAq3q7PSKejoq9J2uE2GHvgqjX9qZ6rP911e_-7n"

MIN_REVIEWS = 50  # 리뷰 50개 이상만 알림
HISTORY_FILE = "sent_games.json"
# ==================================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding='utf-8') as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    return {str(appid): "Verified" for appid in data}
                return data
            except:
                return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False)

def fetch_games_by_status(status_name, category_code):
    # l=koreana: 한국어 텍스트 (리뷰 상태 등)
    # cc=kr: 한국 원화 가격
    url = f"https://store.steampowered.com/search/?sort_by=Released_DESC&category1=998&deck_compatibility={category_code}&l=koreana&cc=kr"
    
    try:
        response = requests.get(url, timeout=10)
    except Exception as e:
        print(f"Network Error ({status_name}): {e}")
        return []

    if response.status_code != 200:
        print(f"Steam Blocked ({status_name}): {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    games = []
    
    rows = soup.select("#search_resultsRows > a")
    print(f"🔎 검색됨 ({status_name}): {len(rows)}개")

    for row in rows:
        try:
            appid = row.get('data-ds-appid')
            if not appid: continue
            
            title_tag = row.select_one(".title")
            title = title_tag.text.strip() if title_tag else "Unknown"
            link = row.get('href', '')
            
            # 1. 리뷰 정보 파싱 (상태 텍스트 + 개수)
            review_count = 0
            review_sentiment = "평가 없음"
            
            review_summary = row.select_one(".search_review_summary")
            if review_summary:
                # 툴팁 예: "매우 긍정적<br>이 게임에 대한 사용자 평가 123개 중 90%가..."
                raw_tooltip = review_summary.get('data-tooltip-html', '')
                
                # <br> 기준으로 나누기
                parts = raw_tooltip.split('<br>')
                if parts:
                    review_sentiment = parts[0].strip() # "매우 긍정적" 추출
                
                # 숫자만 추출해서 리뷰 수 계산
                nums = ''.join(filter(str.isdigit, parts[0])) if len(parts) > 0 else "0"
                # 만약 첫 줄에 숫자가 없으면 전체 텍스트에서 찾기
                if not nums and len(parts) > 1:
                     nums = ''.join(filter(str.isdigit, raw_tooltip.split('평가')[1].split('개')[0]))

                # (더 간단한 방법) data-store-tooltip 속성이 없으면 텍스트 파싱
                # 여기서는 기존 로직 유지하되 안전하게 처리
                tooltip_text = raw_tooltip.replace(',', '')
                import re
                match = re.search(r'([0-9]+)개', tooltip_text)
                if match:
                    review_count = int(match.group(1))
            
            # 2. 가격 파싱
            price_text = "가격 정보 없음"
            # 할인 가격이 있으면 .discount_final_price, 없으면 .search_price
            price_element = row.select_one(".discount_final_price")
            if not price_element:
                price_element = row.select_one(".search_price")
            
            if price_element:
                price_text = price_element.text.strip()
                if "Free" in price_text or "무료" in price_text:
                    price_text = "무료"

            # 3. 조건 체크 및 데이터 저장
            if review_count >= MIN_REVIEWS:
                games.append({
                    "id": str(appid),
                    "title": title,
                    "link": link,
                    "reviews": review_count,
                    "sentiment": review_sentiment, # 추가됨
                    "price": price_text,           # 추가됨
                    "status": status_name
                })
        except Exception as e:
            # print(f"Parsing Error: {e}") # 디버깅용
            continue
            
    return games

def send_discord_alert(game, is_update=False, old_status=None):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    if game['status'] == "Verified":
        color = '00ff00' # 초록
        status_icon = "🟢"
    elif game['status'] == "Playable":
        color = 'ffff00' # 노랑
        status_icon = "🟡"
    else:
        color = 'ff0000' # 빨강
        status_icon = "🔴"

    # 메시지 내용 구성 (가격, 평가 추가)
    info_block = (
        f"**가격:** {game['price']}\n"
        f"**평가:** {game['sentiment']} ({game['reviews']}개)\n"
        f"[스팀 상점 페이지 바로가기]({game['link']})"
    )

    if is_update:
        title = f"🔄 스팀덱 등급 변경: {game['title']}"
        desc = f"상태: {old_status} ➔ {status_icon} **{game['status']}**\n{info_block}"
    else:
        title = f"{status_icon} 스팀덱 신규 결과: {game['title']}"
        desc = f"결과: **{game['status']}**\n{info_block}"

    embed = DiscordEmbed(title=title, description=desc, color=color)
    
    # 썸네일 이미지 추가 (스팀 헤더 이미지)
    img_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{game['id']}/header.jpg"
    embed.set_thumbnail(url=img_url)

    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("Bot started...")
    history = load_history()
    
    verified = fetch_games_by_status("Verified", 3)
    playable = fetch_games_by_status("Playable", 2)
    unsupported = fetch_games_by_status("Unsupported", 1)
    
    all_games = verified + playable + unsupported
    
    msg_count = 0
    
    for game in all_games:
        appid = game['id']
        current_status = game['status']
        
        if appid not in history:
            print(f"New: {game['title']}")
            send_discord_alert(game, is_update=False)
            history[appid] = current_status
            msg_count += 1
            time.sleep(1)
            
        elif history[appid] != current_status:
            old_status = history[appid]
            print(f"Changed: {game['title']}")
            send_discord_alert(game, is_update=True, old_status=old_status)
            history[appid] = current_status
            msg_count += 1
            time.sleep(1)
            
    if msg_count > 0:
        save_history(history)
        print("Updated.")
    else:
        print("No changes.")

if __name__ == "__main__":
    run()
