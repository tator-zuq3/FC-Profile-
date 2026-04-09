import json
import os
import requests
from io import BytesIO
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
NEYNAR_API_KEY = os.getenv("NEYNAR_API_KEY")
NEYNAR_BASE = "https://api.neynar.com/v2/farcaster"

# ── Neynar API helpers ──────────────────────────────────────────────

def _neynar_get(path, params=None):
    """GET wrapper for Neynar API v2."""
    url = f"{NEYNAR_BASE}/{path}"
    headers = {"x-api-key": NEYNAR_API_KEY}
    print(f"\n🔗 GET {url}")
    print(f"📤 Params: {params}")
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        print(f"📥 Status: {resp.status_code}")
        print(f"📥 Preview: {resp.text[:300]}")
        if resp.status_code == 200:
            return resp.json()
        else:
            return {"error": f"API error: {resp.status_code}", "detail": resp.text}
    except Exception as e:
        return {"error": "Exception during API call", "detail": str(e)}


def fetch_by_fid(fid):
    """GET /v2/farcaster/user/bulk?fids=..."""
    return _neynar_get("user/bulk", {"fids": str(fid)})


def fetch_by_username(username):
    """GET /v2/farcaster/user/by_username?username=..."""
    return _neynar_get("user/by_username", {"username": username})


def fetch_by_wallet(addresses):
    """GET /v2/farcaster/user/bulk-by-address?addresses=..."""
    csv = ",".join(addresses)
    return _neynar_get("user/bulk-by-address", {"addresses": csv})


def fetch_by_x_username(x_username):
    """GET /v2/farcaster/user/by_x_username?x_username=..."""
    return _neynar_get("user/by_x_username", {"x_username": x_username})


