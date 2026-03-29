"""Build a self-contained HTML preview with all card JSON embedded inline."""

import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from cards.generate_samples import (
    briefing_data, office_data, leaderboard_data, person_data,
    comparison_offices, trending_data, visitors_data, who_was_in_data,
)
from cards.templates import (
    briefing_card, office_detail_card, leaderboard_card, person_card,
    comparison_card, trending_card, visitors_card, who_was_in_card,
    welcome_card, error_card,
)

cards = [
    ("Welcome", welcome_card()),
    ("Daily Briefing", briefing_card(briefing_data)),
    ("Office Detail — Prague", office_detail_card(office_data)),
    ("Leaderboard — Atlanta", leaderboard_card(leaderboard_data)),
    ("Person — Thomas Murphy", person_card(person_data)),
    ("Comparison", comparison_card(comparison_offices)),
    ("Trending Up", trending_card(trending_data)),
    ("Cross-Office Travel", visitors_card(visitors_data)),
    ("Who Was In — Seattle", who_was_in_card(who_was_in_data)),
    ("Error State", error_card("Having trouble reaching the data warehouse. Usually resolves in a few minutes.")),
]

# Build inline JS data
cards_js = ",\n".join(
    f'  ["{label}", {json.dumps(card)}]'
    for label, card in cards
)

html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Veeam Presence — Card Preview</title>
    <script src="https://unpkg.com/adaptivecards@3.0.0/dist/adaptivecards.min.js"></script>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; margin: 0; padding: 20px; }}
        h1 {{ text-align: center; color: #005f4b; margin-bottom: 5px; }}
        .subtitle {{ text-align: center; color: #888; margin-bottom: 30px; }}
        .card-wrapper {{ max-width: 580px; margin: 0 auto 30px; }}
        .card-label {{ font-size: 11px; color: #999; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 6px; font-weight: 600; }}
        .card-frame {{ background: #fff; border-radius: 6px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.08); overflow: hidden; }}
        .ac-textBlock {{ font-family: 'Segoe UI', sans-serif !important; }}
        .ac-actionSet {{ margin-top: 12px !important; }}
        .ac-pushButton {{ background: #f0f0f0 !important; border: 1px solid #ddd !important; border-radius: 4px !important; padding: 6px 12px !important; font-size: 13px !important; cursor: pointer; }}
        .ac-pushButton:hover {{ background: #e0e0e0 !important; }}
    </style>
</head>
<body>
    <h1>Veeam Presence</h1>
    <p class="subtitle">Adaptive Card Preview — 10 templates as they appear in Microsoft Teams</p>
    <div id="cards"></div>
    <script>
    const allCards = [
{cards_js}
    ];

    const container = document.getElementById("cards");

    allCards.forEach(([label, json]) => {{
        const wrapper = document.createElement("div");
        wrapper.className = "card-wrapper";
        wrapper.innerHTML = '<div class="card-label">' + label + '</div><div class="card-frame"><div class="card-render"></div></div>';
        container.appendChild(wrapper);

        try {{
            const card = new AdaptiveCards.AdaptiveCard();
            card.hostConfig = new AdaptiveCards.HostConfig({{
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
                actions: {{
                    actionsOrientation: "horizontal",
                    actionAlignment: "left",
                    spacing: 8,
                    maxActions: 4
                }}
            }});
            card.parse(json);
            const rendered = card.render();
            wrapper.querySelector(".card-render").appendChild(rendered);
        }} catch(e) {{
            wrapper.querySelector(".card-render").innerHTML = '<p style="color:red">Render error: ' + e.message + '</p>';
        }}
    }});
    </script>
</body>
</html>"""

out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "card_preview.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Preview saved to {out_path}")
print("Open in browser to see all 10 cards")
