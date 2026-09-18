import os
from socket import socket
import aiohttp
import discord
from loguru import logger
from dotenv import load_dotenv
import socket

load_dotenv()

API_URL = "http://api:8000"

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
SUPPORT_CHANNEL = "support"


@client.event
async def on_ready():
    logger.success(f"Logged in as {client.user}")


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

            import json
            import urllib.request
            
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

            import asyncio
            loop = asyncio.get_event_loop()
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())

            logger.debug(f"API response received")

            answer    = data["answer"]
            escalated = data["escalated"]

            if escalated:
                response = f"🚨 **Escalated to human support**\n{answer}"
            else:
                response = answer

            await message.reply(response)

        except aiohttp.ClientConnectorError as e:
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