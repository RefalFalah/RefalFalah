"""Generate the light/dark GitHub profile cards from public GitHub data."""

import io
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps


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


def background_mask(avatar):
    """Build a soft foreground mask by comparing pixels with the avatar corners."""
    width, height = avatar.size
    sample = max(4, min(width, height) // 32)
    corner_pixels = []
    for left, top in ((0, 0), (width - sample, 0), (0, height - sample),
                      (width - sample, height - sample)):
        for y in range(top, top + sample):
            for x in range(left, left + sample):
                corner_pixels.append(avatar.getpixel((x, y)))

    background = tuple(int(median(pixel[channel] for pixel in corner_pixels)) for channel in range(3))
    delta = ImageChops.difference(avatar, Image.new("RGB", avatar.size, background))
    red, green, blue = delta.split()
    distance = ImageChops.lighter(ImageChops.lighter(red, green), blue)

    # Ignore near-black compression noise while keeping the dark jacket and hair.
    mask = distance.point(lambda value: max(0, min(255, (value - 3) * 17)))
    return mask.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.GaussianBlur(0.6))


def crop_to_subject(avatar, mask):
    """Crop tightly around the head and upper torso."""
    bounds = mask.point(lambda value: 255 if value > 24 else 0).getbbox()
    if not bounds:
        return avatar, Image.new("L", avatar.size, 255)

    left, top, right, bottom = bounds
    subject_width = right - left
    subject_height = bottom - top
    centre_x = (left + right) / 2
    crop_width = subject_width * 0.64
    box = (
        max(0, round(centre_x - crop_width / 2)),
        max(0, round(top - subject_height * 0.04)),
        min(avatar.width, round(centre_x + crop_width / 2)),
        min(avatar.height, round(top + subject_height * 0.64)),
    )
    return avatar.crop(box), mask.crop(box)


def enhance_portrait(subject, mask):
    """Lift facial detail without turning dark clothing into a solid character block."""
    grayscale = ImageOps.grayscale(subject)
    grayscale = ImageOps.autocontrast(grayscale, cutoff=(1, 1), mask=mask)
    grayscale = ImageEnhance.Contrast(grayscale).enhance(1.18)
    grayscale = grayscale.point(lambda value: round(255 * ((value / 255) ** 0.82)))

    # Portrait avatars conventionally place the face in the upper-centre region.
    width, height = grayscale.size
    face_box = (round(width * 0.2), round(height * 0.04),
                round(width * 0.8), round(height * 0.62))
    face = grayscale.crop(face_box)
    face = ImageOps.autocontrast(face, cutoff=(1, 1))
    face = ImageEnhance.Contrast(face).enhance(1.38)
    face_blend = Image.new("L", grayscale.size, 0)
    face_blend.paste(255, face_box)
    face_blend = face_blend.filter(ImageFilter.GaussianBlur(max(3, round(width * 0.025))))
    grayscale = Image.composite(
        Image.new("L", grayscale.size, 0),
        grayscale,
        ImageChops.invert(mask),
    )
    face_layer = grayscale.copy()
    face_layer.paste(face, face_box)
    grayscale = Image.composite(face_layer, grayscale, face_blend)

    # Tone down the shirt and jacket so the face remains the visual anchor.
    lower_blend = Image.new("L", grayscale.size, 0)
    lower_pixels = lower_blend.load()
    fade_start = round(height * 0.62)
    for y in range(fade_start, height):
        opacity = round(255 * (y - fade_start) / max(1, height - fade_start))
        for x in range(width):
            lower_pixels[x, y] = opacity
    darker_body = ImageEnhance.Brightness(grayscale).enhance(0.7)
    grayscale = Image.composite(darker_body, grayscale, lower_blend)
    grayscale = grayscale.filter(ImageFilter.UnsharpMask(radius=1.4, percent=135, threshold=3))

    # A light posterization makes tonal groups survive the tiny terminal grid.
    return grayscale.point(
        lambda value: 0 if value < 14 else 255 if value > 242 else (value // 24) * 24
    )


def avatar_art():
    """Turn the public GitHub avatar into a face-first terminal ASCII portrait."""
    avatar = Image.open(io.BytesIO(fetch(f"https://github.com/{USERNAME}.png?size=512"))).convert("RGB")
    mask = background_mask(avatar)
    subject, mask = crop_to_subject(avatar, mask)
    portrait = enhance_portrait(subject, mask)

    columns = 38
    character_aspect = 0.54  # Consolas glyph width relative to the 16 px line height.
    rows = min(25, max(18, round(subject.height / subject.width * columns * character_aspect)))
    size = (columns, rows)
    portrait = portrait.resize(size, Image.Resampling.LANCZOS)
    mask = mask.resize(size, Image.Resampling.LANCZOS)
    edges = portrait.filter(ImageFilter.FIND_EDGES)

    # Low luminance now means whitespace; brighter facial features carry denser glyphs.
    shades = " .:-=+*#%@"
    pixels = portrait.tobytes()
    mask_pixels = mask.tobytes()
    edge_pixels = edges.tobytes()
    lines = []
    for y in range(rows):
        line = []
        for x in range(columns):
            index = y * columns + x
            if mask_pixels[index] < 52:
                character = " "
            else:
                shade = min(len(shades) - 1, pixels[index] * len(shades) // 256)
                character = shades[shade]
                if character == " ":
                    if edge_pixels[index] > 42 or (
                        mask_pixels[index] > 150 and (x + 2 * y) % 3 == 0
                    ):
                        character = "."
            line.append(character)
        lines.append("".join(line).rstrip())
    return lines


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
        text(432, 399, "- Contact", p["text"], 15, "bold"),
        text(529, 399, "────────────────────────────────────", p["border"]),
        row(428, "Website", "refalfalah.site", p),
        row(454, "Email", "refalfalah10@gmail.com", p),
        text(432, 503, "- GitHub Stats", p["text"], 15, "bold"),
        text(558, 503, "────────────────────────────────", p["border"]),
        row(532, "Repos", f"{stats[0]}  |  Stars: {stats[2]}", p),
        row(558, "Followers", str(stats[1]), p),
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
