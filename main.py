import os
import time
import subprocess
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

ROBLOX_PACKAGE = "com.roblox.client"

class TelegramNotifier:
    def __init__(self, user_id):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.enabled = (
            os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
            and self.bot_token
            and self.chat_id
            and "ISI_TOKEN_BOT" not in self.bot_token
        )
        self.notify_on_start = os.getenv("TELEGRAM_NOTIFY_ON_START", "true").lower() == "true"
        self.notify_on_rejoin = os.getenv("TELEGRAM_NOTIFY_ON_REJOIN", "true").lower() == "true"
        self.notify_on_error = os.getenv("TELEGRAM_NOTIFY_ON_ERROR", "true").lower() == "true"
        self.user_id = user_id
        self.username, self.display_name = get_user_info(user_id)

    def send_message(self, text):
        if not self.enabled: return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        try:
            requests.post(url, json=payload, timeout=5)
            return True
        except: return False

    def notify_start(self, user_id, check_interval):
        if not self.notify_on_start: return
        msg = f"🟢 <b>Auto Rejoin Started</b>\nMonitoring private server connection\n\n• <b>User ID:</b> <code>{user_id}</code>\n• <b>Check Interval:</b> {check_interval}s\n"
        if self.display_name: msg += f"• <b>Account:</b> {self.display_name} (@{self.username})"
        self.send_message(msg)

    def notify_rejoin(self, reason, game_id=None):
        if not self.notify_on_rejoin: return
        msg = f"🟡 <b>[ Rejoining ]</b> - {reason}\n"
        if game_id: msg += f"\n• <b>Target Game ID:</b> <code>{game_id}</code>"
        self.send_message(msg)

    def notify_status(self, status, game_id=None, universe_id=None):
        if not self.enabled: return
        emoji = "🔵" if status == "In-Game" else "🟡"
        title = f"{emoji} <b>[ {status} ]</b>" 
        if universe_id:
             game_name = get_game_name(universe_id)
             if game_name: title = f"{emoji} <b>[ {status} ]</b> - {game_name}"
        msg = f"{title}\n\n"
        if game_id: msg += f"• <b>Game ID:</b> <code>{game_id}</code>\n"
        if self.display_name: msg += f"• <b>Account:</b> {self.display_name} (@{self.username})\n"
        self.send_message(msg.strip())

    def notify_error(self, error):
        if not self.notify_on_error: return
        self.send_message(f"🔴 <b>Error Occurred</b>\n\n<code>{error}</code>")


