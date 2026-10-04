"""Snap & Study: visual tutoring and a Telegram revision recap."""
import streamlit as st
from google import genai
from google.genai import types
from prompts import SYSTEM_PROMPT, WELCOME_MESSAGE_TEMPLATE, PHOTO_PROMPT, SUMMARY_REQUEST_PROMPT
from services import validate_chat_id, validate_image, clean_recap, send_telegram, friendly_error, telegram_configuration_errors

st.set_page_config(page_title="Snap & Study", page_icon="📚")
st.title("Snap & Study", icon=":material/school:")
st.caption("Turn a confusing page into a clear explanation and a revision plan.")

def setting(name, default=""):
    try:
        return str(st.secrets.get(name, default)).strip()
    except FileNotFoundError:
        return default

@st.cache_resource
def get_gemini_client(api_key):
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=60000))

def render_message(message):
    with st.chat_message(message["role"]):
        if message.get("image"):
            st.image(message["image"], width="stretch")
        if message.get("text"):
            st.markdown(message["text"])

def reset_session():
    for key in ("onboarded", "name", "telegram_chat_id", "whatsapp_number", "history", "messages", "summary", "sent_summary", "pending"):
        st.session_state.pop(key, None)

api_key = setting("GEMINI_API_KEY")
if not api_key:
    st.info("Add GEMINI_API_KEY to .streamlit/secrets.toml to start studying. See README.md for setup.")
    st.stop()
model = setting("GEMINI_MODEL", "gemini-3.5-flash")
client = get_gemini_client(api_key)
telegram_token = setting("TELEGRAM_BOT_TOKEN")
telegram_errors = telegram_configuration_errors(telegram_token)
telegram_ready = not telegram_errors
# Existing WhatsApp sessions must collect the new Telegram destination.
if st.session_state.get("onboarded") and "telegram_chat_id" not in st.session_state:
    reset_session()

if not st.session_state.get("onboarded"):
    with st.container(border=True):
        st.subheader("Your next study session starts here")
        st.markdown("Upload a question, diagram, or handwritten notes. Ask follow-ups, practise with a quiz, then save a recap to Telegram.")
        with st.form("onboarding"):
            name = st.text_input("Your name", max_chars=60)
            chat_id = st.text_input("Telegram chat ID", placeholder="123456789", max_chars=20, help="Start your Telegram bot first. See the setup guide below to find your numeric chat ID.")
            with st.expander("How to connect Telegram"):
                st.markdown("Create a bot with @BotFather, save its token in the app secrets, then open your bot and send /start. Run the chat ID helper described in README.md and paste your chat ID here.")
            consent = st.checkbox("I agree to send my questions and photos to Google Gemini for explanations.")
            submitted = st.form_submit_button("Start studying", type="primary", width="stretch", key="onboard_submit")
        if submitted:
            try:
                if not name.strip():
                    raise ValueError("Please enter your name.")
                normalized = validate_chat_id(chat_id)
                if not consent:
                    raise ValueError("Please agree to the AI processing notice to continue.")
                st.session_state.update(onboarded=True, name=name.strip(), telegram_chat_id=normalized,
                                        history=[], messages=[], summary="", sent_summary="", pending=None)
                st.session_state.messages.append({"role": "assistant", "text": WELCOME_MESSAGE_TEMPLATE.format(name=name.strip())})
                st.rerun()
            except ValueError as error:
                st.warning(str(error))
    st.caption("Use clear JPG or PNG photos under 10 MB. Conversations last for this browser session; download a recap before leaving.")
    st.stop()

with st.sidebar:
    st.header("Your study space")
    st.markdown(f"Welcome, **{st.session_state.name}**")
    st.caption(f"Telegram chat: {st.session_state.telegram_chat_id}")
    study_mode = st.selectbox("Learning mode", ["Explain step by step", "Give me a hint", "Quiz me"], key="study_mode")
    st.caption("AI explanations can contain mistakes. Check important answers against your course materials.")
    if st.button("Start a new session", icon=":material/refresh:", key="reset"):
        reset_session()
        st.rerun()
for message in st.session_state.messages:
    render_message(message)
if not st.session_state.history:
    st.caption("Try: “Explain Newton’s second law with an example” or attach a photo of a question.")

