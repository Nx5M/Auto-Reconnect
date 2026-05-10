#!/usr/bin/env python3
import os
import sqlite3
import subprocess
import requests
import re
import tempfile
import shutil
from contextlib import contextmanager
from typing import Optional, Tuple, Dict, List

DEFAULT_CHECK_INTERVAL = 30
DEFAULT_RESTART_DELAY = 15
DEFAULT_DISCORD_BOT_NAME = "Auto Rejoin Bot"

PACKAGES = {"Roblox App": "com.roblox.client"}
WEBVIEW_COOKIE_PATHS = ["databases/webviewCookiesChromium.db", "app_webview/Cookies", "app_webview/Default/Cookies"]
ROBLOX_COOKIE_NAME = ".ROBLOSECURITY"

def validate_url(url: str) -> bool:
    if not url: return False
    pattern = re.compile(r'^https?://(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::\d+)?(?:/?|[/?]\S+)$', re.IGNORECASE)
    return bool(pattern.match(url))

def validate_user_id(user_id: str) -> bool: return bool(user_id) and user_id.isdigit() and len(user_id) >= 3

def validate_numeric_input(value: str, min_val: int = 1, max_val: int = 3600) -> bool:
    if not value or not value.isdigit(): return False
    return min_val <= int(value) <= max_val

def get_validated_input(prompt: str, validator, default: Optional[str] = None, error_msg: str = "Invalid input.") -> str:
    while True:
        user_input = input(prompt).strip()
        if default and not user_input: return default
        if validator(user_input): return user_input
        print(error_msg)

def get_yes_no_input(prompt: str, default: bool = True) -> bool:
    default_str = "y" if default else "n"
    user_input = input(f"{prompt} (y/n, default {default_str}): ").strip().lower()
    if not user_input: return default
    return user_input != "n"

@contextmanager
def temp_database_path(suffix: str = ".db"):
    temp_file = None
    try:
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        temp_path = temp_file.name
        temp_file.close()
        yield temp_path
    finally:
        if temp_file and os.path.exists(temp_path):
            try: os.remove(temp_path)
            except OSError: pass

def check_root() -> bool:
    try: return subprocess.run(["su", "-c", "id"], capture_output=True, timeout=5).returncode == 0
    except: return False

def run_shell_cmd(cmd_str: str) -> Tuple[bool, str]:
    try:
        result = subprocess.run(["su", "-c", cmd_str], capture_output=True, text=True, timeout=10)
        if result.returncode == 0: return True, result.stdout.strip()
        else: return False, result.stderr.strip()
    except Exception as e: return False, str(e)

def check_package_installed(package_name):
    success, output = run_shell_cmd(f"pm list packages | grep {package_name}")
    return success and package_name in output

def find_installed_app() -> Dict[str, str]:
    return {name: pkg for name, pkg in PACKAGES.items() if check_package_installed(pkg)}

def find_cookie_databases(package_name: str) -> List[str]:
    base_path = f"/data/data/{package_name}"
    found_paths = []
    for path in WEBVIEW_COOKIE_PATHS:
        full_path = f"{base_path}/{path}"
        if "*" in full_path:
            success, output = run_shell_cmd(f"ls {full_path} 2>/dev/null")
            if success and output: found_paths.extend([line.strip() for line in output.split("\n") if line.strip()])
        else:
            if run_shell_cmd(f'test -f {full_path} && echo "exists"')[0]: found_paths.append(full_path)
    return found_paths

def copy_database(db_path: str, temp_path: str) -> bool:
    try:
        if not run_shell_cmd(f'cp "{db_path}" "{temp_path}"')[0]: return False
        run_shell_cmd(f'chmod 666 "{temp_path}"')
        return True
    except: return False

def extract_cookie_from_webview(db_path: str) -> Optional[str]:
    with temp_database_path("_cookies_webview.db") as temp_db:
        if not copy_database(db_path, temp_db): return None
        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT name, value, host_key FROM cookies WHERE (host_key LIKE '%roblox.com%' OR host_key LIKE '%www.roblox.com%') AND name = ?", (ROBLOX_COOKIE_NAME,))
                result = cursor.fetchone()
            except sqlite3.OperationalError:
                cursor.execute("SELECT name, value FROM cookies WHERE name = ?", (ROBLOX_COOKIE_NAME,))
                result = cursor.fetchone()
            conn.close()
            return result[1] if result and len(result) > 1 else result[0] if result else None
        except: return None

