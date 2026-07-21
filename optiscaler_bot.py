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
    """NoneType 에러를 방지하고 영어 원문을 한글로 안전하게 번역합니다."""
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
    """마크다운 원본에서 기호나 빈칸을 스킵하고 순수 게임 정보만 추출합니다."""
    url = f"{BASE_WIKI_URL}/Compatibility-List.md"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200: return {}
        
        lines = res.text.split('\n')
        games = {}
        
        for line in lines:
            if not line.strip().startswith('|'):
                continue
            if re.search(r'\|[-:\s]+\|[-:\s]+\|', line):
                continue
                
            cols = [c.strip() for c in line.split('|')][1:-1]
            if len(cols) >= 4:
                raw_game = cols[0]
                status = cols[1]
                native_api = cols[2]
                anti_cheat = cols[3]
                
                if "GAME NAME" in raw_game.upper() or "✔" in status or "Game" in raw_game:
                    continue
                if not raw_game or all(c in '-:' for c in raw_game):
                    continue
                
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
    """상세 페이지에 접속해 이미지, 노트, 그리고 DLL(dxgi/winmm) 정보를 추출합니다."""
    if not link: return {"image": "", "notes": "", "dll": ""}
    
    url = f"{BASE_WIKI_URL}/{link}.md"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200: return {"image": "", "notes": "", "dll": ""}
        
        text = res.text
        image_url = ""
        img_match = re.search(r'!\[.*?\]\((.*?)\)', text)
        if img_match:
            image_url = img_match.group(1)
            
        # 상세 페이지 내용 중 DLL 파일명 스캔
        found_dlls = []
        if re.search(r'\bdxgi(?:\.dll)?\b', text, re.IGNORECASE):
            found_dlls.append("dxgi.dll")
        if re.search(r'\bwinmm(?:\.dll)?\b', text, re.IGNORECASE):
            found_dlls.append("winmm.dll")
            
        dll_text = " 또는 ".join(found_dlls)
            
        clean_text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
        clean_text = clean_text.replace('#', '').strip()
        
        if len(clean_text) > 400:
            clean_text = clean_text[:400] + "...\n(상세 페이지 참조)"
            
        return {"image": image_url, "notes": clean_text, "dll": dll_text}
    except:
        return {"image": "", "notes": "", "dll": ""}

def send_discord_alert(game, old_game=None, is_update=False):
    """디스코드 알림을 포맷팅하여 전송합니다. (인게임 설정 예상 로직 포함)"""
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    
    status_raw = game['status']
    
    if 'working' in status_raw.lower() or '✔' in status_raw:
        icon = "🟢"
        color = '00FF00'
        ko_status = "완벽 작동"
    elif 'issue' in status_raw.lower() or '⚠' in status_raw:
        icon = "🟡"
        color = 'FFA500' 
        ko_status = "이슈 있음 (설정 필요)"
    else:
        icon = "🔴"
        color = 'FF0000'
        ko_status = "작동 불가"

    title_prefix = "🔄 상태 업데이트" if is_update else "✨ 신규 추가"
    title = f"{title_prefix}: {game['name']}"
    
    mark_status = mark_api = mark_cheat = mark_notes = ""
    if is_update and old_game:
        if game['status'] != old_game.get('status'): mark_status = " 🔄"
        if game['native_api'] != old_game.get('native_api'): mark_api = " 🔄"
        if game['anti_cheat'] != old_game.get('anti_cheat'): mark_cheat = " 🔄"
        if game.get('notes') != old_game.get('notes'): mark_notes = " 🔄"

    ko_status += mark_status
    
    ko_anti_cheat = game['anti_cheat'].strip()
    if not ko_anti_cheat or ko_anti_cheat.lower() in ['none', 'n/a']:
        ko_anti_cheat = "없음 (싱글플레이)" + mark_cheat
    else:
        ko_anti_cheat = str(translate_ko(ko_anti_cheat)) + mark_cheat
        
    native_api_text = str(game.get('native_api', ''))
    
    # 상세 페이지 기반 DLL 예상 추론 로직
    extracted_dll = game.get('dll', '')
    if extracted_dll:
        target_dll = extracted_dll
    else:
        if 'working' in status_raw.lower() or '✔' in status_raw:
            target_dll = "(예상) dxgi.dll 또는 winmm.dll"
        else:
            target_dll = "정보 없음"
            
    # 인게임 설정 예상 로직
    if "DLSS" in native_api_text.upper():
        in_game_setting = "DLSS 켜기"
    elif "FSR" in native_api_text.upper():
        in_game_setting = "FSR 켜기"
    elif "XESS" in native_api_text.upper():
        in_game_setting = "XeSS 켜기"
    else:
        in_game_setting = f"{native_api_text} 켜기"
        
    native_api_text += mark_api
    ko_notes = str(translate_ko(game.get('notes', '')))
    
    notes_block = f"\n\n**📝 세부 설정 및 이슈 (클릭해서 보기)**{mark_notes}\n||{ko_notes}||" if ko_notes else ""
    detail_url = f"https://github.com/optiscaler/OptiScaler/wiki/{game['detail_link']}" if game['detail_link'] else "상세 페이지 없음"
    
    desc = (
        f"**호환성 상태:** {icon} **{ko_status}**\n"
        f"**안티치트:** {ko_anti_cheat}\n\n"
        f"**⚙️ 덮어쓸 DLL 이름:** `{target_dll}`\n"
        f"**🎮 게임 내 옵션 선택:** **{in_game_setting}**\n"
        f"(원본 지원 API: {native_api_text})"
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
    
    # 테스트를 위해 첫 번째 게임 하나만 추출
    if not all_games:
        print("게임을 불러오지 못했습니다.")
        return
        
    first_game_name = list(all_games.keys())[0]
    first_game_data = all_games[first_game_name]
    
    current_games = {first_game_name: first_game_data}
    
    msg_count = 0
    for name, data in current_games.items():
        old_data = history.get(name)
        
        print(f"테스트 전송 중: {name}")
        details = fetch_detail_page(data['detail_link'])
        data['image'] = details['image']
        data['notes'] = details['notes']
        data['dll'] = details['dll'] # DLL 정보 저장 추가
        
        send_discord_alert(data, old_game=old_data, is_update=bool(old_data))
        history[name] = data
        msg_count += 1
        time.sleep(2) 
            
    if msg_count > 0:
        save_history(history)
        print("테스트 전송 및 저장 완료.")

if __name__ == "__main__":
    run()