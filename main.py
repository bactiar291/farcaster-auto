import requests
import json
import time
import random
from datetime import datetime, timedelta
from pathlib import Path
import sys
import os
import argparse
from typing import List, Dict, Optional, Tuple
import hashlib
import base64

class SecureFarcasterBot:
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.load_config()
        
        self.accounts = []
        self.messages = []
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': self.get_random_user_agent()
        })
        
        self.rate_limit_delay = self.config.get('rate_limit_delay', {
            'min': 3,
            'max': 8,
            'follow_min': 8,
            'follow_max': 15
        })
        self.batch_size = self.config.get('batch_size', 50)
        self.timeout = self.config.get('timeout', 30)
        self.max_retries = self.config.get('max_retries', 3)
        
    def load_config(self) -> None:
        default_config = {
            'api_url': 'https://farcaster.xyz/~api/v2',
            'feed_key': 'home',
            'feed_type': 'default',
            'rate_limit_delay': {
                'min': 3,
                'max': 8,
                'follow_min': 8,
                'follow_max': 15
            },
            'batch_size': 50,
            'timeout': 30,
            'max_retries': 3,
            'account_file': 'accounts.enc',
            'message_file': 'messages.txt'
        }
        
        if Path(self.config_file).exists():
            try:
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
                print(f"Loaded config from {self.config_file}")
            except Exception as e:
                print(f"Error loading config: {e}, using defaults")
                self.config = default_config
        else:
            self.config = default_config
            self.save_config()
            
    def save_config(self) -> None:
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
            
    def get_random_user_agent(self) -> str:
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1'
        ]
        return random.choice(user_agents)
        
    def encrypt_token(self, token: str) -> str:
        salt = os.urandom(16)
        key = hashlib.pbkdf2_hmac('sha256', b'default_key', salt, 100000)
        token_bytes = token.encode()
        encrypted = bytes(a ^ b for a, b in zip(token_bytes, key[:len(token_bytes)]))
        return base64.b64encode(salt + encrypted).decode()
        
    def decrypt_token(self, encrypted_token: str) -> Optional[str]:
        try:
            data = base64.b64decode(encrypted_token)
            salt = data[:16]
            encrypted = data[16:]
            key = hashlib.pbkdf2_hmac('sha256', b'default_key', salt, 100000)
            token_bytes = bytes(a ^ b for a, b in zip(encrypted, key[:len(encrypted)]))
            return token_bytes.decode()
        except:
            return None
            
    def load_accounts(self) -> bool:
        account_file = self.config.get('account_file', 'accounts.enc')
        try:
            if Path(account_file).exists():
                with open(account_file, 'r', encoding='utf-8') as f:
                    encrypted_tokens = [line.strip() for line in f if line.strip()]
                
                for encrypted_token in encrypted_tokens:
                    token = self.decrypt_token(encrypted_token)
                    if token:
                        self.accounts.append(token)
                
                if not self.accounts:
                    print("No valid accounts found in encrypted file")
                    return False
                    
                print(f"Loaded {len(self.accounts)} accounts from encrypted file")
                return True
            else:
                print(f"Account file {account_file} not found")
                return False
                
        except Exception as e:
            print(f"Error loading accounts: {e}")
            return False
    
    def load_messages(self) -> bool:
        message_file = self.config.get('message_file', 'messages.txt')
        try:
            if Path(message_file).exists():
                with open(message_file, 'r', encoding='utf-8') as f:
                    self.messages = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                print(f"Loaded {len(self.messages)} messages")
                return True
            else:
                print(f"Message file {message_file} not found")
                return False
        except Exception as e:
            print(f"Error loading messages: {e}")
            return False

    def make_request(self, method: str, endpoint: str, bearer_token: str, 
                    payload: Optional[Dict] = None) -> Optional[requests.Response]:
        url = f"{self.config['api_url']}/{endpoint}"
        headers = {"Authorization": f"Bearer {bearer_token}"}
        
        for attempt in range(self.max_retries):
            try:
                self.session.headers['User-Agent'] = self.get_random_user_agent()
                
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    print(f"Rate limited. Waiting {retry_after} seconds")
                    time.sleep(retry_after)
                    continue
                    
                return response
                
            except requests.exceptions.RequestException as e:
                print(f"Request failed attempt {attempt+1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None
    
    def get_feed(self, bearer_token: str, limit: int = 100) -> Tuple[bool, List[Dict]]:
        payload = {
            "feedKey": self.config.get('feed_key', 'home'),
            "feedType": self.config.get('feed_type', 'default'),
            "castViewEvents": [],
            "updateState": True
        }
        
        response = self.make_request("POST", "feed-items", bearer_token, payload)
        
        if response and response.status_code == 200:
            data = response.json()
            cast_data = []
            if 'result' in data and 'items' in data['result']:
                for item in data['result']['items'][:limit]:
                    if 'cast' in item:
                        cast_hash = item['cast'].get('hash')
                        author_fid = item['cast'].get('author', {}).get('fid')
                        if cast_hash and author_fid:
                            cast_data.append({
                                'hash': cast_hash,
                                'fid': author_fid,
                                'text': item['cast'].get('text', '')[:100] + '...' if item['cast'].get('text') else ''
                            })
            return True, cast_data
        else:
            status_code = response.status_code if response else 'N/A'
            print(f"Failed to get feed Status: {status_code}")
            return False, []
    
    def like_cast(self, bearer_token: str, cast_hash: str) -> bool:
        payload = {"castHash": cast_hash}
        response = self.make_request("PUT", "cast-likes", bearer_token, payload)
        return response.status_code == 200 if response else False
    
    def recast(self, bearer_token: str, cast_hash: str) -> bool:
        payload = {"castHash": cast_hash}
        response = self.make_request("PUT", "recasts", bearer_token, payload)
        return response.status_code == 200 if response else False
    
    def follow_user(self, bearer_token: str, target_fid: int) -> bool:
        payload = {"targetFid": target_fid}
        response = self.make_request("PUT", "follows", bearer_token, payload)
        return response.status_code == 200 if response else False
    
    def post_cast(self, bearer_token: str, text: str) -> bool:
        payload = {"text": text, "embeds": []}
        response = self.make_request("POST", "casts", bearer_token, payload)
        return response.status_code == 201 if response else False

    def execute_focused_action(self, bearer_token: str, account_idx: int, 
                              action_type: str, target_count: int) -> int:
        print(f"\n{'-'*60}")
        print(f"[ACCOUNT {account_idx}] FOCUS MODE: {action_type.upper()} ({target_count} targets)")
        print(f"{'-'*60}")
        
        print("Getting feed from homepage...")
        success, cast_data = self.get_feed(bearer_token, limit=max(100, target_count * 2))
        
        if not success or not cast_data:
            print("Failed to get feed or feed empty")
            return 0
        
        print(f"Successfully got {len(cast_data)} posts from feed")
        
        if len(cast_data) < target_count:
            print(f"Feed only has {len(cast_data)} posts. Adjusting target.")
            target_count = len(cast_data)
        
        random.shuffle(cast_data)
        selected_casts = cast_data[:target_count]
        
        print(f"Starting {action_type} for {target_count} targets...\n")
        
        success_count = 0
        followed_fids = set()
        
        for idx, cast_info in enumerate(selected_casts, 1):
            cast_hash = cast_info['hash']
            author_fid = cast_info['fid']
            short_hash = cast_hash[:10] + "..."
            short_text = cast_info.get('text', '')[:50]
            
            print(f"[{idx}/{target_count}] Cast: {short_hash} | FID: {author_fid}")
            print(f"    Text: {short_text}")
            
            success = False
            
            if action_type == 'like':
                success = self.like_cast(bearer_token, cast_hash)
                action_icon = "❤️"
            elif action_type == 'recast':
                success = self.recast(bearer_token, cast_hash)
                action_icon = "🔁"
            elif action_type == 'follow':
                if author_fid not in followed_fids:
                    success = self.follow_user(bearer_token, author_fid)
                    action_icon = "👤"
                    if success:
                        followed_fids.add(author_fid)
                else:
                    print(f"  FID {author_fid} already followed, skipping.")
                    success_count += 1
                    continue
            
            if success:
                print(f"  {action_icon} {action_type.capitalize()} successful")
                success_count += 1
            else:
                print(f"  {action_type.capitalize()} failed")
            
            if idx < target_count:
                if action_type == 'follow':
                    wait = random.uniform(
                        self.rate_limit_delay['follow_min'],
                        self.rate_limit_delay['follow_max']
                    )
                else:
                    wait = random.uniform(
                        self.rate_limit_delay['min'],
                        self.rate_limit_delay['max']
                    )
                print(f"  Waiting {wait:.1f} seconds...\n")
                time.sleep(wait)
        
        print(f"\n{action_type.capitalize()} completed: {success_count}/{target_count} successful")
        return success_count

    def run_focused_mode(self) -> None:
        if not self.accounts:
            print("Accounts not loaded!")
            return
        
        print("\n" + "="*60)
        print("FOCUS MODE - SELECT SPECIFIC ACTION")
        print("="*60)
        
        print("\nSelect action to focus on:")
        print("1 Like")
        print("2 Recast")
        print("3 Follow")
        print("4 Like + Recast")
        print("5 Like + Follow")
        print("6 Recast + Follow")
        print("7 Like + Recast + Follow")
        
        choice = input("Choice (1-7): ").strip()
        
        action_map = {
            '1': ['like'],
            '2': ['recast'],
            '3': ['follow'],
            '4': ['like', 'recast'],
            '5': ['like', 'follow'],
            '6': ['recast', 'follow'],
            '7': ['like', 'recast', 'follow']
        }
        
        if choice not in action_map:
            print("Invalid choice!")
            return
        
        selected_actions = action_map[choice]
        
        action_targets = {}
        for action in selected_actions:
            while True:
                try:
                    target = int(input(f"  Target {action} per account (example: 1000): "))
                    if target > 0:
                        action_targets[action] = target
                        break
                    else:
                        print("    Target must be greater than 0.")
                except ValueError:
                    print("    Enter valid number.")
        
        print(f"\nConfiguration:")
        for action, target in action_targets.items():
            print(f"  {action.upper()}: {target} per account")
        
        post_cast = input("\nPost cast too? (y/n): ").lower().strip() == 'y'
        
        print("\n" + "="*60)
        print(f"STARTING FOCUS MODE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        total_stats = {action: 0 for action in selected_actions}
        if post_cast:
            total_stats['posts'] = 0
        
        for idx, bearer_token in enumerate(self.accounts, 1):
            token_preview = bearer_token[:8] + "..." + bearer_token[-8:] if len(bearer_token) > 20 else "***"
            
            print(f"\n{'#'*60}")
            print(f"ACCOUNT {idx}/{len(self.accounts)}: {token_preview}")
            print(f"{'#'*60}")
            
            if post_cast and self.messages:
                message = random.choice(self.messages)
                print(f"\nPosting: {message[:60]}...")
                
                if self.post_cast(bearer_token, message):
                    print("Post successful!")
                    total_stats['posts'] = total_stats.get('posts', 0) + 1
                else:
                    print("Post failed!")
                
                wait = random.uniform(5, 10)
                print(f"Waiting {wait:.1f} seconds...\n")
                time.sleep(wait)
            
            for action in selected_actions:
                target = action_targets[action]
                
                if target > self.batch_size:
                    print(f"\nTarget {target} {action} divided into batches...")
                    batch_size = min(self.batch_size, target)
                    remaining = target
                    batch_count = 0
                    
                    while remaining > 0:
                        current_batch = min(batch_size, remaining)
                        batch_count += 1
                        
                        print(f"\n  Batch #{batch_count}: {current_batch} {action}")
                        success = self.execute_focused_action(
                            bearer_token, idx, action, current_batch
                        )
                        total_stats[action] += success
                        remaining -= current_batch
                        
                        if remaining > 0:
                            wait = random.uniform(30, 60)
                            print(f"\n  Batch wait {wait:.1f} seconds...")
                            time.sleep(wait)
                else:
                    success = self.execute_focused_action(bearer_token, idx, action, target)
                    total_stats[action] += success
            
            if idx < len(self.accounts):
                wait = random.uniform(15, 30)
                print(f"\nWaiting {wait:.1f} seconds before next account...")
                time.sleep(wait)
        
        print("\n" + "="*60)
        print("FOCUS MODE RESULTS")
        print("="*60)
        for action in selected_actions:
            print(f"{action.upper()}: {total_stats[action]}")
        if post_cast:
            print(f"POSTS: {total_stats.get('posts', 0)}")
        print("="*60)

    def countdown_timer(self, seconds: int, message: str = "Waiting") -> None:
        end_time = time.time() + seconds
        
        while time.time() < end_time:
            remaining = int(end_time - time.time())
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            secs = remaining % 60
            
            time_str = f"{hours:02d}:{minutes:02d}:{secs:02d}"
            
            print(f"\r⏳ {message}: {time_str} ", end='', flush=True)
            time.sleep(1)
        
        print("\r" + " " * 80 + "\r", end='')

    def run_continuous_mode(self, interval_hours: int = 1) -> None:
        cycle = 1
        
        print("\n" + "="*60)
        print("SETUP CONTINUOUS MODE")
        print("="*60)
        
        print("\nSelect actions to run each cycle:")
        print("1 Like")
        print("2 Recast")
        print("3 Follow")
        print("4 Like + Recast")
        print("5 Like + Follow")
        print("6 Recast + Follow")
        print("7 Like + Recast + Follow")
        
        choice = input("Choice (1-7): ").strip()
        
        action_map = {
            '1': ['like'],
            '2': ['recast'],
            '3': ['follow'],
            '4': ['like', 'recast'],
            '5': ['like', 'follow'],
            '6': ['recast', 'follow'],
            '7': ['like', 'recast', 'follow']
        }
        
        if choice not in action_map:
            print("Invalid choice!")
            return
        
        selected_actions = action_map[choice]
        
        action_targets = {}
        for action in selected_actions:
            while True:
                try:
                    target = int(input(f"  Target {action} per account per cycle: "))
                    if target > 0:
                        action_targets[action] = target
                        break
                    else:
                        print("    Target must be greater than 0.")
                except ValueError:
                    print("    Enter valid number.")
        
        post_cast = input("\nPost cast each cycle? (y/n): ").lower().strip() == 'y'
        
        print(f"\nContinuous Mode Configuration:")
        print(f"  ⏱️  Interval: {interval_hours} hours")
        for action, target in action_targets.items():
            print(f"  {action.upper()}: {target} per account")
        if post_cast:
            print(f"  📝 Posting: Yes")
        
        input("\nPress ENTER to start...\n")
        
        while True:
            print(f"\n{'='*60}")
            print(f"🔄 CYCLE #{cycle} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")
            
            total_stats = {action: 0 for action in selected_actions}
            if post_cast:
                total_stats['posts'] = 0
            
            for idx, bearer_token in enumerate(self.accounts, 1):
                token_preview = bearer_token[:8] + "..." + bearer_token[-8:] if len(bearer_token) > 20 else "***"
                
                print(f"\n{'#'*60}")
                print(f"ACCOUNT {idx}/{len(self.accounts)}: {token_preview}")
                print(f"{'#'*60}")
                
                if post_cast and self.messages:
                    message = random.choice(self.messages)
                    print(f"\n📝 Posting: {message[:60]}...")
                    
                    if self.post_cast(bearer_token, message):
                        print("✅ Post successful!")
                        total_stats['posts'] += 1
                    else:
                        print("❌ Post failed!")
                    
                    wait = random.uniform(5, 10)
                    print(f"⏳ Waiting {wait:.1f} seconds...\n")
                    time.sleep(wait)
                
                for action in selected_actions:
                    target = action_targets[action]
                    success = self.execute_focused_action(bearer_token, idx, action, target)
                    total_stats[action] += success
                
                if idx < len(self.accounts):
                    wait = random.uniform(15, 30)
                    print(f"\n⏳ Waiting {wait:.1f} seconds before next account...")
                    time.sleep(wait)
            
            print("\n" + "="*60)
            print(f"📊 RESULTS CYCLE #{cycle}")
            print("="*60)
            for action in selected_actions:
                print(f"{action.upper()}: {total_stats[action]}")
            if post_cast:
                print(f"POSTS: {total_stats.get('posts', 0)}")
            print("="*60)
            
            next_time = datetime.now() + timedelta(hours=interval_hours)
            wait_seconds = interval_hours * 3600
            
            print(f"\n⏱️  Cycle #{cycle} completed!")
            print(f"📅 Next cycle: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"⏳ Waiting {interval_hours} hours...\n")
            
            self.countdown_timer(wait_seconds, f"Cycle #{cycle+1} starts in")
            
            print(f"\n✅ Wait time completed! Starting cycle #{cycle+1}...\n")
            cycle += 1

def setup_accounts():
    print("\n" + "="*60)
    print("ACCOUNT SETUP")
    print("="*60)
    
    accounts = []
    print("\nEnter bearer tokens (one per line).")
    print("Enter 'done' when finished:\n")
    
    counter = 1
    while True:
        token = input(f"Token #{counter}: ").strip()
        if token.lower() == 'done':
            break
        if token:
            accounts.append(token)
            counter += 1
    
    if accounts:
        bot = SecureFarcasterBot()
        encrypted_accounts = []
        
        for token in accounts:
            encrypted = bot.encrypt_token(token)
            encrypted_accounts.append(encrypted)
        
        with open(bot.config.get('account_file', 'accounts.enc'), 'w') as f:
            for encrypted_token in encrypted_accounts:
                f.write(encrypted_token + '\n')
        
        print(f"\n✅ {len(accounts)} accounts saved encrypted")
    else:
        print("\n❌ No accounts saved")

def create_example_files():
    if not Path("messages.txt").exists():
        with open("messages.txt", 'w', encoding='utf-8') as f:
            f.write("Hello Farcaster! 🚀\n")
            f.write("GM everyone! ☀️\n")
            f.write("Building in public today! 💪\n")
            f.write("Just shipped something cool! 🎉\n")
        print("✅ Created messages.txt file")

def main():
    parser = argparse.ArgumentParser(description='Secure Farcaster Bot')
    parser.add_argument('--setup', action='store_true', help='Setup accounts')
    parser.add_argument('--config', default='config.json', help='Config file path')
    args = parser.parse_args()
    
    if args.setup:
        setup_accounts()
        return
    
    print("="*60)
    print("🔒 SECURE FARCASTER BOT")
    print("="*60)
    
    create_example_files()
    
    bot = SecureFarcasterBot(args.config)
    
    if not bot.load_accounts():
        print("\n❌ Failed to load accounts")
        print("Use --setup to configure accounts")
        return
    
    if not bot.load_messages():
        print("\n⚠️  Could not load messages")
    
    print("\n" + "="*60)
    print("🤖 BOT CONFIGURATION")
    print("="*60)
    print(f"👤 Accounts: {len(bot.accounts)}")
    print(f"💬 Messages: {len(bot.messages)}")
    print("="*60)
    
    print("\n📋 SELECT OPERATION MODE:")
    print("1 Focus Mode (One time run)")
    print("2 Continuous Mode (Auto loop)")
    
    mode = input("Choice (1-2): ").strip()
    
    if mode == "1":
        print("\n🚀 Starting Focus Mode...")
        bot.run_focused_mode()
        print("\n✅ Focus Mode completed!")
    elif mode == "2":
        print("\n🔄 Starting Continuous Mode...")
        interval = input("Interval (hours) [default: 1]: ").strip()
        interval_hours = int(interval) if interval.isdigit() else 1
        bot.run_continuous_mode(interval_hours=interval_hours)
    else:
        print("Invalid choice!")

if __name__ == "__main__":
    main()