class DiscordNotifier:
    def __init__(self, user_id):
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        self.webhook_name = os.getenv("DISCORD_WEBHOOK_NAME", "Auto Rejoin Bot")
        self.mention_user = os.getenv("DISCORD_MENTION_USER", "").strip()
        self.enabled = (
            os.getenv("DISCORD_ENABLED", "false").lower() == "true"
            and self.webhook_url
            and "ISI_WEBHOOK" not in self.webhook_url
            and "YOUR_WEBHOOK" not in self.webhook_url
        )
        self.notify_on_start = os.getenv("DISCORD_NOTIFY_ON_START", "true").lower() == "true"
        self.notify_on_rejoin = os.getenv("DISCORD_NOTIFY_ON_REJOIN", "true").lower() == "true"
        self.notify_on_error = os.getenv("DISCORD_NOTIFY_ON_ERROR", "true").lower() == "true"
        self.user_id = user_id
        self.username, self.display_name = get_user_info(user_id)
        self.avatar_url = get_user_avatar(user_id) if self.username else None

    def format_mention(self):
        if not self.mention_user: return ""
        return f"<@{self.mention_user}>" if self.mention_user.isdigit() else self.mention_user

    def get_system_info(self):
        use_psutil = os.getenv("USE_PSUTIL", "false").lower() == "true"
        
        # Bypass total jika script berjalan di Cloud Phone (Teks CPU/RAM bakal disembunyikan)
        if not use_psutil:
            return None

        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            return {
                "cpu_percent": f"{cpu_percent}%",
                "ram_usage": f"{round(ram.used / (1024**3), 2)}/{round(ram.total / (1024**3), 2)} GB ({ram.percent}%)",
            }
        except ImportError:
            # Fallback notifikasi untuk Device Android Biasa/Emulator jika psutil belum diinstall
            return {
                "cpu_percent": "⚠️ Butuh module 'psutil' (Ketik: pip install psutil)",
                "ram_usage": "⚠️ Butuh module 'psutil' (Ketik: pip install psutil)",
            }
        except Exception as e:
            return {
                "cpu_percent": f"Error: {str(e)}",
                "ram_usage": f"Error: {str(e)}",
            }

    def send_embed(self, title, description, color, fields=None, show_user_info=True):
        if not self.enabled: return False
        content_lines = []
        if description: content_lines.append(f"{description}")
        if fields:
            for field in fields: content_lines.append(f"• **{field.get('name', '')}:** {field.get('value', '')}")
        content_lines.extend(["", "──────────────────────────────", ""])
        
        system_info = self.get_system_info()
        
        if self.display_name: content_lines.append(f"• **Account Name:** {self.display_name}")
        
        # Hanya tambahkan baris CPU & RAM jika system_info tidak kosong (Bukan Cloud Phone)
        if system_info:
            content_lines.append(f"• **CPU Usage:** {system_info['cpu_percent']}")
            content_lines.append(f"• **RAM Usage:** {system_info['ram_usage']}")
            
        mention = self.format_mention()
        if mention: content_lines.append(f"\n{mention}")

        embed = {
            "title": f"**{title}**",
            "description": "\n".join(content_lines),
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": self.webhook_name},
            "thumbnail": {"url": "https://tr.rbxcdn.com/53eb9b17fe1432a809c73a1ca3434645/150/150/Image/Png"}
        }
        if show_user_info and self.username:
             embed["author"] = {"name": f"{self.display_name} (@{self.username})", "icon_url": self.avatar_url}
        try:
            requests.post(self.webhook_url, json={"username": self.webhook_name, "embeds": [embed]}, timeout=5)
            return True
        except: return False

    def notify_start(self, user_id, check_interval):
        if not self.notify_on_start: return
        self.send_embed("Auto Rejoin Started", "Monitoring private server connection", 3447003,
            [{"name": "User ID", "value": str(user_id)}, {"name": "Check Interval", "value": f"{check_interval}s"}])

    def notify_rejoin(self, reason, game_id=None):
        if not self.notify_on_rejoin: return
        fields = [{"name": "Target Game ID", "value": f"`{game_id}`"}] if game_id else []
        self.send_embed(f"[ Rejoining ] - {reason}", "", 16776960, fields)

    def notify_status(self, status, game_id=None, universe_id=None):
        if not self.enabled: return
        title = f"[ {status} ]" 
        if universe_id:
             game_name = get_game_name(universe_id)
             if game_name: title = f"[ {status} ] - {game_name}"
        fields = []
        if game_id: fields.append({"name": "Game ID", "value": f"`{game_id}`"})
        if universe_id and " - " not in title:
             game_name = get_game_name(universe_id)
             if game_name: fields.append({"name": "Game Name", "value": game_name})
        color = 5025616 if status == "In-Game" else 16776960
        self.send_embed(title, "", color, fields)

    def notify_error(self, error):
        if not self.notify_on_error: return
        self.send_embed("Error Occurred", f"```{error}```", 16711680)

def check_root():
    try:
        result = subprocess.run(["su", "-c", "id"], capture_output=True, timeout=5)
        return result.returncode == 0
    except: return False

def run_shell_cmd(cmd_str, use_root=False, silent=False):
    full_cmd = ["su", "-c", cmd_str] if use_root else cmd_str.split()
    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=10)
        return (True, result.stdout.strip()) if result.returncode == 0 else (False, result.stderr.strip())
    except Exception as e: return False, str(e)

def get_roblox_pid():
    success, output = run_shell_cmd(f"pidof {ROBLOX_PACKAGE}", use_root=True, silent=True)
    return output.split()[0] if success and output else None

def force_stop_roblox():
    pid = get_roblox_pid()
    if pid:
        run_shell_cmd(f"kill -9 {pid}", use_root=True, silent=True)
        time.sleep(1)
    run_shell_cmd(f"am force-stop {ROBLOX_PACKAGE}", use_root=True, silent=True)
    time.sleep(1)

def open_ps_link(link):
    return run_shell_cmd(f'am start -a android.intent.action.VIEW -d "{link}" -p {ROBLOX_PACKAGE}', use_root=True, silent=True)[0]

def is_roblox_running(): return get_roblox_pid() is not None

