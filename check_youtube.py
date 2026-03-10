import requests
import json
import os
import xml.etree.ElementTree as ET
from discord_webhook import DiscordWebhook, DiscordEmbed

# ================= 설정 =================
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_NEWVIDEO')
YOUTUBE_CHANNEL_ID = "UCcJeDBJiD3SlIvnKEplxX-Q" 
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
    print(f"📡 접속 시도 중: {url}")  
    
    try:
        response = requests.get(url, timeout=10)
        print(f"응답 코드: {response.status_code}") 
        
        if response.status_code != 200:
            print(f"❌ 접속 실패! 원인: {response.text[:100]}") 
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

def is_short(video_id):
    """
    유튜브 URL 리다이렉트 특성을 이용해 쇼츠 영상인지 판별합니다.
    """
    url = f"https://www.youtube.com/shorts/{video_id}"
    try:
        # 봇 차단을 방지하기 위해 User-Agent 추가 및 리다이렉트 추적 방지
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.head(url, headers=headers, allow_redirects=False, timeout=5)
        
        # 상태 코드가 200이면 쇼츠, 303 등 다른 코드면 일반 영상으로 리다이렉트됨
        return response.status_code == 200
    except Exception as e:
        print(f"⚠️ 쇼츠 확인 중 에러 발생: {e}")
        return False

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
            
            # 쇼츠 여부를 검사합니다.
            if is_short(video['id']):
                print("🚫 이 영상은 쇼츠(Shorts)이므로 알림을 건너뜁니다.")
            else:
                print("새 일반 영상입니다! 알림 전송...")
                send_discord_alert(video)
            
            # 히스토리 배열에 새 영상 ID를 추가합니다.
            history.append(video['id'])
            
            # 기록이 너무 길어지지 않도록 최신 50개만 남기고 자릅니다.
            if len(history) > 50:
                history = history[-50:] 
                
            # 업데이트된 배열을 파일에 저장합니다.
            save_history(history)
            
        else:
            print("이미 처리된 영상입니다.")
    else:
        print("결국 피드를 가져오지 못했습니다.")

if __name__ == "__main__":
    run()
