import requests
import json
import os
import xml.etree.ElementTree as ET
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 =================
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_NEWVIDEO')
YOUTUBE_CHANNEL_ID = "UCcJeDBJiD3SlIvnKEplxX-Q"  # 따옴표 유지 필수!
HISTORY_FILE = "sent_videos.json"
# =======================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding='utf-8') as f:
            try: return json.load(f)
            except: return []
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False)

def fetch_latest_video():
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
    print(f"📡 접속 시도 중: {url}")  # [디버그] 접속하는 주소 출력
    
    try:
        response = requests.get(url, timeout=10)
        print(f"응답 코드: {response.status_code}") # [디버그] 결과 코드 출력 (200이 정상)
        
        if response.status_code != 200:
            print(f"❌ 접속 실패! 원인: {response.text[:100]}") # [디버그] 에러 내용 일부 출력
            return None
            
        root = ET.fromstring(response.content)
        ns = {'yt': 'http://www.youtube.com/xml/schemas/2015', 'media': 'http://search.yahoo.com/mrss/', 'atom': 'http://www.w3.org/2005/Atom'}
        entry = root.find('atom:entry', ns)
        
        if entry:
            return {
                "id": entry.find('yt:videoId', ns).text,
                "title": entry.find('atom:title', ns).text,
                "link": entry.find('atom:link', ns).attrib['href'],
                "author": entry.find('atom:author/atom:name', ns).text,
                "thumbnail": entry.find('media:group', ns).find('media:thumbnail', ns).attrib['url']
            }
    except Exception as e:
        print(f"❌ 치명적 에러: {e}")
        return None
    return None

def send_discord_alert(video):
    if not WEBHOOK_URL: return
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    embed = DiscordEmbed(
        title=f"📺 {video['author']} 새 영상!",
        description=f"**{video['title']}**\n[보기]({video['link']})",
        color='FF0000'
    )
    embed.set_image(url=video['thumbnail'])
    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("--- 유튜브 봇 디버그 모드 시작 ---")
    history = load_history()
    video = fetch_latest_video()
    
    if video:
        print(f"✅ 영상 가져오기 성공: {video['title']}")
        if video['id'] not in history:
            print("새 영상입니다! 알림 전송...")
            send_discord_alert(video)
            save_history([video['id']])
        else:
            print("이미 보낸 영상입니다.")
    else:
        print("결국 피드를 가져오지 못했습니다.")

if __name__ == "__main__":
    run()
