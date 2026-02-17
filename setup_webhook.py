#!/usr/bin/env python3
"""
HITL Setup Script - Configure Telegram Webhook

This script helps you:
1. Create a Telegram bot (via @BotFather)
2. Get your admin chat ID
3. Generate webhook secret
4. Configure webhook URL
5. Update .env file
6. Apply Supabase schema

Usage:
    python setup_webhook.py
"""

import asyncio
import secrets
import os
from pathlib import Path
from telegram import Bot
from telegram.error import TelegramError


def generate_secret() -> str:
    """Generate secure random secret for webhook"""
    return secrets.token_urlsafe(32)


async def verify_bot_token(token: str) -> dict:
    """
    Verify bot token and get bot info

    Args:
        token: Telegram bot token

    Returns:
        Dict with bot info (id, username, first_name)
    """
    try:
        bot = Bot(token=token)
        me = await bot.get_me()
        return {
            "valid": True,
            "id": me.id,
            "username": me.username,
            "first_name": me.first_name
        }
    except TelegramError as e:
        return {
            "valid": False,
            "error": str(e)
        }


async def set_webhook(token: str, webhook_url: str, secret: str) -> dict:
    """
    Configure Telegram webhook

    Args:
        token: Bot token
        webhook_url: Full webhook URL
        secret: Webhook secret token

    Returns:
        Result dict with success status
    """
    try:
        bot = Bot(token=token)
        result = await bot.set_webhook(
            url=webhook_url,
            secret_token=secret,
            drop_pending_updates=True
        )
        return {"success": result}
    except TelegramError as e:
        return {"success": False, "error": str(e)}


async def get_webhook_info(token: str) -> dict:
    """Get current webhook configuration"""
    try:
        bot = Bot(token=token)
        info = await bot.get_webhook_info()
        return {
            "url": info.url,
            "has_custom_certificate": info.has_custom_certificate,
            "pending_update_count": info.pending_update_count,
            "last_error_date": info.last_error_date,
            "last_error_message": info.last_error_message
        }
    except TelegramError as e:
        return {"error": str(e)}


def update_env_file(env_path: Path, updates: dict):
    """
    Update .env file with new values

    Args:
        env_path: Path to .env file
        updates: Dict of KEY=VALUE pairs to update
    """
    if env_path.exists():
        with open(env_path, "r") as f:
            lines = f.readlines()
    else:
        lines = []

    # Update existing or add new
    updated_keys = set()
    new_lines = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            new_lines.append(line)
            continue

        key = line.split("=", 1)[0]
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    # Add new keys
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    # Write back
    with open(env_path, "w") as f:
        f.write("\n".join(new_lines) + "\n")

    print(f"✅ Updated {env_path}")


def print_header(text: str):
    """Print formatted header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")


async def main():
    """Interactive setup wizard"""
    print_header("🤖 HITL Telegram Webhook Setup")

    # Step 1: Get bot token
    print("📌 Step 1: Telegram Bot Token")
    print("   If you don't have a bot, create one with @BotFather on Telegram")
    print("   Commands: /newbot -> choose name and username")
    print()

    bot_token = input("Enter your bot token: ").strip()

    if not bot_token:
        print("❌ Bot token required!")
        return

    # Verify token
    print("\n🔍 Verifying bot token...")
    bot_info = await verify_bot_token(bot_token)

    if not bot_info["valid"]:
        print(f"❌ Invalid bot token: {bot_info.get('error')}")
        return

    print(f"✅ Bot verified: @{bot_info['username']} ({bot_info['first_name']})")

    # Step 2: Get admin chat ID
    print_header("📱 Step 2: Admin Chat ID")
    print("   To get your chat ID:")
    print(f"   1. Start a conversation with @{bot_info['username']}")
    print("   2. Send any message to the bot")
    print("   3. Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates")
    print("   4. Look for 'chat':{'id': YOUR_CHAT_ID}")
    print()

    chat_id = input("Enter your admin chat ID: ").strip()

    if not chat_id:
        print("❌ Chat ID required!")
        return

    # Step 3: Generate webhook secret
    print_header("🔐 Step 3: Webhook Secret")
    webhook_secret = generate_secret()
    print(f"✅ Generated secure secret: {webhook_secret[:20]}...")

    # Step 4: Get webhook URL
    print_header("🌐 Step 4: Webhook URL")
    print("   Default: https://supabase.dsolution-ia.fr/webhook/telegram")
    print()

    webhook_url = input("Enter webhook URL (or press Enter for default): ").strip()
    if not webhook_url:
        webhook_url = "https://supabase.dsolution-ia.fr/webhook/telegram"

    print(f"📍 Using webhook URL: {webhook_url}")

    # Step 5: Configure webhook
    print_header("⚙️ Step 5: Configure Webhook")
    print("   Setting up webhook with Telegram...")

    webhook_result = await set_webhook(bot_token, webhook_url, webhook_secret)

    if webhook_result.get("success"):
        print("✅ Webhook configured successfully!")

        # Get webhook info
        info = await get_webhook_info(bot_token)
        print(f"\n📊 Webhook Status:")
        print(f"   URL: {info.get('url')}")
        print(f"   Pending updates: {info.get('pending_update_count', 0)}")

        if info.get("last_error_message"):
            print(f"   ⚠️ Last error: {info['last_error_message']}")

    else:
        print(f"❌ Failed to configure webhook: {webhook_result.get('error')}")
        return

    # Step 6: Update .env file
    print_header("💾 Step 6: Update .env File")

    env_path = Path(__file__).parent / ".env"

    env_updates = {
        "TELEGRAM_TOKEN": bot_token,
        "TELEGRAM_WEBHOOK_SECRET": webhook_secret,
        "TELEGRAM_ADMIN_ID": chat_id,
        "TELEGRAM_WEBHOOK_URL": webhook_url,
        "HITL_ENABLED": "true",
        "HITL_TIMEOUT_MINUTES": "30",
        "HITL_FACTURE_THRESHOLD": "1500.0"
    }

    confirm = input(f"\nUpdate {env_path}? (y/n): ").strip().lower()

    if confirm == "y":
        update_env_file(env_path, env_updates)
        print("\n✅ Environment variables updated!")
    else:
        print("\n⚠️ Skipped .env update. Add these manually:")
        for key, value in env_updates.items():
            print(f"   {key}={value}")

    # Step 7: Database setup
    print_header("🗄️ Step 7: Supabase Database Setup")
    print("   Apply the schema:")
    print(f"   1. Open Supabase SQL Editor")
    print(f"   2. Run: schemas/hitl_requests_schema.sql")
    print()
    print("   Or use Supabase CLI:")
    print("   $ supabase db push")

    # Summary
    print_header("🎉 Setup Complete!")
    print("✅ Bot configured and webhook active")
    print("✅ Environment variables ready")
    print()
    print("📝 Next steps:")
    print("   1. Apply Supabase schema (see Step 7 above)")
    print("   2. Install dependencies: pip install -r requirements.txt")
    print("   3. Restart the proxy server")
    print("   4. Test with a high-value invoice creation")
    print()
    print(f"🔗 Test your bot: https://t.me/{bot_info['username']}")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Setup cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Setup failed: {e}")
