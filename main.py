import requests
import json
import os
import time
import random
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 (SETTINGS) =================
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK')

if not WEBHOOK_URL:
    print("⚠️ 오류: 웹훅 URL을 찾을 수 없습니다. Secrets 설정(DISCORD_WEBHOOK)을 확인하세요.")
    exit()

MIN_REVIEWS = 100  # 인기 게임 기준
HISTORY_FILE = "sent_games.json"

# [핵심] 4가지 등급 + 한국어 표기 + 아이콘
STATUS_INFO = {
    "Verified": {"text": "완벽 호환", "icon": "🟢", "color": "00FF00"},
    "Playable": {"text": "플레이 가능", "icon": "🟡", "color": "FFFF00"},
    "Unsupported": {"text": "지원 안 됨", "icon": "🔴", "color": "FF0000"},
    "Unknown": {"text": "알 수 없음", "icon": "❓", "color": "CCCCCC"}
}

# 검색할 페이지 수 (안전하게 2페이지)
PAGES_TO_SCAN = 2 
# ==================================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding='utf-8') as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    return {str(appid): "Unknown" for appid in data}
                return data
            except:
                return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False)

def fetch_games_by_status(status_name, category_code):
    games = []
    
    for page in range(PAGES_TO_SCAN):
        start_count = page * 50
        # 인기순(Reviews_DESC) 정렬
        url = f"https://store.steampowered.com/search/?sort_by=Reviews_DESC&category1=998&deck_compatibility={category_code}&l=koreana&cc=kr&start={start_count}"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                break
            
            soup = BeautifulSoup(response.text, "html.parser")
            rows = soup.select("#search_resultsRows > a")
            
            if not rows: break

            for row in rows:
                try:
                    raw_appid = row.get('data-ds-appid')
                    if not raw_appid: continue
                    appid = raw_appid.split(',')[0]
                    
                    title = row.select_one(".title").text.strip()
                    link = row.get('href', '')
                    
                    img_url = ""
                    img_tag = row.select_one(".search_capsule img")
                    if img_tag:
                        img_url = img_tag.get('src')
                        srcset = img_tag.get('srcset')
                        if srcset:
                            img_url = srcset.split(',')[0].split(' ')[0]
                    
                    if not img_url:
                        img_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"
                    
                    # 리뷰 수 파싱
                    review_count = 0
                    review_sentiment = "평가 없음"
                    review_summary = row.select_one(".search_review_summary")
                    if review_summary:
                        raw_tooltip = review_summary.get('data-tooltip-html', '')
                        parts = raw_tooltip.split('<br>')
                        if parts: review_sentiment = parts[0].strip()
                        import re
                        match = re.search(r'([0-9,]+)개', raw_tooltip)
                        if match: review_count = int(match.group(1).replace(',', ''))
                    
                    price_text = "가격 정보 없음"
                    price_el = row.select_one(".discount_final_price") or row.select_one(".search_price")
                    if price_el: price_text = price_el.text.strip()

                    if review_count >= MIN_REVIEWS:
                        games.append({
                            "id": str(appid),
                            "title": title,
                            "link": link,
                            "reviews": review_count,
                            "sentiment": review_sentiment,
                            "price": price_text,
                            "status": status_name,
                            "img": img_url
                        })
                except: continue
            time.sleep(1)
        except: break
    return games

def send_discord_alert(game, is_update=False, old_status=None):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    # 현재 상태 정보 가져오기
    curr_info = STATUS_INFO.get(game['status'], STATUS_INFO["Unknown"])
    
    info_block = (
        f"**가격:** {game['price']}\n"
        f"**평가:** {game['sentiment']} ({format(game['reviews'], ',')}개)\n"
        f"[스팀 상점 페이지 바로가기]({game['link']})"
    )

    if is_update:
        # [핵심] 변경일 경우: A -> B 형식으로 표시
        old_info = STATUS_INFO.get(old_status, STATUS_INFO["Unknown"])
        
        title = f"🔄 호환성 등급 변경: {game['title']}"
        desc = (
            f"**{old_info['icon']} {old_info['text']}**"
            f"  ➔  "
            f"**{curr_info['icon']} {curr_info['text']}**\n\n"
            f"{info_block}"
        )
        color = curr_info['color']
        
    else:
        # 신규 발견일 경우
        title = f"{curr_info['icon']} 스팀덱 호환성 확인: {game['title']}"
        desc = f"**현재 상태: {curr_info['text']}**\n\n{info_block}"
        color = curr_info['color']

    embed = DiscordEmbed(title=title, description=desc, color=color)
    if game.get('img'):
        embed.set_image(url=game['img'])

    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("스팀덱 게임 호환성 체크 중 (4등급)...")
    history = load_history()
    
    # 4가지 카테고리 모두 스캔 (Unknown=0, Unsupported=1, Playable=2, Verified=3)
    target_categories = [
        ("Verified", 3),
        ("Playable", 2),
        ("Unsupported", 1),
        ("Unknown", 0)
    ]
    
    all_fetched_games = []
    for status_name, code in target_categories:
        games = fetch_games_by_status(status_name, code)
        all_fetched_games.extend(games)
        time.sleep(1)
    
    unique_games = {g['id']: g for g in all_fetched_games}
    msg_count = 0
    
    for game in unique_games.values():
        appid = game['id']
        current_status = game['status']
        
        # 1. 신규 발견 (Unknown 제외하고 알림)
        if appid not in history:
            if current_status != "Unknown": 
                print(f"✨ 신규: {game['title']}")
                send_discord_alert(game, is_update=False)
                msg_count += 1
                time.sleep(1)
            history[appid] = current_status
            
        # 2. 상태 변경 (이전 기록과 다르면)
        elif history[appid] != current_status:
            old_status = history[appid]
            print(f"🔄 변경: {game['title']} ({old_status} -> {current_status})")
            send_discord_alert(game, is_update=True, old_status=old_status)
            history[appid] = current_status
            msg_count += 1
            time.sleep(1)
            
    if msg_count > 0:
        save_history(history)
        print("저장 완료.")
    else:
        print("변경 없음.")

if __name__ == "__main__":
    run()
