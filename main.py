import requests
import json
import os
import time
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 (SETTINGS) =================
# [주의] 호환성 체크 봇은 'DISCORD_WEBHOOK'이라는 이름의 키를 사용합니다.
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK')

if not WEBHOOK_URL:
    print("⚠️ 오류: 웹훅 URL을 찾을 수 없습니다. Secrets 설정(DISCORD_WEBHOOK)을 확인하세요.")
    exit()

MIN_REVIEWS = 50  # 리뷰 50개 이상인 게임만 알림
HISTORY_FILE = "sent_games.json"

STATUS_KOREAN = {
    "Verified": "완벽 호환",
    "Playable": "플레이 가능",
    "Unsupported": "지원되지 않음"
}
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
            # [개선] 앱 ID 파싱 안전장치 추가
            raw_appid = row.get('data-ds-appid')
            if not raw_appid: continue
            appid = raw_appid.split(',')[0]
            
            title_tag = row.select_one(".title")
            title = title_tag.text.strip() if title_tag else "Unknown"
            link = row.get('href', '')
            
            # [개선] 이미지 추출 로직 강화 (HTML에서 직접 추출 시도)
            img_url = ""
            img_tag = row.select_one(".search_capsule img")
            if img_tag:
                img_url = img_tag.get('src')
                srcset = img_tag.get('srcset')
                if srcset:
                    img_url = srcset.split(',')[0].split(' ')[0]
            
            # 없으면 기본 헤더 이미지 사용
            if not img_url:
                img_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"
            
            # 리뷰 파싱
            review_count = 0
            review_sentiment = "평가 없음"
            review_summary = row.select_one(".search_review_summary")
            
            if review_summary:
                raw_tooltip = review_summary.get('data-tooltip-html', '')
                parts = raw_tooltip.split('<br>')
                if parts:
                    review_sentiment = parts[0].strip()
                
                # 숫자 추출
                import re
                match = re.search(r'([0-9,]+)개', raw_tooltip)
                if match:
                    review_count = int(match.group(1).replace(',', ''))
            
            # 가격 파싱
            price_text = "가격 정보 없음"
            price_el = row.select_one(".discount_final_price") or row.select_one(".search_price")
            
            if price_el:
                price_text = price_el.text.strip()
                if "Free" in price_text or "무료" in price_text:
                    price_text = "무료"

            if review_count >= MIN_REVIEWS:
                games.append({
                    "id": str(appid),
                    "title": title,
                    "link": link,
                    "reviews": review_count,
                    "sentiment": review_sentiment,
                    "price": price_text,
                    "status": status_name,
                    "img": img_url # 이미지 URL 저장
                })
        except Exception:
            continue
            
    return games

def send_discord_alert(game, is_update=False, old_status=None):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    kr_status = STATUS_KOREAN.get(game['status'], game['status'])
    kr_old_status = STATUS_KOREAN.get(old_status, old_status)

    if game['status'] == "Verified":
        color = '00ff00' 
        status_icon = "🟢"
    elif game['status'] == "Playable":
        color = 'ffff00' 
        status_icon = "🟡"
    else:
        color = 'ff0000' 
        status_icon = "🔴"

    info_block = (
        f"**가격:** {game['price']}\n"
        f"**평가:** {game['sentiment']} ({game['reviews']}개)\n"
        f"[스팀 상점 페이지 바로가기]({game['link']})"
    )

    if is_update:
        title = f"🔄 스팀덱 등급 변경: {game['title']}"
        desc = f"상태: {kr_old_status} ➔ {status_icon} **{kr_status}**\n{info_block}"
    else:
        title = f"{status_icon} 스팀덱 신규 결과: {game['title']}"
        desc = f"결과: **{kr_status}**\n{info_block}"

    embed = DiscordEmbed(title=title, description=desc, color=color)
    
    # [핵심 변경] set_thumbnail -> set_image (큰 이미지)
    if game.get('img'):
        embed.set_image(url=game['img'])

    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("Bot started...")
    history = load_history()
    
    verified = fetch_games_by_status("Verified", 3)
    playable = fetch_games_by_status("Playable", 2)
    unsupported = fetch_games_by_status("Unsupported", 1)
    
    # 중복 제거 로직
    all_raw_games = verified + playable + unsupported
    unique_games = {}
    
    for g in all_raw_games:
        if g['id'] not in unique_games:
            unique_games[g['id']] = g
    
    msg_count = 0
    
    for game in unique_games.values():
        appid = game['id']
        current_status = game['status']
        
        if appid not in history:
            print(f"New: {game['title']} ({current_status})")
            send_discord_alert(game, is_update=False)
            history[appid] = current_status
            msg_count += 1
            time.sleep(1)
            
        elif history[appid] != current_status:
            old_status = history[appid]
            print(f"Changed: {game['title']} ({old_status} -> {current_status})")
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
