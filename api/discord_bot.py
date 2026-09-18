import os
import json
import asyncio
import socket
import urllib.request
import aiohttp
import discord
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

API_URL      = "http://api:8000"
SUPPORT_CHANNEL = "support"

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# track escalated discord users
# { discord_user_id: conversation_id }
escalated_users: dict[str, str] = {}
shown_messages:  dict[str, set] = {}


async def poll_human_replies():
    """Poll for human agent replies every 5 seconds."""
    await client.wait_until_ready()
    while not client.is_closed():
        for user_id, conversation_id in list(escalated_users.items()):
            try:
                connector = aiohttp.TCPConnector(family=socket.AF_INET)
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(
                        f"{API_URL}/messages/{conversation_id}",
                        ssl=False,
                    ) as res:
                        data = await res.json()

                human_msgs = [
                    m for m in data["messages"]
                    if m["role"] == "human_agent"
                ]

                if user_id not in shown_messages:
                    shown_messages[user_id] = set()

                for msg in human_msgs:
                    if msg["content"] not in shown_messages[user_id]:
                        shown_messages[user_id].add(msg["content"])
                        user = await client.fetch_user(int(user_id))
                        await user.send(
                            f"🧑‍💼 **Support Agent:**\n{msg['content']}"
                        )

                # check if resolved
                connector2 = aiohttp.TCPConnector(family=socket.AF_INET)
                async with aiohttp.ClientSession(connector=connector2) as session:
                    async with session.get(
                        f"{API_URL}/conversation/discord_{user_id}",
                        ssl=False,
                    ) as res:
                        conv = await res.json()

                if conv.get("status") in ("resolved", "active"):
                    escalated_users.pop(user_id, None)
                    user = await client.fetch_user(int(user_id))
                    await user.send(
                        "✅ Your case has been resolved. You can continue chatting."
                    )

            except Exception as e:
                logger.error(f"Polling error for {user_id}: {e}")

        await asyncio.sleep(5)


@client.event
async def on_ready():
    logger.success(f"Logged in as {client.user}")
    client.loop.create_task(poll_human_replies())


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

            answer    = data["answer"]
            escalated = data["escalated"]
            logger.debug(f"escalated={escalated}, conversation_id={data.get('conversation_id')}")

            if escalated:
                # track this user as escalated
                escalated_users[str(message.author.id)] = data.get("conversation_id", "")
                shown_messages[str(message.author.id)]  = set()
                response = f"🚨 **Escalated to human support**\n{answer}"
            else:
                # remove from escalated if resolved
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