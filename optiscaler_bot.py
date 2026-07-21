import requests
import json
import os
import time
import re
import urllib.parse
from bs4 import BeautifulSoup
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
                
                if "GAME NAME" in raw_game.upper() or "Game" in raw_game:
                    continue
                if not raw_game or all(c in '-:' for c in raw_game):
                    continue
                
                # 🌟 Images 열(6번째 기둥)에서 이미지 링크 추출
                table_image = ""
                if len(cols) >= 6:
                    img_match = re.search(r'\[.*?\]\((.*?)\)', cols[5])
                    if img_match:
                        table_image = img_match.group(1).strip()
                
                match = re.search(r'\[(.*?)\]\((.*?)\)', raw_game)
                if match:
                    game_name = match.group(1).replace('*', '').strip()
                    detail_link = match.group(2).strip()
                else:
                    game_name = raw_game.replace('*', '').strip()
                    detail_link = None
                
                games[game_name] = {
                    "name": game_name,
                    "status": status,
                    "native_api": native_api,
                    "anti_cheat": anti_cheat,
                    "detail_link": detail_link,
                    "table_image": table_image # 딕셔너리에 추가
                }
        return games
    except Exception as e:
        print(f"메인 표 파싱 에러: {e}")
        return {}

def fetch_detail_page(link):
    """실제 깃허브 웹페이지에 접속하여 BeautifulSoup으로 테이블과 노트를 파싱합니다."""
    if not link: return {"image": "", "notes": "", "dll": "", "upscaler_input": "", "fg_input": ""}
    
    if "github.com/" in link:
        page_path = link.split('/wiki/')[-1]
    else:
        page_path = link
        
    page_path = page_path.split('#')[0].strip()
    page_path = urllib.parse.quote(page_path)
    
    # 🌟 마크다운 원본 대신, 사용자가 보는 "진짜 HTML 주소"로 바로 접속합니다.
    url = f"https://github.com/optiscaler/OptiScaler/wiki/{page_path}"
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200: 
            return {"image": "", "notes": f"⚠️ 상세 페이지 데이터 로드 실패 (HTTP {res.status_code})\n요청 URL: {url}", "dll": "", "upscaler_input": "", "fg_input": ""}
            
        soup = BeautifulSoup(res.text, 'html.parser')
        body = soup.find('div', class_='markdown-body')
        
        extracted_dll = ""
        upscaler_input = ""
        fg_input = ""
        notes_lines = []
        
        if body:
            # 1. 화면에 보이는 표(Table)를 긁어서 세팅값 추출
            for table in body.find_all('table'):
                for row in table.find_all('tr'):
                    cols = row.find_all(['th', 'td'])
                    if len(cols) >= 2:
                        key = cols[0].get_text(strip=True).lower()
                        val = cols[1].get_text(separator=" ", strip=True)
                        
                        if 'filename' in key:
                            extracted_dll = val
                        elif 'upscaler input' in key:
                            upscaler_input = val
                        elif 'fg input' in key:
                            fg_input = val
                            
            # 2. 표 아래에 적힌 문단(p)과 리스트(li) 내용만 깔끔하게 노트로 취합
            for child in body.children:
                if child.name == 'p':
                    text = child.get_text(separator=" ", strip=True)
                    if text: notes_lines.append(text)
                elif child.name == 'ul':
                    for li in child.find_all('li', recursive=False):
                        text = li.get_text(separator=" ", strip=True)
                        if text: notes_lines.append(f"- {text}")
                        
        clean_text = "\n".join(notes_lines).strip()
        if len(clean_text) > 400:
            clean_text = clean_text[:400] + "...\n(상세 페이지 참조)"
            
        return {
            "image": "", 
            "notes": clean_text, 
            "dll": extracted_dll,
            "upscaler_input": upscaler_input,
            "fg_input": fg_input
        }
    except Exception as e:
        return {"image": "", "notes": f"⚠️ 파싱 에러 발생: {e}", "dll": "", "upscaler_input": "", "fg_input": ""}

