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

MIN_REVIEWS = 100  # 인기 게임 기준 (리뷰 100개 이상)
HISTORY_FILE = "sent_games.json"

# [핵심] 4가지 등급으로 확장 (Unknown 추가)
STATUS_KOREAN = {
    "Verified": "🟢 완벽 호환 (Verified)",
    "Playable": "🟡 플레이 가능 (Playable)",
    "Unsupported": "🔴 지원 안 됨 (Unsupported)",
    "Unknown": "❓ 알 수 없음 (Unknown)"
}

# 검색할 페이지 수 (안전하게 2페이지, 즉 카테고리당 100개씩 체크)
PAGES_TO_SCAN = 2 
# ==================================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding='utf-8') as f:
            try:
                data = json.load(f)
                # 구버전 호환성 유지
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
    
    # [핵심] 여러 페이지 스캔 (안전하게 끊어서 요청)
    for page in range(PAGES_TO_SCAN):
        start_count = page * 50
        # sort_by=Reviews_DESC: 리뷰 많은 순(인기순)으로 정렬
        url = f"https://store.steampowered.com/search/?sort_by=Reviews_DESC&category1=998&deck_compatibility={category_code}&l=koreana&cc=kr&start={start_count}"
        
        print(f"📡 검색 중: {status_name} (페이지 {page+1})...")
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                print(f"⛔ 차단됨 또는 오류 ({status_name}): {response.status_code}")
                break # 오류나면 이 카테고리는 중단
            
            soup = BeautifulSoup(response.text, "html.parser")
            rows = soup.select("#search_resultsRows > a")
            
            if not rows:
                break # 더 이상 게임이 없으면 중단

            for row in rows:
                try:
                    raw_appid = row.get('data-ds-appid')
                    if not raw_appid: continue
                    appid = raw_appid.split(',')[0]
                    
                    title = row.select_one(".title").text.strip()
                    link = row.get('href', '')
                    
                    # 이미지 추출
                    img_url = ""
                    img_tag = row.select_one(".search_capsule img")
                    if img_tag:
                        img_url = img_tag.get('src')
                        srcset = img_tag.get('srcset')
                        if srcset:
                            img_url = srcset.split(',')[0].split(' ')[0]
                    
                    if not img_url:
                        img_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"
                    
                    # 리뷰 수 파싱 (인기 척도)
                    review_count = 0
                    review_sentiment = "평가 없음"
                    review_summary = row.select_one(".search_review_summary")
                    
                    if review_summary:
                        raw_tooltip = review_summary.get('data-tooltip-html', '')
                        parts = raw_tooltip.split('<br>')
                        if parts:
                            review_sentiment = parts[0].strip()
                        
                        import re
                        match = re.search(r'([0-9,]+)개', raw_tooltip)
                        if match:
                            review_count = int(match.group(1).replace(',', ''))
                    
                    price_text = "가격 정보 없음"
                    price_el = row.select_one(".discount_final_price") or row.select_one(".search_price")
                    if price_el:
                        price_text = price_el.text.strip()

                    # 일정 리뷰 수 이상인 '인기 게임'만 수집
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
                except Exception:
                    continue
            
            # 스팀 서버 부하 방지를 위해 페이지 넘길 때 잠깐 쉬기
            time.sleep(random.uniform(1.0, 2.0))
            
        except Exception as e:
            print(f"에러 발생 ({status_name}): {e}")
            break
            
    return games

def send_discord_alert(game, is_update=False, old_status=None):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    kr_status = STATUS_KOREAN.get(game['status'], game['status'])
    
    # 색상 및 아이콘 설정
    if game['status'] == "Verified":
        color = '00ff00' # 초록
    elif game['status'] == "Playable":
        color = 'ffff00' # 노랑
    elif game['status'] == "Unsupported":
        color = 'ff0000' # 빨강
    else:
        color = 'cccccc' # 회색 (Unknown)

    info_block = (
        f"**가격:** {game['price']}\n"
        f"**평가:** {game['sentiment']} ({format(game['reviews'], ',')}개)\n"
        f"[스팀 상점 페이지 바로가기]({game['link']})"
    )

    if is_update:
        kr_old = STATUS_KOREAN.get(old_status, old_status)
        title = f"🔄 스팀덱 상태 변경: {game['title']}"
        desc = f"**{kr_old}** ➔ **{kr_status}**\n\n{info_block}"
    else:
        title = f"📢 스팀덱 현황 알림: {game['title']}"
        desc = f"현재 상태: **{kr_status}**\n\n{info_block}"

    embed = DiscordEmbed(title=title, description=desc, color=color)
    if game.get('img'):
        embed.set_image(url=game['img'])

    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("🚀 스팀덱 인기 게임 스캔 시작 (4등급 분류)...")
    history = load_history()
    
    # 4가지 카테고리 모두 스캔 (0: Unknown, 1: Unsupported, 2: Playable, 3: Verified)
    # 인기순(Reviews_DESC)으로 정렬된 리스트를 가져옵니다.
    target_categories = [
        ("Verified", 3),
        ("Playable", 2),
        ("Unsupported", 1),
        ("Unknown", 0) # [추가됨] 알 수 없음 상태도 체크
    ]
    
    all_fetched_games = []
    
    for status_name, code in target_categories:
        games = fetch_games_by_status(status_name, code)
        all_fetched_games.extend(games)
        time.sleep(1) # 카테고리 변경 시 딜레이
    
    # 중복 제거 (한 게임이 여러 상태에 잡힐 일은 드물지만 안전장치)
    unique_games = {g['id']: g for g in all_fetched_games}
    
    msg_count = 0
    print(f"🔍 총 {len(unique_games)}개의 인기 게임 분석 중...")
    
    for game in unique_games.values():
        appid = game['id']
        current_status = game['status']
        
        # 1. 아예 처음 발견된 게임 (기록에 없음)
        if appid not in history:
            # 너무 많은 알림 방지: Unknown(미정) 상태인 게임은 '최초 발견' 알림을 굳이 안 보내고 기록만 함
            # (Verified나 Playable, Unsupported로 확정된 것만 알림)
            if current_status != "Unknown": 
                print(f"✨ 신규 등록: {game['title']} ({current_status})")
                send_discord_alert(game, is_update=False)
                msg_count += 1
                time.sleep(1)
            history[appid] = current_status
            
        # 2. 기록은 있는데 상태가 바뀐 게임 (핵심!)
        elif history[appid] != current_status:
            old_status = history[appid]
            print(f"🔄 상태 변경: {game['title']} ({old_status} -> {current_status})")
            send_discord_alert(game, is_update=True, old_status=old_status)
            history[appid] = current_status
            msg_count += 1
            time.sleep(1)
            
    if msg_count > 0:
        save_history(history)
        print("✅ 업데이트 완료.")
    else:
        print("💤 변경된 사항이 없습니다.")

if __name__ == "__main__":
    run()