submission = st.chat_input("Ask a study question or attach a photo", accept_file=True,
                           file_type=["jpg", "jpeg", "png"], max_upload_size=10,
                           disabled=bool(st.session_state.pending), key="study_input")
if submission and not st.session_state.pending:
    text = submission.text.strip()
    image = submission.files[0].getvalue() if submission.files else None
    try:
        mime_type = validate_image(image) if image else None
        if len(text) > 12000:
            raise ValueError("Please keep your question under 12,000 characters.")
        if text or image:
            st.session_state.pending = {"text": text or PHOTO_PROMPT, "image": image, "mime_type": mime_type, "mode": study_mode, "attempt": True}
            st.rerun()
    except ValueError as error:
        st.warning(str(error))

if st.session_state.pending and st.session_state.pending.get("attempt", True):
    pending = st.session_state.pending
    render_message({"role": "user", **pending})
    parts = []
    if pending["image"]:
        parts.append(types.Part.from_bytes(data=pending["image"], mime_type=pending["mime_type"]))
    parts.append(types.Part.from_text(text=f"Learning mode: {pending['mode']}\n\n{pending['text']}"))
    content = types.Content(role="user", parts=parts)
    try:
        with st.spinner("Working through your question..."):
            response = client.models.generate_content(model=model, contents=[*st.session_state.history, content],
                         config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT))
            answer = (response.text or "").strip()
            if not answer:
                raise ValueError("Empty response")
        st.session_state.history.extend([content, types.Content(role="model", parts=[types.Part.from_text(text=answer)])])
        st.session_state.messages.extend([{"role": "user", "text": pending["text"], "image": pending["image"]},
                                          {"role": "assistant", "text": answer}])
        st.session_state.update(pending=None, summary="", sent_summary="")
        st.rerun()
    except Exception as error:
        st.session_state.pending.update(attempt=False, error=friendly_error(error))
        st.rerun()

if st.session_state.pending and not st.session_state.pending.get("attempt", True):
    render_message({"role": "user", **st.session_state.pending})
    st.error(st.session_state.pending["error"])
    retry, discard = st.columns(2)
    if retry.button("Retry question", width="stretch", key="retry"):
        st.session_state.pending["attempt"] = True
        st.rerun()
    if discard.button("Discard question", width="stretch", key="discard"):
        st.session_state.pending = None
        st.rerun()

with st.container(border=True):
    st.subheader("Take your learning with you", icon=":material/bookmark:")
    if st.button("Create revision recap", disabled=not st.session_state.history or bool(st.session_state.pending),
                 icon=":material/summarize:", width="stretch", key="recap"):
        try:
            with st.spinner("Preparing your revision recap..."):
                # Separate request keeps recap instructions out of the tutoring history.
                response = client.models.generate_content(model=model,
                    contents=[*st.session_state.history, types.Content(role="user", parts=[types.Part.from_text(text=SUMMARY_REQUEST_PROMPT)])],
                    config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT))
                st.session_state.summary = clean_recap(response.text or "")
        except Exception as error:
            st.error(friendly_error(error))
    if st.session_state.summary:
        st.text(st.session_state.summary)
        st.download_button("Download recap", st.session_state.summary, "snap-and-study-recap.txt", "text/plain", icon=":material/download:")
        st.caption(f"Send this recap and your name to Telegram chat {st.session_state.telegram_chat_id} through your bot.")
        sent = st.session_state.sent_summary == st.session_state.summary
        if st.button("Send recap to Telegram", disabled=not telegram_ready or sent, type="primary", icon=":material/send:", key="send"):
            try:
                with st.spinner("Sending your recap..."):
                    message_id = send_telegram(telegram_token, st.session_state.telegram_chat_id, st.session_state.name, st.session_state.summary)
                st.session_state.sent_summary = st.session_state.summary
                st.success(f"Telegram accepted your recap in the selected chat. Message reference: {message_id}")
            except Exception as error:
                st.error(friendly_error(error, service="Telegram"))
        if sent:
            st.caption("This recap has already been sent to Telegram.")
    if not telegram_ready:
        st.caption("Add your Telegram bot token to enable sending. You can study and download recaps now.")
        with st.expander("Telegram setup needed"):
            for issue in telegram_errors:
                st.markdown(f"- {issue}")