def auto_extract_cookie() -> Optional[str]:
    if not check_root():
        print("Root access required for auto cookie extraction\n")
        return None
    installed_apps = find_installed_app()
    if not installed_apps: return None
    for app_name, package_name in installed_apps.items():
        print(f"Checking {app_name} for cookie...")
        for db_path in find_cookie_databases(package_name):
            cookie = extract_cookie_from_webview(db_path)
            if cookie:
                print(f"Cookie extracted successfully ({len(cookie)} characters)\n")
                return cookie
    return None

def get_roblox_user_info(cookie: str) -> Tuple[Optional[int], Optional[str]]:
    try:
        r = requests.get("https://users.roblox.com/v1/users/authenticated", headers={"Cookie": f".ROBLOSECURITY={cookie}", "User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200: return r.json().get("id"), r.json().get("name")
        return None, None
    except: return None, None

def setup() -> None:
    print("\nAuto Rejoin Setup (Discord + Telegram)")
    print("----------------\n")
    env_path = ".env"

    if os.path.exists(env_path) and not get_yes_no_input("Existing .env file found. Overwrite?", False): return

    print("\nPilih Environment/Device yang kamu gunakan:")
    print("1. Cloud Phone (Redfinger, LDCloud, dll) -> Auto Copy ke Download")
    print("2. Device Android Biasa / Emulator (MumuPlayer, LDPlayer, dll) -> Setup Full via Terminal")
    
    device_choice = get_validated_input("Pilihanmu (1/2): ", lambda x: x in ["1", "2"])
    print("\n----------------\n")

    if device_choice == "1":
        print("[ MODE CLOUD PHONE TERPILIH ]")
        roblox_cookie = auto_extract_cookie() if get_yes_no_input("Auto-extract cookie from Roblox app?", True) else get_validated_input("Roblox Cookie (.ROBLOSECURITY): ", lambda x: len(x) > 10)
        
        fetched_user_id, fetched_username = get_roblox_user_info(roblox_cookie) if roblox_cookie else (None, None)
        if fetched_user_id: print(f"Logged in as: {fetched_username} (ID: {fetched_user_id})")
        user_id = str(fetched_user_id) if fetched_user_id else ""

        env_content = f"""PS_LINK=ISI_LINK_PRIVATE_SERVER_DISINI_MENGGUNAKAN_FILE_MANAGER
USER_ID={user_id}
CHECK_INTERVAL={DEFAULT_CHECK_INTERVAL}
RESTART_DELAY={DEFAULT_RESTART_DELAY}
ROBLOX_COOKIE={roblox_cookie if roblox_cookie else ''}
USE_PSUTIL=false

# === TELEGRAM SETTINGS ===
TELEGRAM_BOT_TOKEN=ISI_TOKEN_BOT_DISINI_JIKA_INGIN_PAKAI_TELEGRAM
TELEGRAM_CHAT_ID=ISI_CHAT_ID_DISINI_JIKA_INGIN_PAKAI_TELEGRAM
TELEGRAM_ENABLED=true
TELEGRAM_NOTIFY_ON_START=true
TELEGRAM_NOTIFY_ON_REJOIN=true
TELEGRAM_NOTIFY_ON_ERROR=true

# === DISCORD SETTINGS ===
DISCORD_WEBHOOK_URL=ISI_WEBHOOK_URL_DISINI_JIKA_INGIN_PAKAI_DISCORD
DISCORD_WEBHOOK_NAME={DEFAULT_DISCORD_BOT_NAME}
DISCORD_MENTION_USER=
DISCORD_ENABLED=true
DISCORD_NOTIFY_ON_START=true
DISCORD_NOTIFY_ON_REJOIN=true
DISCORD_NOTIFY_ON_ERROR=true
"""
        with open(env_path, "w") as f: f.write(env_content.strip())

        current_dir = os.getcwd()
        target_dir = "/sdcard/Download/Auto-Rejoin"
        is_copied = False

        if "/sdcard" not in current_dir and "/storage" not in current_dir:
            if run_shell_cmd(f"cp -rf '{current_dir}' '{target_dir}'")[0]:
                run_shell_cmd(f"chmod -R 777 '{target_dir}'")
                is_copied = True
            else:
                try:
                    if os.path.exists(target_dir): shutil.rmtree(target_dir)
                    shutil.copytree(current_dir, target_dir)
                    is_copied = True
                except: pass
        else:
            is_copied = True
            target_dir = current_dir

        print("\n" + "="*55)
        print(" SETUP TAHAP 1 SELESAI ".center(55, "="))
        print("="*55)
        
        if is_copied:
            print(f"\nFolder lu sekarang ada di: {target_dir}")
            print("\n1. Buka File Manager lu, masuk ke folder Download/Auto-Rejoin.")
            print("2. Buka dan edit file bernama '.env'")
            print("3. Isi PS_LINK lu.")
            print("4. Isi Token/Webhook di bagian Telegram atau Discord.")
            print("5. Save file .env tersebut.")
            print(f"\n6. Terakhir, kembali ke Termux:\n   cd {target_dir}\n   python main.py")
        print("="*55 + "\n")
        return

    # === MODE ANDROID NATIVE / EMULATOR ===
    roblox_cookie = auto_extract_cookie() if get_yes_no_input("Auto-extract cookie from Roblox app?", True) else get_validated_input("Roblox Cookie (.ROBLOSECURITY): ", lambda x: len(x) > 10)

    fetched_user_id, fetched_username = get_roblox_user_info(roblox_cookie) if roblox_cookie else (None, None)
    if fetched_user_id: print(f"Logged in as: {fetched_username} (ID: {fetched_user_id})")

    ps_link = get_validated_input("Private Server Link: ", validate_url)
    user_id = str(fetched_user_id) if fetched_user_id and get_yes_no_input(f"Use User ID {fetched_user_id}?", True) else get_validated_input("Roblox User ID: ", validate_user_id)

    check_interval = get_validated_input(f"Check Interval (default {DEFAULT_CHECK_INTERVAL}): ", lambda x: validate_numeric_input(x, 5, 3600) or x == "", str(DEFAULT_CHECK_INTERVAL))
    restart_delay = get_validated_input(f"Restart Delay (default {DEFAULT_RESTART_DELAY}): ", lambda x: validate_numeric_input(x, 5, 300) or x == "", str(DEFAULT_RESTART_DELAY))

    print("\n----------------\nNotification Setup\n")
    
    # Telegram
    telegram_token, telegram_chat_id = ("", "")
    if get_yes_no_input("Setup Telegram Notification?", False):
        telegram_token = input("Telegram Bot Token: ").strip()
        telegram_chat_id = input("Telegram Chat ID: ").strip()

    # Discord
    discord_webhook, discord_webhook_name, discord_mention_user = ("", DEFAULT_DISCORD_BOT_NAME, "")
    if get_yes_no_input("Setup Discord Webhook?", False):
        discord_webhook = input("Discord Webhook URL: ").strip()
        discord_webhook_name = input(f"Discord Bot Name (default: {DEFAULT_DISCORD_BOT_NAME}): ").strip() or DEFAULT_DISCORD_BOT_NAME
        discord_mention_user = input("Discord User ID to Mention: ").strip()

    env_content = f"""PS_LINK={ps_link}
USER_ID={user_id}
CHECK_INTERVAL={check_interval}
RESTART_DELAY={restart_delay}
ROBLOX_COOKIE={roblox_cookie}
USE_PSUTIL=true

TELEGRAM_BOT_TOKEN={telegram_token}
TELEGRAM_CHAT_ID={telegram_chat_id}
TELEGRAM_ENABLED={'true' if telegram_token and telegram_chat_id else 'false'}
TELEGRAM_NOTIFY_ON_START=true
TELEGRAM_NOTIFY_ON_REJOIN=true
TELEGRAM_NOTIFY_ON_ERROR=true

DISCORD_WEBHOOK_URL={discord_webhook}
DISCORD_WEBHOOK_NAME={discord_webhook_name}
DISCORD_MENTION_USER={discord_mention_user}
DISCORD_ENABLED={'true' if discord_webhook else 'false'}
DISCORD_NOTIFY_ON_START=true
DISCORD_NOTIFY_ON_REJOIN=true
DISCORD_NOTIFY_ON_ERROR=true
"""

    with open(env_path, "w") as f: f.write(env_content.strip())
    print(f"\nConfiguration saved to {env_path}\nSetup complete. Run main.py\n")

if __name__ == "__main__":
    try: setup()
    except KeyboardInterrupt: print("\n\nSetup cancelled.")