def get_user_info(user_id):
    try:
        r = requests.get(f"https://users.roblox.com/v1/users/{user_id}", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200: return r.json().get("name"), r.json().get("displayName")
    except: pass
    return None, None

def get_user_avatar(user_id):
    try:
        r = requests.get("https://thumbnails.roblox.com/v1/users/avatar-headshot", params={"userIds": user_id, "size": "150x150", "format": "Png", "isCircular": True}, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            images = r.json().get("data", [])
            if images: return images[0].get("imageUrl")
    except: pass
    return None

def get_game_name(universe_id):
    try:
        r = requests.get("https://games.roblox.com/v1/games", params={"universeIds": universe_id}, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            games = r.json().get("data", [])
            if games: return games[0].get("name")
    except: pass
    return None

def check_user_presence(user_id, roblox_cookie=None):
    try:
        cookies = {".ROBLOSECURITY": roblox_cookie} if roblox_cookie else {}
        r = requests.post("https://presence.roblox.com/v1/presence/users", json={"userIds": [user_id]}, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}, cookies=cookies, timeout=10)
        if r.status_code == 200:
            user_presences = r.json().get("userPresences", [])
            if user_presences:
                presence = user_presences[0]
                return presence.get("userPresenceType") == 2, presence.get("gameId"), presence.get("universeId")
    except: pass
    return True, None, None

def should_rejoin(user_id, expected_game_id, roblox_cookie=None):
    if not is_roblox_running(): return True, "Process stopped", None, None
    is_ingame, current_game_id, universe_id = check_user_presence(user_id, roblox_cookie)
    if not is_ingame: return True, "Not in-game", current_game_id, universe_id
    if expected_game_id and current_game_id and current_game_id != expected_game_id: return True, "Server switched", current_game_id, universe_id
    return False, "OK", current_game_id, universe_id

def set_selinux_permissive():
    success, mode = run_shell_cmd("getenforce", use_root=True, silent=True)
    if success and mode.strip() == "Enforcing": run_shell_cmd("setenforce 0", use_root=True, silent=True)

def print_header():
    print("\n" + "-" * 50)
    print("  Auto Rejoin Roblox PS (Discord + Telegram)")
    print("-" * 50 + "\n")

def main():
    if not os.path.exists(".env"):
        print("Error: .env file not found. Run: python setup.py")
        return
    if not check_root():
        print("Error: Root access required")
        return

    set_selinux_permissive()
    print_header()

    ps_link = os.getenv("PS_LINK")
    user_id = os.getenv("USER_ID")
    interval = int(os.getenv("CHECK_INTERVAL", "30"))
    restart_delay = int(os.getenv("RESTART_DELAY", "15"))
    roblox_cookie = os.getenv("ROBLOX_COOKIE")

    tg_notifier = TelegramNotifier(user_id)
    dc_notifier = DiscordNotifier(user_id)

    if not ps_link or "YOUR_CODE" in ps_link or "ISI_LINK_PRIVATE_SERVER" in ps_link:
        print("Error: Configure PS_LINK in .env file")
        return

    print(f"Config: User {user_id}, Interval {interval}s")
    force_stop_roblox()
    time.sleep(2)

    if not open_ps_link(ps_link):
        print("Error: Failed to open Roblox")
        return

    print(f"Initializing...")
    time.sleep(restart_delay * 2)

    _, private_game_id, _ = check_user_presence(user_id, roblox_cookie)
    if private_game_id: print(f"Game ID: {private_game_id[:12]}...")

    print("Monitoring active (Ctrl+C to stop)\n")
    tg_notifier.notify_start(user_id, interval)
    dc_notifier.notify_start(user_id, interval)

    expected_game_id = private_game_id
    last_game_id = None

    while True:
        try:
            needs_rejoin, reason, current_game_id, universe_id = should_rejoin(user_id, expected_game_id, roblox_cookie)

            if needs_rejoin:
                print(f"{reason} - Rejoining...")
                tg_notifier.notify_rejoin(reason, current_game_id)
                dc_notifier.notify_rejoin(reason, current_game_id)

                force_stop_roblox()
                time.sleep(2)
                open_ps_link(ps_link)
                time.sleep(restart_delay * 2)

                _, new_game_id, new_universe_id = check_user_presence(user_id, roblox_cookie)
                if new_game_id:
                    expected_game_id = new_game_id
                    new_game_name = get_game_name(new_universe_id)
                    print("Rejoined successfully")
                    if new_game_name: print(f"Game: {new_game_name}")
                    print()
                    last_game_id = new_game_id
                    tg_notifier.notify_status("Rejoined", new_game_id, new_universe_id)
                    dc_notifier.notify_status("Rejoined", new_game_id, new_universe_id)
                else:
                    print("Rejoined (Game ID unavailable)\n")
                    last_game_id = None
                    tg_notifier.notify_status("Rejoined (Waiting for data...)", None, None)
                    dc_notifier.notify_status("Rejoined (Waiting for data...)", None, None)
            else:
                if not expected_game_id and current_game_id:
                    expected_game_id = current_game_id
                    print(f"Tracking Game ID: {expected_game_id[:12]}...")

                status = "In-Game" if (current_game_id and expected_game_id and current_game_id == expected_game_id) else "In-Game (Unknown server)"
                
                if current_game_id and current_game_id != last_game_id:
                    game_name = get_game_name(universe_id)
                    last_game_id = current_game_id
                    print(f"{status}")
                    if game_name: print(f"Game: {game_name}")
                    tg_notifier.notify_status(status, current_game_id, universe_id)
                    dc_notifier.notify_status(status, current_game_id, universe_id)

            time.sleep(interval)

        except KeyboardInterrupt:
            print("\nStopped by user\n")
            break
        except Exception as e:
            error_msg = str(e)
            print(f"Error: {error_msg}")
            tg_notifier.notify_error(error_msg)
            dc_notifier.notify_error(error_msg)
            time.sleep(5)

if __name__ == "__main__":
    main()
