import requests
import json
import os
import time
import re
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 (SETTINGS) =================
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK')

if not WEBHOOK_URL:
    print("⚠️ 오류: 웹훅 URL을 찾을 수 없습니다. Secrets 설정(DISCORD_WEBHOOK)을 확인하세요.")
    exit()

MIN_REVIEWS = 100  # 인기 게임 기준
HISTORY_FILE = "sent_games.json"

STATUS_INFO = {
    "Verified": {"text": "완벽 호환", "icon": "🟢", "color": "00FF00"},
    "Playable": {"text": "플레이 가능", "icon": "🟡", "color": "FFFF00"},
    "Unsupported": {"text": "지원 안 됨", "icon": "🔴", "color": "FF0000"},
    "Unknown": {"text": "알 수 없음", "icon": "❓", "color": "CCCCCC"}
}

PAGES_TO_SCAN = 2 
# ==================================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding='utf-8') as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False)

def fetch_top_games():
    """스팀 검색 페이지에서 최상위 인기 게임 리스트를 가져옵니다."""
    games = []
    for page in range(PAGES_TO_SCAN):
        start_count = page * 50
        url = f"https://store.steampowered.com/search/?sort_by=Reviews_DESC&category1=998&l=koreana&cc=kr&start={start_count}"
        
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
                    
                    review_count = 0
                    review_sentiment = "평가 없음"
                    review_summary = row.select_one(".search_review_summary")
                    if review_summary:
                        raw_tooltip = review_summary.get('data-tooltip-html', '')
                        parts = raw_tooltip.split('<br>')
                        if parts: review_sentiment = parts[0].strip()
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
                            "img": img_url
                        })
                except: continue
            time.sleep(1)
        except: break
    return games

def fetch_compatibilities_for_game(appid):
    """
    HTML 파싱을 완전히 배제하고, 스팀 내부 비공개 JSON API와 공식 API를 조합하여
    기기별 호환성 데이터를 안전하게 수집합니다. (연령 제한 우회 및 UI 변경 면역)
    """
    deck_status = "Unknown"
    machine_status = "Unknown"
    os_status = "Unknown"

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    # 1. Steam Deck 호환성 (내부 비공개 AJAX API)
    try:
        deck_url = f"https://store.steampowered.com/saleaction/ajaxgetdeckappcompatibilityreport?nAppID={appid}"
        res = requests.get(deck_url, headers=headers, timeout=5).json()
        
        if res and res.get("success") == 1:
            category = res.get("results", {}).get("resolved_category")
            if category == 3: deck_status = "Verified"
            elif category == 2: deck_status = "Playable"
            elif category == 1: deck_status = "Unsupported"
    except:
        pass

    # 2. SteamOS 및 Steam Machine 호환성 (공식 AppDetails API)
    try:
        app_url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=koreana&cc=kr"
        res = requests.get(app_url, headers=headers, timeout=5).json()
        
        if res and str(appid) in res and res[str(appid)].get("success"):
            data = res[str(appid)]["data"]
            platforms = data.get("platforms", {})
            
            # 리눅스/SteamOS 네이티브 지원 여부 확인
            is_linux_native = platforms.get("linux", False)
            
            if is_linux_native:
                os_status = "Verified" if deck_status == "Verified" else "Playable"
                machine_status = "Playable"
            else:
                # 네이티브는 아니지만 스팀덱(Proton 호환 계층)으로 구동되는 경우
                if deck_status == "Verified":
                    os_status = "Playable"
                    machine_status = "Unknown"
                elif deck_status == "Unsupported":
                    os_status = "Unsupported"
                    machine_status = "Unsupported"
    except:
        pass

    return {"deck": deck_status, "machine": machine_status, "os": os_status}

