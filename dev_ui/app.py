"""Veeam Presence — Local Dev UI.

Standalone FastAPI app for testing the agent without Teams.
No auth. In-process calls to run_agent(). Renders Adaptive Cards.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

# Load .env from project root
_project_root = os.path.join(os.path.dirname(__file__), "..")
load_dotenv(os.path.join(_project_root, ".env"))

# Ensure project root is on path
sys.path.insert(0, _project_root)

import config
from tools.query_office_intel import load_cache
from tools.query_person import _load_enriched
from response_cache import load_pregenerated

logger = logging.getLogger(__name__)

# In-memory chat sessions
_sessions: dict[str, list[dict]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Dev UI: loading data caches...")
    load_cache()
    _load_enriched()
    load_pregenerated()
    logger.info("Dev UI: caches loaded. Ready.")
    yield


app = FastAPI(title="Veeam Presence Dev UI", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "veeam-presence-dev-ui"}


@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in _sessions:
        session_id = str(uuid.uuid4())
        _sessions[session_id] = []

    messages = _sessions.get(session_id, [])
    html = _render_page(messages, session_id)
    response = HTMLResponse(html)
    response.set_cookie("session_id", session_id)
    return response


@app.post("/chat", response_class=HTMLResponse)
async def chat_submit(request: Request, message: str = Form(...)):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in _sessions:
        session_id = str(uuid.uuid4())
        _sessions[session_id] = []

    messages = _sessions[session_id]
    messages.append({"role": "user", "text": message, "card": None})

    # Call agent in-process
    try:
        from agent.agent import run_agent
        from cards import card_builder
        response_text, _ = await run_agent(message, conversation_id=session_id)

        # Build card server-side from stashed tool results
        card = card_builder.build_card(session_id)

        messages.append({"role": "assistant", "text": response_text, "card": card})
    except Exception as e:
        logger.error("Agent error: %s", e)
        messages.append({"role": "assistant", "text": f"Error: {e}", "card": None})

    html = _render_page(messages, session_id)
    response = HTMLResponse(html)
    response.set_cookie("session_id", session_id)
    return response


@app.post("/chat/reset")
async def chat_reset(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in _sessions:
        del _sessions[session_id]
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session_id")
    return response


def _render_page(messages: list[dict], session_id: str) -> str:
    """Render the full chat page HTML."""
    message_html = ""
    card_init_js = ""
    card_index = 0

    for msg in messages:
        role = msg["role"]
        text = msg.get("text", "")
        card = msg.get("card")

        # Escape HTML in text
        safe_text = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )

        if role == "user":
            message_html += f'<div class="msg user-msg"><div class="bubble user-bubble">{safe_text}</div></div>\n'
        else:
            message_html += f'<div class="msg assistant-msg"><div class="bubble assistant-bubble">{safe_text}</div></div>\n'
            if card:
                card_id = f"card-{card_index}"
                card_json = json.dumps(card)
                message_html += f'<div class="msg assistant-msg"><div class="card-frame" id="{card_id}"></div></div>\n'
                card_init_js += f'renderCard("{card_id}", {card_json});\n'
                card_index += 1

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Veeam Presence — Dev UI</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://unpkg.com/adaptivecards@3.0.0/dist/adaptivecards.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Segoe UI', -apple-system, sans-serif; background: #f0f2f5; height: 100vh; display: flex; flex-direction: column; }}
        .header {{ background: #005f4b; color: white; padding: 14px 20px; display: flex; align-items: center; justify-content: space-between; }}
        .header h1 {{ font-size: 18px; font-weight: 600; }}
        .header .actions {{ display: flex; gap: 10px; }}
        .header form button {{ background: rgba(255,255,255,0.2); color: white; border: none; padding: 6px 14px; border-radius: 4px; cursor: pointer; font-size: 13px; }}
        .header form button:hover {{ background: rgba(255,255,255,0.3); }}
        .chat-area {{ flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 10px; }}
        .msg {{ display: flex; }}
        .user-msg {{ justify-content: flex-end; }}
        .assistant-msg {{ justify-content: flex-start; }}
        .bubble {{ max-width: 70%; padding: 10px 14px; border-radius: 12px; font-size: 14px; line-height: 1.5; word-wrap: break-word; }}
        .user-bubble {{ background: #005f4b; color: white; border-bottom-right-radius: 4px; }}
        .assistant-bubble {{ background: white; color: #333; border-bottom-left-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }}
        .card-frame {{ max-width: 580px; background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); overflow: hidden; }}
        .input-area {{ background: white; border-top: 1px solid #ddd; padding: 12px 20px; }}
        .input-area form {{ display: flex; gap: 10px; }}
        .input-area input {{ flex: 1; padding: 10px 14px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; outline: none; }}
        .input-area input:focus {{ border-color: #005f4b; }}
        .input-area button {{ background: #005f4b; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; }}
        .input-area button:hover {{ background: #004a3a; }}
        .empty-state {{ text-align: center; color: #999; margin-top: 40px; }}
        .empty-state p {{ font-size: 15px; margin-bottom: 8px; }}
        .empty-state .suggestions {{ margin-top: 16px; display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }}
        .empty-state .suggestion {{ background: white; border: 1px solid #ddd; padding: 6px 14px; border-radius: 20px; font-size: 13px; cursor: pointer; color: #005f4b; }}
        .ac-textBlock {{ font-family: 'Segoe UI', sans-serif !important; }}
        .ac-actionSet {{ margin-top: 12px !important; }}
        .ac-pushButton {{ background: #f0f0f0 !important; border: 1px solid #ddd !important; border-radius: 4px !important; padding: 6px 12px !important; font-size: 13px !important; cursor: pointer; }}
        .ac-pushButton:hover {{ background: #e0e0e0 !important; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Veeam Presence</h1>
        <div class="actions">
            <form action="/chat/reset" method="post"><button type="submit">New Chat</button></form>
        </div>
    </div>

    <div class="chat-area" id="chatArea">
        {"" if messages else '''
        <div class="empty-state">
            <p>Ask me about office attendance across Veeam offices.</p>
            <div class="suggestions">
                <div class="suggestion" onclick="fillSuggestion(this)">Give me the daily briefing</div>
                <div class="suggestion" onclick="fillSuggestion(this)">What's going on in Prague?</div>
                <div class="suggestion" onclick="fillSuggestion(this)">Who's trending up?</div>
                <div class="suggestion" onclick="fillSuggestion(this)">Who's traveling between offices?</div>
            </div>
        </div>
        '''}
        {message_html}
    </div>

    <div class="input-area">
        <form action="/chat" method="post">
            <input type="text" name="message" placeholder="Ask about office attendance..." autocomplete="off" autofocus>
            <button type="submit">Send</button>
        </form>
    </div>

    <script>
    const hostConfig = new AdaptiveCards.HostConfig({{
        fontFamily: "Segoe UI, sans-serif",
        supportsInteractivity: true,
        fontSizes: {{ default: 14, small: 12, medium: 16, large: 20, extraLarge: 28 }},
        fontWeights: {{ default: 400, lighter: 300, bolder: 600 }},
        containerStyles: {{
            default: {{
                backgroundColor: "#ffffff",
                foregroundColors: {{
                    default: {{ default: "#333333", subtle: "#888888" }},
                    accent: {{ default: "#005f4b" }},
                    good: {{ default: "#107c10" }},
                    attention: {{ default: "#d83b01" }},
                    warning: {{ default: "#e8912d" }},
                    light: {{ default: "#ffffff" }}
                }}
            }},
            accent: {{
                backgroundColor: "#005f4b",
                foregroundColors: {{
                    default: {{ default: "#ffffff", subtle: "#dddddd" }},
                    light: {{ default: "#ffffff" }}
                }}
            }},
            emphasis: {{
                backgroundColor: "#f7f7f7",
                foregroundColors: {{
                    default: {{ default: "#333333", subtle: "#888888" }}
                }}
            }}
        }},
        actions: {{ actionsOrientation: "horizontal", actionAlignment: "left", spacing: 8, maxActions: 4 }}
    }});

    function renderCard(elementId, cardJson) {{
        try {{
            const card = new AdaptiveCards.AdaptiveCard();
            card.hostConfig = hostConfig;
            card.onExecuteAction = function(action) {{
                // Handle card button clicks — submit as new chat message
                let msg = '';
                if (action.data && action.data.msteams && action.data.msteams.value) {{
                    msg = action.data.msteams.value;
                }} else if (action.title) {{
                    msg = action.title;
                }}
                if (msg) {{
                    const input = document.querySelector('input[name="message"]');
                    input.value = msg;
                    input.closest('form').submit();
                }}
            }};
            card.parse(cardJson);
            const rendered = card.render();
            document.getElementById(elementId).appendChild(rendered);
        }} catch(e) {{
            document.getElementById(elementId).innerHTML = '<p style="color:red">Card render error: ' + e.message + '</p>';
        }}
    }}

    function fillSuggestion(el) {{
        const input = document.querySelector('input[name="message"]');
        input.value = el.textContent;
        input.focus();
    }}

    // Scroll to bottom
    const chatArea = document.getElementById('chatArea');
    chatArea.scrollTop = chatArea.scrollHeight;

    // Render any cards
    {card_init_js}
    </script>
</body>
</html>"""
