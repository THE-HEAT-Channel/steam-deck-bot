import requests
import json
import os
import time
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 =================
WEBHOOK_URL = "https://discord.com/api/webhooks/1464325575505215499/MRwIZuOSNWzHqtZAeKVnKTa9GsgReAq3q7PSKejoq9J2uE2GHvgqjX9qZ6rP911e_-7n"
MIN_REVIEWS = 50  # 리뷰 50개 이상 (다운로드 수 필터링용)
HISTORY_FILE = "sent_games.json"
# =======================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False)

def get_new_verified_games():
    # 스팀 검색: 'Deck Verified(3)' 정렬: '출시일(Released_DESC)'
    url = "https://store.steampowered.com/search/?sort_by=Released_DESC&category1=998&deck_compatibility=3"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    
    games = []
    # 검색 결과 상위 25개만 확인 (하루 2번 체크하므로 충분)
    rows = soup.select("#search_resultsRows > a")
    
    for row in rows:
        try:
            appid = row['data-ds-appid']
            title = row.select_one(".title").text.strip()
            link = row['href']
            
            # 리뷰 수 체크 (검색 페이지 HTML 파싱)
            review_summary = row.select_one(".search_review_summary")
            review_count = 0
            if review_summary:
                # 툴팁 데이터에서 숫자 추출 (예: "35 User Reviews")
                raw_reviews = review_summary.get('data-tooltip-html', '')
                review_count = int(''.join(filter(str.isdigit, raw_reviews.split('<br>')[0])))
            
            # 조건: 리뷰 수가 설정값 이상인 경우만
            if review_count >= MIN_REVIEWS:
                games.append({
                    "id": appid,
                    "title": title,
                    "link": link,
                    "reviews": review_count
                })
        except Exception:
            continue
            
    return games

def run():
    history = load_history()
    new_games = get_new_verified_games()
    updated_history = history[:]
    
    # 알림 보낼 게임 찾기
    for game in new_games:
        if game['id'] not in history:
            print(f"New Game Found: {game['title']}")
            
            # 디스코드 전송
            webhook = DiscordWebhook(url=WEBHOOK_URL)
            embed = DiscordEmbed(title=f"🟢 스팀덱 호환 완료: {game['title']}", 
                                 description=f"리뷰 수: {game['reviews']}개\n[스팀 페이지 바로가기]({game['link']})", 
                                 color='00ff00')
            webhook.add_embed(embed)
            webhook.execute()
            
            updated_history.append(game['id'])
            time.sleep(1) # 도배 방지
            
    # 최신 500개만 기억 (파일 용량 관리)
    if len(updated_history) > 500:
        updated_history = updated_history[-500:]
        
    save_history(updated_history)

if __name__ == "__main__":
    run()