def send_discord_alert(game, new_status, is_update=False):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    deck_info = STATUS_INFO.get(new_status['deck'], STATUS_INFO["Unknown"])
    machine_info = STATUS_INFO.get(new_status['machine'], STATUS_INFO["Unknown"])
    os_info = STATUS_INFO.get(new_status['os'], STATUS_INFO["Unknown"])
    
    status_block = (
        f"🎮 **Steam Deck:** {deck_info['icon']} {deck_info['text']}\n"
        f"🖥️ **Steam Machine:** {machine_info['icon']} {machine_info['text']}\n"
        f"🐧 **SteamOS:** {os_info['icon']} {os_info['text']}"
    )
    
    info_block = (
        f"**가격:** {game['price']}\n"
        f"**평가:** {game['sentiment']} ({format(game['reviews'], ',')}개)\n"
        f"[스팀 상점 페이지 바로가기]({game['link']})"
    )

    if is_update:
        title = f"🔄 호환성 업데이트: {game['title']}"
        desc = f"{status_block}\n\n{info_block}"
        color = deck_info['color']
    else:
        title = f"{deck_info['icon']} 스팀 기기 호환성: {game['title']}"
        desc = f"{status_block}\n\n{info_block}"
        color = deck_info['color']

    embed = DiscordEmbed(title=title, description=desc, color=color)
    if game.get('img'):
        embed.set_image(url=game['img'])

    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("스팀 호환성 갱신 중 (JSON API 통신 방식)...")
    history = load_history()
    top_games = fetch_top_games()
    
    unique_games = {g['id']: g for g in top_games}
    
    # [1. 기존 구버전 데이터 강제 업데이트 로직]
    old_appids = [appid for appid, status in history.items() if isinstance(status, str)]
    for appid in old_appids:
        if appid not in unique_games:
            try:
                res = requests.get(f"https://store.steampowered.com/api/appdetails?appids={appid}&l=koreana&cc=kr", timeout=5).json()
                if res and str(appid) in res and res[str(appid)]['success']:
                    data = res[str(appid)]['data']
                    if data['type'] == 'game':
                        price = "무료"
                        if not data.get('is_free') and 'price_overview' in data:
                            price = data['price_overview']['final_formatted']
                        unique_games[appid] = {
                            "id": str(appid),
                            "title": data['name'],
                            "link": f"https://store.steampowered.com/app/{appid}/",
                            "reviews": 0,
                            "sentiment": "기존 데이터 갱신",
                            "price": price,
                            "img": data.get('header_image', '')
                        }
            except Exception as e:
                pass
            time.sleep(0.5) 

    # [2. 이름 기반 중복 에디션/DLC 방지 로직]
    sorted_games = sorted(unique_games.values(), key=lambda x: len(x['title']))
    processed_base_titles = set()
    
    msg_count = 0
    
    for game in sorted_games:
        appid = game['id']
        
        base_title = game['title'].split(':')[0].split('-')[0].strip().lower()
        if base_title in processed_base_titles:
            continue
            
        old_status = history.get(appid)
        
        # 순수 JSON API로 통신하여 호환성 데이터 추출
        current_status = fetch_compatibilities_for_game(appid)
        
        processed_base_titles.add(base_title)
        
        if not old_status:
            if current_status['deck'] != "Unknown" or current_status['machine'] != "Unknown":
                print(f"✨ 신규: {game['title']}")
                send_discord_alert(game, current_status, is_update=False)
                history[appid] = current_status
                msg_count += 1
                time.sleep(1)
            else:
                history[appid] = current_status
                
        elif isinstance(old_status, str) or old_status != current_status:
            
            # JSON API가 3가지 항목 모두 Unknown을 반환하는 경우는 실제 데이터가 없는 경우입니다.
            if current_status['deck'] == "Unknown" and current_status['machine'] == "Unknown" and current_status['os'] == "Unknown":
                continue
                
            print(f"🔄 업데이트 됨: {game['title']}")
            send_discord_alert(game, current_status, is_update=True)
            history[appid] = current_status
            msg_count += 1
            time.sleep(1)
            
    if msg_count > 0:
        save_history(history)
        print("모든 데이터 저장 완료.")
    else:
        print("새로 변경된 항목 없음.")

if __name__ == "__main__":
    run()