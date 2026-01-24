import requests
import json
import os
import time
import xml.etree.ElementTree as ET
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 =================
# [수정됨] 새로 정하신 변수 이름 적용
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_NEWVIDEO')

if not WEBHOOK_URL:
    print("⚠️ 오류: DISCORD_WEBHOOK_NEWVIDEO 시크릿이 설정되지 않았습니다.")
    exit()

YOUTUBE_CHANNEL_ID = "UCcJeDBJiD3SlIvnKEplxX-Q" 

HISTORY_FILE = "sent_videos.json"
# =======================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding='utf-8') as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False)

def fetch_latest_video():
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
            
        root = ET.fromstring(response.content)
        ns = {'yt': 'http://www.youtube.com/xml/schemas/2015', 'media': 'http://search.yahoo.com/mrss/', 'atom': 'http://www.w3.org/2005/Atom'}
        
        entry = root.find('atom:entry', ns)
        
        if entry:
            video_id = entry.find('yt:videoId', ns).text
            title = entry.find('atom:title', ns).text
            link = entry.find('atom:link', ns).attrib['href']
            author = entry.find('atom:author/atom:name', ns).text
            
            group = entry.find('media:group', ns)
            thumbnail = group.find('media:thumbnail', ns).attrib['url'] if group else ""

            return {
                "id": video_id,
                "title": title,
                "link": link,
                "author": author,
                "thumbnail": thumbnail
            }
            
    except Exception as e:
        print(f"에러: {e}")
        return None
    return None

def send_discord_alert(video):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    # 멘션 예시 (필요하면 주석 해제)
    # webhook.content = "@everyone 새 영상이 올라왔어요!"

    embed = DiscordEmbed(
        title=f"📺 {video['author']} 새 영상 업로드!",
        description=f"**{video['title']}**\n\n[보러 가기]({video['link']})",
        color='FF0000'
    )
    
    embed.set_image(url=video['thumbnail'])
    
    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("유튜브 감시 시작...")
    history = load_history()
    video = fetch_latest_video()
    
    if video:
        if video['id'] not in history:
            print(f"새 영상 발견: {video['title']}")
            send_discord_alert(video)
            save_history([video['id']])
        else:
            print("새로운 영상 없음.")
    else:
        print("피드를 가져올 수 없음.")

if __name__ == "__main__":
    run()