# ── Telegram handler ────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text.strip()
    lines = message.splitlines()

    fids = []
    x_usernames = []     # @handle → X lookup
    usernames = []
    wallets = []

    for line in lines:
        text = line.strip()
        if not text:
            continue
        # Detect X (Twitter) handle: starts with @
        if text.startswith("@") and len(text) >= 2:
            x_usernames.append(text[1:])  # strip @
        elif text.isdigit() and len(text) <= 10:
            fids.append(int(text))
        elif len(text) <= 20:
            usernames.append(text.lower())
        else:
            wallets.append(text.lower())

    # ── Handle FID ──────────────────────────────────────────────
    if fids:
        if len(fids) > 1:
            await update.message.reply_text("⚠️ Please query **only 1 FID at a time**.")
        else:
            fid = fids[0]
            await update.message.reply_text(f"🔍 Looking up FID: {fid}", parse_mode='Markdown')
            result = fetch_by_fid(fid)

            if "error" in result:
                await update.message.reply_text(f"⚠️ Error: {result['error']}\n{result.get('detail','')}")
                return

            users = result.get("users", [])
            if not users:
                await update.message.reply_text(f"❌ No user found for FID `{fid}`", parse_mode='Markdown')
                return

            user = users[0]
            fname = user.get("username", "N/A")
            username = user.get("username", "N/A")
            eth_addrs = user.get("verified_addresses", {}).get("eth_addresses", [])
            addresses_text = "\n".join(f"`{addr}`" for addr in eth_addrs) if eth_addrs else "None found"

            await update.message.reply_text(
                f"📬 FID `{fid}` details:\n"
                f"- fname: `{fname}`\n"
                f"- username: `{username}`\n"
                f"- addresses:\n{addresses_text}",
                parse_mode='Markdown'
            )

    # ── Handle Username ─────────────────────────────────────────
    if usernames:
        if len(usernames) > 1:
            await update.message.reply_text("⚠️ Please query **only 1 username at a time**.")
        else:
            username = usernames[0]
            await update.message.reply_text(f"🔍 Looking up username: {username}", parse_mode='Markdown')
            result = fetch_by_username(username)

            if "error" in result:
                await update.message.reply_text(f"⚠️ Error: {result['error']}\n{result.get('detail','')}")
                return

            user = result.get("user", {})
            if not user:
                await update.message.reply_text(f"❌ No user found for username `{username}`", parse_mode='Markdown')
                return

            fname = user.get("username", "N/A")
            fid = user.get("fid", "N/A")
            eth_addrs = user.get("verified_addresses", {}).get("eth_addresses", [])
            addresses_text = "\n".join(f"`{addr}`" for addr in eth_addrs) if eth_addrs else "None found"

            await update.message.reply_text(
                f"📬 Username `{username}` details:\n"
                f"- fname: `{fname}`\n"
                f"- fid: `{fid}`\n"
                f"- addresses:\n{addresses_text}",
                parse_mode='Markdown'
            )

    # ── Handle X (Twitter) Username ─────────────────────────────
    if x_usernames:
        if len(x_usernames) > 1:
            await update.message.reply_text("⚠️ Please query **only 1 X username at a time**.")
        else:
            x_handle = x_usernames[0]
            await update.message.reply_text(f"🔍 Looking up X username: @{x_handle}", parse_mode='Markdown')
            result = fetch_by_x_username(x_handle)

            if "error" in result:
                await update.message.reply_text(f"⚠️ Error: {result['error']}\n{result.get('detail','')}")
                return

            users = result.get("users", [])
            if not users:
                await update.message.reply_text(f"❌ No Farcaster user found linked to X @{x_handle}")
                return

            blocks = []
            for user in users:
                fid_val = user.get("fid", "N/A")
                fname = user.get("username", "N/A")
                display_name = user.get("display_name", "N/A")
                eth_addrs = user.get("verified_addresses", {}).get("eth_addresses", [])
                addresses_text = "\n".join(f"`{addr}`" for addr in eth_addrs) if eth_addrs else "None found"
                username_url = f"https://farcaster.xyz/{fname}" if fname != "N/A" else "N/A"

                block = (
                    f"*fid:* `{fid_val}`\n"
                    f"*display\\_name:* `{display_name}`\n"
                    f"*username:* {username_url}\n"
                    f"*addresses:*\n{addresses_text}"
                )
                blocks.append(block)

            body = f"📬 X @{x_handle} → Farcaster:\n" + "\n------\n".join(blocks)

            if len(body) > 3500:
                buffer = BytesIO(body.encode("utf-8"))
                buffer.seek(0)
                await update.message.reply_document(
                    document=buffer,
                    filename="x_lookup_result.txt",
                    caption=f"📬 X @{x_handle} → Farcaster (attached file)"
                )
            else:
                await update.message.reply_text(body, parse_mode='Markdown')

    # ── Handle Wallets ──────────────────────────────────────────
    if wallets:
        await update.message.reply_text(f"🔍 Looking up {len(wallets)} wallet address(es)...", parse_mode='Markdown')
        result_wallet = fetch_by_wallet(wallets)

        try:
            if "error" in result_wallet:
                await update.message.reply_text(f"⚠️ Error: {result_wallet['error']}\n{result_wallet.get('detail','')}")
                return

            # Neynar returns dict keyed by address → list of users
            blocks = []
            for addr_key, user_list in result_wallet.items():
                if not isinstance(user_list, list):
                    continue
                for item in user_list:
                    address = addr_key
                    fname = item.get("username", "N/A")
                    username_raw = item.get("username", "")
                    fid_val = item.get("fid", "N/A")

                    username_url = f"https://farcaster.xyz/{username_raw}" if username_raw else "N/A"

                    block = (
                        f"*address:* `{address}`\n"
                        f"*fname:* `{fname}`\n"
                        f"*username:* {username_url}\n"
                        f"*fid:* `{fid_val}`"
                    )
                    blocks.append(block)

            if blocks:
                body = "📬 Wallet result:\n" + "\n------\n".join(blocks)

                if len(body) > 3500:
                    payload = "\n------\n".join(blocks)
                    buffer = BytesIO(payload.encode("utf-8"))
                    buffer.seek(0)
                    await update.message.reply_document(
                        document=buffer,
                        filename="wallet_result.txt",
                        caption="📬 Wallet result (attached file)"
                    )
                else:
                    await update.message.reply_text(body, parse_mode='Markdown')
            else:
                result_text = json.dumps(result_wallet, indent=2, ensure_ascii=False)
                if len(result_text) > 3500:
                    buffer = BytesIO(result_text.encode("utf-8"))
                    buffer.seek(0)
                    await update.message.reply_document(
                        document=buffer,
                        filename="wallet_result.json",
                        caption="📬 Wallet result (attached file)"
                    )
                else:
                    await update.message.reply_text(f"📬 Wallet result:\n```json\n{result_text}\n```", parse_mode='Markdown')

        except Exception as e:
            try:
                result_text = json.dumps(result_wallet, indent=2, ensure_ascii=False)
                if len(result_text) > 3500:
                    buffer = BytesIO(result_text.encode("utf-8"))
                    buffer.seek(0)
                    await update.message.reply_document(
                        document=buffer,
                        filename="wallet_result.json",
                        caption="📬 Wallet result (attached file)"
                    )
                else:
                    await update.message.reply_text(f"📬 Wallet result:\n```json\n{result_text}\n```", parse_mode='Markdown')
            except Exception as e2:
                await update.message.reply_text(f"⚠️ Error while parsing wallet response.\n{str(e)}\n{str(e2)}")

    if not fids and not usernames and not wallets and not x_usernames:
        await update.message.reply_text("⚠️ No valid input detected.")

# ── Run bot ─────────────────────────────────────────────────────────
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    app.add_handler(handler)
    print("🤖 Bot is running!")
    app.run_polling()