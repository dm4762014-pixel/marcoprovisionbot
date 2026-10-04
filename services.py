"""Input validation and Telegram delivery, independent of the UI."""
import json
import re
from io import BytesIO
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from PIL import Image, UnidentifiedImageError

class TelegramError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__("Telegram request failed")

def telegram_configuration_errors(token):
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,}", token):
        return ["TELEGRAM_BOT_TOKEN is missing or invalid. Copy the token supplied by @BotFather into the app secrets."]
    return []

def validate_chat_id(value):
    chat_id = str(value).strip()
    if not re.fullmatch(r"-?[1-9][0-9]{0,19}", chat_id):
        raise ValueError("Enter your numeric Telegram chat ID. A phone number or @username is not a chat ID.")
    return chat_id

def validate_image(data):
    if len(data) > 10 * 1024 * 1024:
        raise ValueError("Choose a photo smaller than 10 MB.")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in ("JPEG", "PNG"):
                raise ValueError("Only genuine JPG and PNG photos are supported.")
            mime_type = Image.MIME[image.format]
            image.verify()
            return mime_type
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("This photo could not be read. Upload a valid JPG or PNG.") from error

def clean_recap(text):
    cleaned = " ".join(text.split())
    if not cleaned:
        raise ValueError("The recap is empty. Create a new recap before sending.")
    return cleaned if len(cleaned) <= 1500 else cleaned[:1497] + "..."


def telegram_request(token, method, payload):
    if telegram_configuration_errors(token):
        raise ValueError("Telegram bot token is missing or invalid.")
    request = Request(f"https://api.telegram.org/bot{token}/{method}",
                      data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read())
    except HTTPError as error:
        raise TelegramError(error.code) from None
    except (URLError, TimeoutError, OSError):
        raise TelegramError("connection") from None
    except (ValueError, TypeError):
        raise TelegramError("response") from None
    if not result.get("ok"):
        raise TelegramError(result.get("error_code", "response"))
    return result["result"]

def send_telegram(token, chat_id, name, summary):
    text = f"Hi {name}, here's your Snap & Study revision recap:\n\n{clean_recap(summary)}"
    result = telegram_request(token, "sendMessage", {"chat_id": validate_chat_id(chat_id), "text": text})
    return result["message_id"]

def get_telegram_chats(token):
    updates = telegram_request(token, "getUpdates", {"timeout": 0, "allowed_updates": ["message"]})
    chats = {}
    for update in updates:
        chat = update.get("message", {}).get("chat", {})
        if chat.get("type") == "private" and chat.get("id"):
            chats[str(chat["id"])] = chat.get("first_name", "Telegram user")
    return chats

def friendly_error(error, service="Gemini"):
    # Never expose raw provider exceptions: Telegram URLs contain the bot token.
    code = getattr(error, "code", None)
    if service == "Telegram":
        if code in (401, "401"):
            return "Telegram rejected the bot token. Check TELEGRAM_BOT_TOKEN in the app secrets."
        if code in (400, "400"):
            return "Telegram could not find that chat. Open your bot, send /start, and check the numeric chat ID."
        if code in (403, "403"):
            return "Your bot cannot message this chat. Start or unblock the bot in Telegram, then retry."
        if code in (429, "429"):
            return "Telegram is rate limiting requests. Wait a little before retrying."
        return "Telegram could not confirm sending. Check your connection and the chat before retrying to avoid duplicate messages."
    if code in (429, "429", "RESOURCE_EXHAUSTED"):
        return "Gemini's quota is exhausted. Wait a little, or check the API project's quota and billing, then retry."
    if code in (401, "401"):
        return "Gemini rejected the API credentials (401). Replace GEMINI_API_KEY in .streamlit/secrets.toml with a valid Google AI Studio API key, then restart the app."
    if code in (403, "403"):
        return "Gemini denied access (403). Check the API key's project, restrictions, and permission to use the Gemini API."
    if code in (404, "404"):
        return "The configured Gemini model was not found (404). Set GEMINI_MODEL to a text-and-image model available to your API project."
    if code in (400, "400"):
        return "Gemini rejected the request (400). Check the API key, image format, and whether the configured model supports these inputs."
    return "Couldn't get a response from Gemini. Check your connection and API configuration, then retry."
