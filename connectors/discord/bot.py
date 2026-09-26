import os
import json
import asyncio
import urllib.request
import discord
from datetime import datetime, timezone, timedelta
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

API_URL         = os.getenv("API_URL", "http://api:8000")
SUPPORT_CHANNEL = "support"

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

escalated_users: dict[str, dict] = {}
shown_messages:  dict[str, set]  = {}


async def poll_human_replies():
    logger.info("Polling task started")
    await client.wait_until_ready()
    logger.info("Polling task running")

    while not client.is_closed():
        if escalated_users:
            logger.debug(f"Polling {len(escalated_users)} escalated users")

        for user_id, escalation_data in list(escalated_users.items()):
            try:
                conversation_id = escalation_data["conversation_id"]

                # fetch messages
                req = urllib.request.Request(
                    f"{API_URL}/messages/{conversation_id}?limit=100",
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode())

                # escalated_at is tz-aware, created_at is naive UTC: compare the
                # first 19 chars (YYYY-MM-DDTHH:MM:SS) as strings
                escalated_at_clean = escalation_data["escalated_at"][:19]
                human_msgs = [
                    m for m in data["messages"]
                    if m["role"] == "human_agent"
                    and m["created_at"][:19] > escalated_at_clean
                ]
                logger.debug(
                    f"Found {len(human_msgs)} human messages for {user_id} "
                    f"(conversation {conversation_id})"
                )

                if user_id not in shown_messages:
                    shown_messages[user_id] = set()

                for msg in human_msgs:
                    msg_key = msg["created_at"]
                    if msg_key in shown_messages[user_id]:
                        continue

                    user = await client.fetch_user(int(user_id))
                    await user.send(f"🧑‍💼 **Support Agent:**\n{msg['content']}")
                    shown_messages[user_id].add(msg_key)
                    logger.info(
                        f"Sent DM to {user_id}: {msg['content'][:50]}"
                    )

                # check if resolved
                req2 = urllib.request.Request(
                    f"{API_URL}/conversation/discord_{user_id}",
                    method="GET",
                )
                with urllib.request.urlopen(req2, timeout=10) as r:
                    conv = json.loads(r.read().decode())

                if conv.get("status") in ("resolved", "active"):
                    escalated_users.pop(user_id, None)
                    user = await client.fetch_user(int(user_id))
                    await user.send(
                        "Your case has been resolved. You can continue chatting."
                    )

            except Exception as e:
                logger.error(f"Polling error for {user_id}: {e}")

        await asyncio.sleep(5)


@client.event
async def on_ready():
    logger.success(f"Logged in as {client.user}")
    asyncio.get_event_loop().create_task(poll_human_replies())


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    if not isinstance(message.channel, discord.DMChannel):
        if message.channel.name != SUPPORT_CHANNEL:
            return
        text = message.content.strip()
    else:
        text = message.content.strip()

    if not text:
        return

    logger.info(f"Received message: {text[:50]} from {message.author}")

    async with message.channel.typing():
        try:
            logger.debug(f"Calling API at {API_URL}/chat")

            payload = json.dumps({
                "telegram_chat_id": f"discord_{message.author.id}",
                "message":          text,
                "customer_name":    str(message.author.display_name),
                "channel":          "discord",
            }).encode()

            req = urllib.request.Request(
                f"{API_URL}/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())

            logger.debug(f"API response received: {data.get('answer', '')[:50]}")
            logger.debug(f"escalated={data.get('escalated')}, conversation_id={data.get('conversation_id')}")

            answer    = data["answer"]
            escalated = data["escalated"]

            if escalated:
                conv_id = data.get("conversation_id", "")
                already_tracked = (
                    escalated_users.get(str(message.author.id), {}).get("conversation_id") == conv_id
                )
                if already_tracked:
                    # follow-up during an open escalation: message was forwarded to
                    # the agent, keep the existing tracking state
                    logger.info(f"Forwarded follow-up from {message.author.id} to agent")
                    await message.reply(answer)
                    return
                if conv_id:
                    escalated_users[str(message.author.id)] = {
                        "conversation_id": conv_id,
                        "escalated_at":    datetime.now(timezone.utc).isoformat(),
                    }
                    # mark messages from earlier escalations as already shown
                    already_shown = set()
                    try:
                        req_msgs = urllib.request.Request(
                            f"{API_URL}/messages/{conv_id}",
                            method="GET",
                        )
                        with urllib.request.urlopen(req_msgs, timeout=10) as r:
                            existing = json.loads(r.read().decode())
                            one_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
                        already_shown = {
                        m["created_at"] for m in existing["messages"]
                        if m["role"] == "human_agent"
                        and m["created_at"] < one_min_ago
                    }
                    except Exception as e:
                        logger.error(f"Could not pre-populate shown messages: {e}")
                    shown_messages[str(message.author.id)] = already_shown
                    logger.info(
                        f"Pre-marked {len(already_shown)} old human messages as shown"
                    )
                    logger.info(f"Tracking escalation for {message.author.id}: {conv_id}")
                response = f"🚨 **Escalated to human support**\n{answer}"
            else:
                escalated_users.pop(str(message.author.id), None)
                response = answer

            await message.reply(response)

        except urllib.error.URLError as e:
            logger.error(f"Cannot connect to API: {e}")
            await message.reply("Cannot connect to support system. Please try again.")
        except Exception as e:
            logger.error(f"Error: {type(e).__name__}: {e}")
            await message.reply("Sorry, there was an error processing your request.")


def run_bot():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("DISCORD_BOT_TOKEN not set")
        return
    client.run(token)


if __name__ == "__main__":
    run_bot()
