"""Generate the light/dark GitHub profile cards from public GitHub data."""

import io
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

from PIL import Image, ImageOps


USERNAME = "RefalFalah"
ROOT = Path(__file__).resolve().parent
PALETTES = {
    "light": {
        "background": "#f6f8fa",
        "surface": "#ffffff",
        "border": "#d0d7de",
        "text": "#24292f",
        "muted": "#57606a",
        "key": "#953800",
        "value": "#0a3069",
        "accent": "#1a7f37",
        "art": "#3d6a5a",
    },
    "dark": {
        "background": "#0d1117",
        "surface": "#161b22",
        "border": "#30363d",
        "text": "#e6edf3",
        "muted": "#8b949e",
        "key": "#ffa657",
        "value": "#a5d6ff",
        "accent": "#3fb950",
        "art": "#86c8a4",
    },
}


def fetch(url):
    headers = {"User-Agent": "RefalFalah-profile-generator", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urlopen(Request(url, headers=headers), timeout=20) as response:
        return response.read()


def github_stats():
    import json

    user = json.loads(fetch(f"https://api.github.com/users/{USERNAME}"))
    stars = 0
    page = 1
    while True:
        repos = json.loads(fetch(f"https://api.github.com/users/{USERNAME}/repos?per_page=100&page={page}"))
        stars += sum(repo["stargazers_count"] for repo in repos if not repo["fork"])
        if len(repos) < 100:
            break
        page += 1
    return user["public_repos"], user["followers"], stars


def avatar_art():
    """Turn the public GitHub avatar into a small terminal-style ASCII portrait."""
    avatar = Image.open(io.BytesIO(fetch(f"https://github.com/{USERNAME}.png?size=256"))).convert("RGB")
    avatar = ImageOps.fit(avatar, (38, 25))
    avatar = ImageOps.grayscale(avatar)
    shades = "@%#*+=-:. "
    pixels = avatar.tobytes()
    return ["".join(shades[min(pixel * len(shades) // 256, len(shades) - 1)] for pixel in pixels[y * 38:(y + 1) * 38])
            for y in range(25)]


def text(x, y, value, color, size=15, weight="normal", extra=""):
    return (f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
            f'font-weight="{weight}" {extra}>{escape(str(value))}</text>')


def row(y, label, value, palette):
    return (text(432, y, ".", palette["muted"]) +
            text(451, y, label, palette["key"]) +
            text(608, y, value, palette["value"]))


def render(mode, stats, portrait, generated):
    p = PALETTES[mode]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="600" viewBox="0 0 1040 600" '
        'role="img" aria-labelledby="title desc">',
        '<title id="title">Refal Falah Fadhilah | Fullstack Developer</title>',
        '<desc id="desc">Terminal-inspired profile featuring an ASCII portrait, developer stack, '
        'contact information and GitHub statistics.</desc>',
        '<style>text{font-family:Consolas,"Liberation Mono",Menlo,monospace;white-space:pre}</style>',
        f'<rect width="1040" height="600" rx="18" fill="{p["background"]}"/>',
        f'<rect x="16" y="16" width="1008" height="568" rx="12" fill="{p["surface"]}" '
        f'stroke="{p["border"]}"/>',
        f'<line x1="406" y1="42" x2="406" y2="552" stroke="{p["border"]}"/>',
        text(43, 58, "refal@github:~", p["accent"], 16, "bold"),
        text(43, 82, "./whoami --portrait", p["muted"], 13),
    ]

    for index, line in enumerate(portrait):
        parts.append(text(43, 114 + index * 16, line, p["art"], 14))

    parts.extend([
        text(43, 541, "BUILD  /  DEBUG  /  DEPLOY", p["accent"], 14, "bold"),
        text(432, 65, "refal@github", p["text"], 19, "bold"),
        text(432, 88, "──────────────────────────────────────────", p["border"], 15),
        row(120, "Name", "Refal Falah Fadhilah", p),
        row(146, "Role", "Fullstack Developer", p),
        row(172, "Location", "Bandung, Indonesia", p),
        row(198, "Focus", "Web apps & reliable systems", p),
        text(432, 239, "- Tech Stack", p["text"], 15, "bold"),
        text(548, 239, "─────────────────────────────────", p["border"]),
        row(268, "Backend", "PHP, Laravel, REST APIs", p),
        row(294, "Frontend", "JavaScript, React, Tailwind", p),
        row(320, "Database", "MySQL, PostgreSQL", p),
        row(346, "Infra", "Linux, Nginx, AWS EC2", p),
        row(372, "Platforms", "WordPress, Moodle", p),
        text(432, 413, "- Contact", p["text"], 15, "bold"),
        text(529, 413, "────────────────────────────────────", p["border"]),
        row(442, "Website", "refalfalah.site", p),
        row(468, "Email", "refalfalah10@gmail.com", p),
        text(432, 509, "- GitHub Stats", p["text"], 15, "bold"),
        text(558, 509, "────────────────────────────────", p["border"]),
        row(538, "Repos", f"{stats[0]}  |  Stars: {stats[2]}", p),
        row(564, "Followers", str(stats[1]), p),
        text(43, 568, f"updated {generated}", p["muted"], 12),
        "</svg>\n",
    ])
    return "\n".join(parts)


def main():
    stats = github_stats()
    portrait = avatar_art()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d UTC")
    for mode in PALETTES:
        (ROOT / f"{mode}_mode.svg").write_text(render(mode, stats, portrait, generated), encoding="utf-8")
    print(f"Generated profile cards: {stats[0]} repos, {stats[1]} followers, {stats[2]} stars")


if __name__ == "__main__":
    main()
