import requests
import json
import os
import time
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 =================
# 여기에 아까 복사한 디스코드 웹훅 주소를 그대로 넣으세요
WEBHOOK_URL = "https://discord.com/api/webhooks/1464325575505215499/MRwIZuOSNWzHqtZAeKVnKTa9GsgReAq3q7PSKejoq9J2uE2GHvgqjX9qZ6rP911e_-7n"

# 테스트를 위해 리뷰 수 제한을 0으로 낮춥니다
MIN_REVIEWS = 0 
HISTORY_FILE = "sent_games.json"
# =======================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False)

def get_new_verified_games():
    # 스팀 덱 호환성 필터 적용된 검색 페이지
    url = "https://store.steampowered.com/search/?sort_by=Released_DESC&category1=998&deck_compatibility=3"
    response = requests.get(url)
    
    # 봇 차단 방지용 헤더 (브라우저인 척 하기)
    if response.status_code != 200:
        print(f"Error: 스팀 접속 실패 (상태코드: {response.status_code})")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    games = []
    
    # 검색 결과 가져오기
    rows = soup.select("#search_resultsRows > a")
    print(f"🔍 검색된 게임 수: {len(rows)}개") # 로그 출력

    for row in rows:
        try:
            appid = row['data-ds-appid']
            title = row.select_one(".title").text.strip()
            link = row['href']
            
            # 리뷰 수 체크
            review_summary = row.select_one(".search_review_summary")
            review_count = 0
            if review_summary:
                raw_reviews = review_summary.get('data-tooltip-html', '')
                # 숫자만 추출
                nums = ''.join(filter(str.isdigit, raw_reviews.split('<br>')[0]))
                if nums:
                    review_count = int(nums)
            
            print(f" - 확인 중: {title} (리뷰: {review_count}개)") # 로그 출력

            if review_count >= MIN_REVIEWS:
                games.append({
                    "id": appid,
                    "title": title,
                    "link": link,
                    "reviews": review_count
                })
        except Exception as e:
            print(f"파싱 에러 발생: {e}")
            continue
            
    return games

def run():
    print("🤖 봇 실행 시작...")
    history = load_history()
    new_games = get_new_verified_games()
    updated_history = history[:]
    
    msg_count = 0
    for game in new_games:
        # 중복 체크 (이미 보낸 건지)
        if game['id'] not in history:
            print(f"🚀 전송 시도: {game['title']}")
            
            webhook = DiscordWebhook(url=WEBHOOK_URL)
            embed = DiscordEmbed(title=f"🟢 스팀덱 호환 확인: {game['title']}", 
                                 description=f"리뷰 수: {game['reviews']}개\n[스팀 페이지]({game['link']})", 
                                 color='00ff00')
            webhook.add_embed(embed)
            response = webhook.execute()
            
            if response.status_code == 200 or response.status_code == 204:
                print(" -> 전송 성공!")
                updated_history.append(game['id'])
                msg_count += 1
            else:
                print(f" -> 전송 실패 (코드: {response.status_code})")

            time.sleep(1) 
    
    if msg_count == 0:
        print("💤 새로 보낼 알림이 없습니다.")
    else:
        # 파일 저장
        save_history(updated_history)
        print("💾 기록 저장 완료.")

if __name__ == "__main__":
    run()
