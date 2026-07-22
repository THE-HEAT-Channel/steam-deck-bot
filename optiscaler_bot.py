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

def get_steam_korean_name(eng_name):
    search_term = eng_name.split('(')[0].strip()
    url = f"https://store.steampowered.com/api/storesearch/?term={urllib.parse.quote(search_term)}&l=korean&cc=kr"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data.get('total', 0) > 0:
                steam_name = data['items'][0].get('name', '')
                if re.search(r'[가-힣]', steam_name):
                    return steam_name
    except Exception as e:
        print(f"스팀 API 검색 에러: {e}")
    return None

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
                optipatcher = cols[3] 
                
                if "GAME NAME" in raw_game.upper() or "Game" in raw_game:
                    continue
                if not raw_game or all(c in '-:' for c in raw_game):
                    continue
                
                table_image = ""
                if len(cols) >= 6:
                    # 🌟 이미지 링크도 괄호 방어 적용
                    img_match = re.search(r'\[.*?\]\((.*?)\)(?!\))', cols[5])
                    if img_match:
                        table_image = img_match.group(1).strip()
                
                # 🌟 핵심 수정: 주소 내부에 괄호가 포함되어 있어도 마크다운의 '진짜 끝 괄호'를 정확히 찾아냅니다.
                match = re.search(r'\[(.*?)\]\((.*?)\)(?!\))', raw_game)
                if match:
                    game_name = match.group(1).replace('*', '').strip()
                    detail_link = match.group(2).strip()
                else:
                    game_link_match = re.search(r'href=["\'](.*?)["\']', raw_game)
                    if game_link_match:
                        detail_link = game_link_match.group(1).split('/')[-1]
                    else:
                        detail_link = None
                    game_name = raw_game.replace('*', '').strip()
                
                games[game_name] = {
                    "name": game_name,
                    "status": status,
                    "native_api": native_api,
                    "optipatcher": optipatcher,
                    "detail_link": detail_link,
                    "table_image": table_image
                }
        return games
    except Exception as e:
        print(f"메인 표 파싱 에러: {e}")
        return {}

def fetch_detail_page(link):
    if not link: 
        return {"success": True, "image": "", "notes": "", "dll": "", "upscaler_input": "", "fg_input": ""}
    
    if "github.com/" in link:
        page_path = link.split('/wiki/')[-1]
    else:
        page_path = link
        
    page_path = page_path.split('#')[0].strip()
    page_path = urllib.parse.quote(page_path)
    url = f"https://github.com/optiscaler/OptiScaler/wiki/{page_path}"
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 404: 
            return {"success": True, "image": "", "notes": "", "dll": "", "upscaler_input": "", "fg_input": ""}
        elif res.status_code != 200: 
            return {"success": False, "error_msg": f"⚠️ 통신 에러 (HTTP {res.status_code})"}
            
        soup = BeautifulSoup(res.text, 'html.parser')
        body = soup.find('div', class_='markdown-body')
        
        extracted_dll = ""
        upscaler_input = ""
        fg_input = ""
        notes_lines = []
        
        if body:
            for table in body.find_all('table'):
                for row in table.find_all('tr'):
                    cols = row.find_all(['th', 'td'])
                    if len(cols) >= 2:
                        key = cols[0].get_text(strip=True).lower()
                        val = cols[1].get_text(separator=" ", strip=True)
                        if 'filename' in key: extracted_dll = val
                        elif 'upscaler input' in key: upscaler_input = val
                        elif 'fg input' in key: fg_input = val
                            
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
            "success": True,
            "image": "", 
            "notes": clean_text, 
            "dll": extracted_dll,
            "upscaler_input": upscaler_input,
            "fg_input": fg_input
        }
    except Exception as e:
        return {"success": False, "error_msg": f"⚠️ 파싱 에러 발생: {e}"}

