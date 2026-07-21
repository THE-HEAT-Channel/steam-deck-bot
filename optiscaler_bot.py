import requests
import json
import os
import time
import re
from discord_webhook import DiscordWebhook, DiscordEmbed
from deep_translator import GoogleTranslator

# ================= 설정 =================
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_OPTISCALER')

if not WEBHOOK_URL:
    print("⚠️ 오류: 옵티스케일러 알림용 웹훅 URL이 없습니다.")
    exit()

HISTORY_FILE = "optiscaler_games.json"
BASE_WIKI_URL = "https://raw.githubusercontent.com/wiki/optiscaler/OptiScaler"
# =======================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding='utf-8') as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False)

def translate_ko(text):
    if not text:
        return ""
    
    text_str = str(text)
    if len(text_str) < 2 or text_str.lower() in ["none", "n/a"]:
        return text_str
        
    try:
        translator = GoogleTranslator(source='en', target='ko')
        result = translator.translate(text_str)
        return str(result) if result else text_str
    except:
        return text_str

def parse_main_table():
    url = f"{BASE_WIKI_URL}/Compatibility-List.md"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200: return []
        
        lines = res.text.split('\n')
        games = {}
        
        for line in lines:
            if not line.startswith('|') or '---|' in line or 'Game' in line:
                continue
                
            cols = [c.strip() for c in line.split('|')][1:-1]
            if len(cols) >= 4:
                raw_game = cols[0]
                status = cols[1]
                native_api = cols[2]
                anti_cheat = cols[3]
                
                match = re.search(r'\[(.*?)\]\((.*?)\)', raw_game)
                if match:
                    game_name = match.group(1)
                    detail_link = match.group(2)
                else:
                    game_name = raw_game.replace('*', '').strip()
                    detail_link = None
                
                games[game_name] = {
                    "name": game_name,
                    "status": status,
                    "native_api": native_api,
                    "anti_cheat": anti_cheat,
                    "detail_link": detail_link
                }
        return games
    except Exception as e:
        print(f"메인 표 파싱 에러: {e}")
        return {}

def fetch_detail_page(link):
    if not link: return {"image": "", "notes": ""}
    
    url = f"{BASE_WIKI_URL}/{link}.md"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200: return {"image": "", "notes": ""}
        
        text = res.text
        image_url = ""
        img_match = re.search(r'!\[.*?\]\((.*?)\)', text)
        if img_match:
            image_url = img_match.group(1)
            
        clean_text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
        clean_text = clean_text.replace('#', '').strip()
        
        if len(clean_text) > 400:
            clean_text = clean_text[:400] + "...\n(상세 페이지 참조)"
            
        return {"image": image_url, "notes": clean_text}
    except:
        return {"image": "", "notes": ""}

def send_discord_alert(game, old_game=None, is_update=False):
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    status_lower = game['status'].lower()
    if 'working' in status_lower and 'not' not in status_lower:
        icon = "🟢"
        color = '00FF00'
    elif 'issue' in status_lower:
        icon = "🟡"
        color = 'FFA500' 
    else:
        icon = "🔴"
        color = 'FF0000'

    title_prefix = "🔄 상태 업데이트" if is_update else "✨ 신규 추가"
    title = f"{title_prefix}: {game['name']}"
    
    # 🌟 업데이트 된 항목 찾아서 마크 표시 로직
    mark_status = mark_api = mark_cheat = mark_notes = ""
    if is_update and old_game:
        if game['status'] != old_game.get('status'): mark_status = " 🔄(업데이트 됨)"
        if game['native_api'] != old_game.get('native_api'): mark_api = " 🔄(업데이트 됨)"
        if game['anti_cheat'] != old_game.get('anti_cheat'): mark_cheat = " 🔄(업데이트 됨)"
        if game.get('notes') != old_game.get('notes'): mark_notes = " 🔄(노트 내용 업데이트 됨)"

    ko_status = str(translate_ko(game.get('status', ''))) + mark_status
    ko_anti_cheat = str(translate_ko(game.get('anti_cheat', ''))) + mark_cheat
    native_api_text = str(game.get('native_api', '')) + mark_api
    ko_notes = str(translate_ko(game.get('notes', '')))
    
    notes_block = f"\n\n**📝 설정 노트 및 알려진 이슈 (클릭해서 보기)**{mark_notes}\n||{ko_notes}||" if ko_notes else ""
    detail_url = f"https://github.com/optiscaler/OptiScaler/wiki/{game['detail_link']}" if game['detail_link'] else "상세 페이지 없음"
    
    desc = (
        f"**상태:** {icon} {ko_status}\n"
        f"**기본 API:** {native_api_text}\n"
        f"**안티치트:** {ko_anti_cheat}"
        f"{notes_block}\n\n"
        f"[👉 OptiScaler 깃허브 상세 페이지 바로가기]({detail_url})"
    )

    embed = DiscordEmbed(title=title, description=desc, color=color)
    
    if game.get('image'):
        embed.set_image(url=game['image'])
        
    embed.set_footer(text="데이터 제공 (Developed & Maintained by): OptiScaler Team")
    
    webhook.add_embed(embed)
    webhook.execute()

def run():
    print("옵티스케일러 봇 [단일 항목 테스트 모드] 실행 중...")
    history = load_history()
    all_games = parse_main_table()
    
    # 🌟 첫 번째 게임만 추출하여 테스트 진행
    if not all_games:
        print("게임을 불러오지 못했습니다.")
        return
        
    first_game_name = list(all_games.keys())[0]
    first_game_data = all_games[first_game_name]
    
    current_games = {first_game_name: first_game_data}
    
    msg_count = 0
    for name, data in current_games.items():
        old_data = history.get(name)
        
        # 첫 번째 게임 무조건 알림 전송 (테스트 목적)
        print(f"테스트 전송 중: {name}")
        details = fetch_detail_page(data['detail_link'])
        data['image'] = details['image']
        data['notes'] = details['notes']
        
        send_discord_alert(data, old_game=old_data, is_update=bool(old_data))
        history[name] = data
        msg_count += 1
        time.sleep(2) 
            
    if msg_count > 0:
        save_history(history)
        print("테스트 전송 및 저장 완료.")

if __name__ == "__main__":
    run()