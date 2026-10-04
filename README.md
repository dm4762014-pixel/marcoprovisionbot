# Snap & Study

A Streamlit study companion powered by Gemini text and vision. Upload a question,
diagram, or notes, ask follow-ups, practise with hints/quizzes, then review and
send a revision recap to Telegram.

## Run locally

Use Python 3.12 or newer. In Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
# Edit secrets.toml; don't replace an existing configured file.
.\venv\Scripts\python.exe -m streamlit run app.py
```

On macOS/Linux, use python3 and venv/bin/python. Configure GEMINI_API_KEY from
[Google AI Studio](https://aistudio.google.com/apikey). GEMINI_MODEL defaults to
gemini-3.5-flash and can be changed to a text-and-image model available to your key.

## Connect Telegram

1. Open [@BotFather](https://t.me/BotFather) in Telegram, send /newbot, and follow
   its instructions. Save the supplied token as TELEGRAM_BOT_TOKEN in your private
   .streamlit/secrets.toml. Never put it in the repository or browser address bar.
2. Open your new bot in Telegram and press Start or send /start. Bots cannot
   initiate a private conversation before a user contacts them.
3. Run the local helper to find recent private chat IDs:

```powershell
.\venv\Scripts\python.exe telegram_setup.py
```

4. Enter your name and numeric Telegram chat ID in the app. A phone number or
   @username is not a chat ID. Choose your own chat from the helper output.
5. Ask a study question or upload a JPG/PNG, create a recap, review it, and click
   Send recap to Telegram. The recap and your name are sent to that chat.

The helper reads recent bot messages without consuming them. If no chat appears,
send /start again. A bot configured with a webhook cannot use getUpdates at the
same time; use a dedicated bot for this app. The app uses Python's built-in HTTP
client and requires no Telegram SDK. See the [Bot API](https://core.telegram.org/bots/api)
and [bot FAQ](https://core.telegram.org/bots/faq).

## Features and privacy

- Text/photo chat with memory for the browser session.
- Step-by-step explanations, hints, and one-question quizzes.
- JPG/PNG validation and a 10 MB upload limit.
- Scoped academic prompts that request clearer photos when content is unreadable.
- Recap preview, download, and Telegram sending with duplicate-send protection.
- Specific authentication errors and explicit retry/discard for failed questions.

Gemini receives questions/photos. Telegram receives the recap, name, and selected
chat ID only when you click Send. The app stores conversations in session state,
not a database. AI answers may be wrong; verify them against course materials.
Recaps are limited to 1,500 characters. API quotas apply. A successful Telegram
API response confirms message creation, not that the recipient has read it.

## Tests

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Eight automated checks cover onboarding/reset, text/photo history, retries,
recap generation, chat/image validation, Telegram payload, and safe errors.
Google and Telegram are mocked; actual Telegram receipt needs a live test.

## Deploy and submit

1. Publish this project to a public/shared GitHub repository. Include app.py,
   prompts.py, services.py, telegram_setup.py, requirements.txt, README.md,
   .gitignore, tests/, .streamlit/config.toml, and secrets.toml.example.
2. Never commit .streamlit/secrets.toml. The ignore file also excludes local
   environments, bytecode, logs, and artifacts/.
3. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/), create an
   app from your repository and app.py, and select Python 3.12 or newer.
4. Add GEMINI_API_KEY, GEMINI_MODEL, and TELEGRAM_BOT_TOKEN to the app's private
   Secrets settings. Deploy and test the input ? AI response ? Telegram flow.
5. Submit the repository and deployed app URLs through the
   [assignment form](https://forms.ccbp.in/ai-vision-chatbot-last-project-submission).

The guide allows Telegram as the action tool and states 4 October, 11:59 PM as
the deadline, without specifying year/timezone.