def send_discord_alert(game, old_game=None, is_update=False):
    if is_update and old_game and old_game.get('message_id'):
        old_msg_id = old_game['message_id']
        try:
            requests.delete(f"{WEBHOOK_URL}/messages/{old_msg_id}", timeout=10)
            time.sleep(1) 
        except Exception as e:
            print(f"기존 메시지 삭제 실패: {e}")

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
    
    ko_name = game.get('kor_name')
    if ko_name:
        display_name = f"{ko_name} ({game['name']})"
    else:
        display_name = game['name']
        
    title = f"{title_prefix}: {display_name}"
    
    mark_status = mark_api = mark_patcher = mark_notes = ""
    if is_update and old_game:
        if game['status'] != old_game.get('status', ''): mark_status = " 🔄"
        if game['native_api'] != old_game.get('native_api', ''): mark_api = " 🔄"
        if game['optipatcher'] != old_game.get('optipatcher', ''): mark_patcher = " 🔄"
        if game.get('notes', '') != old_game.get('notes', ''): mark_notes = " 🔄"

    ko_status += mark_status
    
    # 🌟 OptiPatcher 지원 텍스트 처리 (안티치트 찌꺼기 제거됨)
    opti_raw = game.get('optipatcher', '').strip()
    if opti_raw == '✨' or opti_raw.lower() == 'yes':
        ko_optipatcher = "✨ 지원됨 (패치 필요)" + mark_patcher
    elif opti_raw:
        ko_optipatcher = opti_raw + mark_patcher
    else:
        ko_optipatcher = "❌ 불필요 / 정보 없음" + mark_patcher
        
    native_api_text = str(game.get('native_api', ''))
    
    extracted_dll = game.get('dll', '')
    if extracted_dll:
        target_dll = extracted_dll
    else:
        if icon == "🟢": target_dll = "(예상) dxgi.dll 또는 winmm.dll"
        else: target_dll = "정보 없음"

    up_input = game.get('upscaler_input', '')
    fg_input = game.get('fg_input', '')
    
    if not up_input: up_input = native_api_text 
        
    if up_input: up_text = f"**🎮 업스케일링 인풋:** `{up_input}`"
    else: up_text = "**🎮 업스케일링 인풋:** 정보 없음"
        
    if fg_input: fg_text = f"**🚀 프레임 생성(FG) 인풋:** `{fg_input}`"
    else: fg_text = "**🚀 프레임 생성(FG) 인풋:** 미지원 / 정보 없음"
        
    native_api_text += mark_api
    ko_notes = str(translate_ko(game.get('notes', '')))
    notes_block = f"\n\n**📝 세부 설정 및 이슈**{mark_notes}\n{ko_notes}" if ko_notes else ""
    
    if game.get('detail_link'):
        detail_link_text = f"[👉 OptiScaler 깃허브 상세 페이지(영문) 바로가기](https://github.com/optiscaler/OptiScaler/wiki/{game['detail_link']})"
    else:
        detail_link_text = "🚫 **이 게임은 깃허브 상세 페이지가 없습니다.**"
    
    table_img = game.get('table_image', '')
    final_img = ""
    image_notice = ""
    if table_img:
        final_img = f"https://github.com{table_img}" if table_img.startswith('/') else table_img
    elif game.get('image'):
        final_img = game['image']

    desc = (
        f"**호환성 상태:** {icon} **{ko_status}**\n"
        f"**🔧 OptiPatcher:** {ko_optipatcher}\n\n"
        f"**⚙️ 덮어쓸 DLL 이름:** `{target_dll}`\n"
        f"{up_text}\n"
        f"{fg_text}\n"
        f"(원본 지원 API: {native_api_text})\n"
        f"{notes_block}\n"
        f"**💡 팁:** 번역된 내용이나 예상 설정으로 적용 시 문제가 발생하거나, 세부 설정이 필요하다면 아래 원문 페이지를 확인해 주세요.\n"
        f"{detail_link_text}" # 🌟 수정된 링크 텍스트 변수 적용
        f"{image_notice}"
    )

    if final_img:
        image_notice = "\n\n**🖼️ 적용 스크린샷** (아래 이미지를 클릭하면 확대됩니다)"
        desc += image_notice

    embed = DiscordEmbed(title=title, description=desc, color=color)
    if final_img:
        embed.set_image(url=final_img)
        
    embed.set_footer(text="데이터 제공 (Developed & Maintained by): OptiScaler Team")
    webhook.add_embed(embed)
    
    try:
        response = webhook.execute()
        new_message_id = None
        if response.status_code in [200, 201]:
            resp_json = response.json()
            if isinstance(resp_json, list): new_message_id = resp_json[0].get('id')
            else: new_message_id = resp_json.get('id')
        return new_message_id
    except Exception as e:
        print(f"디스코드 웹훅 전송 실패: {e}")
        return None

def run():
    print("옵티스케일러 봇 [전체 데이터 실전 모드] 시작 중...")
    history = load_history()
    all_games = parse_main_table()
    
    if not all_games:
        print("게임을 불러오지 못했습니다.")
        return
        
    msg_count = 0
    
    for name, data in all_games.items():
        old_data = history.get(name)
        is_new = old_data is None
        
        main_changed = False
        if not is_new:
            # 🌟 anti_cheat 비교 로직도 optipatcher로 교체 완료
            if (data['status'] != old_data.get('status', '') or
                data['native_api'] != old_data.get('native_api', '') or
                data['optipatcher'] != old_data.get('optipatcher', '') or
                data.get('table_image', '') != old_data.get('table_image', '')):
                main_changed = True

        details = fetch_detail_page(data['detail_link'])
        
        if details.get('success'):
            data['image'] = details.get('image', '')
            data['notes'] = details.get('notes', '')
            data['dll'] = details.get('dll', '')
            data['upscaler_input'] = details.get('upscaler_input', '')
            data['fg_input'] = details.get('fg_input', '')
        else:
            if not is_new:
                data['image'] = old_data.get('image', '')
                data['notes'] = old_data.get('notes', '')
                data['dll'] = old_data.get('dll', '')
                data['upscaler_input'] = old_data.get('upscaler_input', '')
                data['fg_input'] = old_data.get('fg_input', '')
            else:
                data['image'] = ""
                data['notes'] = details.get('error_msg', '')
                data['dll'] = ""
                data['upscaler_input'] = ""
                data['fg_input'] = ""
                
        time.sleep(0.5) 
        
        if is_new:
            data['kor_name'] = get_steam_korean_name(name)
        else:
            data['kor_name'] = old_data.get('kor_name')
        
        if old_data and old_data.get('message_id'):
            data['message_id'] = old_data['message_id']
            
        is_updated = False
        if not is_new:
            if (main_changed or
                data['notes'] != old_data.get('notes', '') or
                data['dll'] != old_data.get('dll', '') or
                data['upscaler_input'] != old_data.get('upscaler_input', '') or
                data['fg_input'] != old_data.get('fg_input', '') or
                data.get('kor_name', '') != old_data.get('kor_name', '')):
                is_updated = True
                
        if is_new or is_updated:
            print(f"알림 전송 중: {name} (신규: {is_new}, 업데이트: {is_updated})")
            
            new_msg_id = send_discord_alert(data, old_game=old_data, is_update=is_updated)
            
            if new_msg_id: 
                data['message_id'] = new_msg_id
            
            history[name] = data
            msg_count += 1
            
            save_history(history)
            time.sleep(3) 
        else:
            history[name] = data

    save_history(history)
    print(f"작업 완료! 총 {msg_count}건의 알림이 전송 및 업데이트되었습니다.")

if __name__ == "__main__":
    run()