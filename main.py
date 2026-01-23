import requests
import json
import os
import time
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 (SETTINGS) =================
# 여기에 본인의 디스코드 웹훅 주소를 넣어주세요
WEBHOOK_URL = "https://discord.com/api/webhooks/1464325575505215499/MRwIZuOSNWzHqtZAeKVnKTa9GsgReAq3q7PSKejoq9J2uE2GHvgqjX9qZ6rP911e_-7n"

MIN_REVIEWS = 50  # 리뷰 50개 이상인 게임만 알림
HISTORY_FILE = "sent_games.json"

# 한글 상태 표기 맵핑
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
    # l=koreana: 한국어, cc=kr: 한국 원화
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
            
            # 리뷰 파싱
            review_count = 0
            review_sentiment = "평가 없음"
            review_summary = row.select_one(".search_review_summary")
            
            if review_summary:
                raw_tooltip = review_summary.get('data-tooltip-html', '')
                parts = raw_tooltip.split('<br>')
                if parts:
                    review_sentiment = parts[0].strip()
                
                # 숫자만 추출
                nums = ''.join(filter(str.isdigit, raw_tooltip))
                # 너무 긴 숫자(날짜 등)가 섞일 수 있으므로 '개' 앞의 숫자나 패턴으로 찾기
                if "사용자 평가" in raw_tooltip and "개" in raw_tooltip:
                     try:
                        # 예: "사용자 평가 211개 중" -> 211 추출
                        check_str = raw_tooltip.split("사용자 평가")[1].split("개")[0]
                        review_count = int(''.join(filter(str.isdigit, check_str)))
                     except:
                        pass
                elif nums:
                     # 단순 숫자 추출 (가장 간단한 방식, 오차 가능성 낮음)
                     # 보통 툴팁에 "211 user reviews" 식으로 나오므로
                     # 첫 번째로 발견되는 의미있는 숫자 덩어리를 씀
                     # 여기서는 안전하게 기존 방식 유지하되 0 처리
                     import re
                     match = re.search(r'([0-9,]+)개', raw_tooltip)
                     if match:
                         review_count = int(match.group(1).replace(',', ''))
            
            # 가격 파싱
            price_text = "가격 정보 없음"
            price_element = row.select_one(".discount_final_price")
            if not price_element:
                price_element = row.select_one(".search_price")
            
            if price_element:
                price_text = price_element.text.strip()
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
                    "status": status_name
                })
        except Exception:
            continue
            
    return games

def send_discord_alert(game, is_update=False, old_status=None):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    # 영문 상태 -> 한글 상태 변환
    kr_status = STATUS_KOREAN.get(game['status'], game['status'])
    kr_old_status = STATUS_KOREAN.get(old_status, old_status)

    if game['status'] == "Verified":
        color = '00ff00' # 초록
        status_icon = "🟢"
    elif game['status'] == "Playable":
        color = 'ffff00' # 노랑
        status_icon = "🟡"
    else:
        color = 'ff0000' # 빨강
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
    img_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{game['id']}/header.jpg"
    embed.set_thumbnail(url=img_url)

    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("Bot started...")
    history = load_history()
    
    # 1. 모든 상태 수집
    verified = fetch_games_by_status("Verified", 3)
    playable = fetch_games_by_status("Playable", 2)
    unsupported = fetch_games_by_status("Unsupported", 1)
    
    # 2. [핵심 수정] 중복 제거 및 우선순위 정하기
    # Verified가 리스트 앞에 오므로, 먼저 딕셔너리에 넣으면 나중에 오는 Unsupported는 무시됨
    # (반대로 넣어야 나중에 덮어씌워지지 않게 하려면, '이미 있으면 패스' 하는 로직 사용)
    
    all_raw_games = verified + playable + unsupported
    unique_games = {}
    
    for g in all_raw_games:
        # 이미 딕셔너리에 이 게임이 있다면? (즉, 더 좋은 등급으로 이미 처리됐다면) 건너뜀
        if g['id'] not in unique_games:
            unique_games[g['id']] = g
    
    # 이제 unique_games.values()에는 각 게임별로 가장 우선순위 높은 등급 하나만 남음
    
    msg_count = 0
    
    for game in unique_games.values():
        appid = game['id']
        current_status = game['status']
        
        # 신규 발견
        if appid not in history:
            print(f"New: {game['title']} ({current_status})")
            send_discord_alert(game, is_update=False)
            history[appid] = current_status
            msg_count += 1
            time.sleep(1)
            
        # 상태 변경
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