def send_discord_alert(game, old_game=None, is_update=False):
    # 🌟 1. 업데이트인 경우, 기존에 보냈던 옛날 메시지를 조용히 삭제합니다.
    if is_update and old_game and old_game.get('message_id'):
        old_msg_id = old_game['message_id']
        try:
            requests.delete(f"{WEBHOOK_URL}/messages/{old_msg_id}", timeout=10)
        except Exception as e:
            print(f"기존 메시지 삭제 실패: {e}")

    # URL에 wait=true 파라미터가 있어야 발송 후 메시지 ID를 응답받을 수 있습니다.
    post_url = WEBHOOK_URL
    if "wait=true" not in post_url.lower():
        post_url += "&wait=true" if "?" in post_url else "?wait=true"
        
    webhook = DiscordWebhook(url=post_url)
    
    status_raw = game['status']
    
    if 'working' in status_raw.lower() or '✔' in status_raw or '✅' in status_raw:
        icon = "🟢"
        color = '00FF00'
        ko_status = "완벽 작동"
    elif 'issue' in status_raw.lower() or '⚠' in status_raw or '⚠️' in status_raw:
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
    
    extracted_dll = game.get('dll', '')
    if extracted_dll:
        target_dll = extracted_dll
    else:
        if icon == "🟢":
            target_dll = "(예상) dxgi.dll 또는 winmm.dll"
        else:
            target_dll = "정보 없음"

    up_input = game.get('upscaler_input', '')
    fg_input = game.get('fg_input', '')
    
    if not up_input:
        up_input = native_api_text 
        
    if up_input:
        up_text = f"**🎮 업스케일링 인풋:** `{up_input}`"
    else:
        up_text = "**🎮 업스케일링 인풋:** 정보 없음"
        
    if fg_input:
        fg_text = f"**🚀 프레임 생성(FG) 인풋:** `{fg_input}`"
    else:
        fg_text = "**🚀 프레임 생성(FG) 인풋:** 미지원 / 정보 없음"
        
    native_api_text += mark_api
    
    ko_notes = str(translate_ko(game.get('notes', '')))
    notes_block = f"\n\n**📝 세부 설정 및 이슈**{mark_notes}\n{ko_notes}" if ko_notes else ""
    
    detail_url = f"https://github.com/optiscaler/OptiScaler/wiki/{game['detail_link']}" if game['detail_link'] else "상세 페이지 없음"
    
    table_img = game.get('table_image', '')
    final_img = ""
    image_notice = ""

    if table_img:
        final_img = f"https://github.com{table_img}" if table_img.startswith('/') else table_img
    elif game.get('image'):
        final_img = game['image']

    if final_img:
        image_notice = "\n\n**🖼️ 적용 스크린샷** (아래 이미지를 클릭하면 확대됩니다)"

    desc = (
        f"**호환성 상태:** {icon} **{ko_status}**\n"
        f"**안티치트:** {ko_anti_cheat}\n\n"
        f"**⚙️ 덮어쓸 DLL 이름:** `{target_dll}`\n"
        f"{up_text}\n"
        f"{fg_text}\n"
        f"(원본 지원 API: {native_api_text})"
        f"{notes_block}"
        f"{image_notice}\n\n"
        f"**💡 팁:** 번역된 내용이나 예상 설정으로 적용 시 문제가 발생하거나, `nvngx.ini` 세부 설정이 필요하다면 아래 원문 페이지를 확인해 주세요.\n"
        f"[👉 OptiScaler 깃허브 상세 페이지(영문) 바로가기]({detail_url})"
    )

    embed = DiscordEmbed(title=title, description=desc, color=color)
    
    if final_img:
        embed.set_image(url=final_img)
        
    embed.set_footer(text="데이터 제공 (Developed & Maintained by): OptiScaler Team")
    
    webhook.add_embed(embed)
    response = webhook.execute()

    # 🌟 2. 새로 발송된 메시지의 고유 ID를 가져와서 반환합니다.
    new_message_id = None
    try:
        if response.status_code in [200, 201]:
            resp_json = response.json()
            if isinstance(resp_json, list):
                new_message_id = resp_json[0].get('id')
            else:
                new_message_id = resp_json.get('id')
    except Exception as e:
        print(f"메시지 ID 추출 실패: {e}")

    return new_message_id

def run():
    print("옵티스케일러 봇 [단일 항목 테스트 모드] 실행 중...")
    history = load_history()
    all_games = parse_main_table()
    
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
        data['dll'] = details['dll']
        data['upscaler_input'] = details['upscaler_input']
        data['fg_input'] = details['fg_input']
        
        # 🌟 3. 알림을 보낸 뒤 반환받은 메시지 ID를 JSON 데이터에 기록합니다.
        new_msg_id = send_discord_alert(data, old_game=old_data, is_update=bool(old_data))
        if new_msg_id:
            data['message_id'] = new_msg_id
        elif old_data and old_data.get('message_id'):
            # 혹시라도 발급에 실패하면 예전 ID라도 유지
            data['message_id'] = old_data['message_id']
            
        history[name] = data
        msg_count += 1
        time.sleep(2) 
            
    if msg_count > 0:
        save_history(history)
        print("테스트 전송 및 저장 완료.")

if __name__ == "__main__":
    run()