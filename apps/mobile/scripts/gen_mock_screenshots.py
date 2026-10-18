"""Generate the synthetic browser screenshots used by mock mode (assets/mock/step-*.png)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "assets" / "mock"
W, H = 640, 400


def font(size):
    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def frame(url, title):
    img = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 44], fill="#eceef3")
    for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        d.ellipse([14 + i * 18, 16, 26 + i * 18, 28], fill=c)
    d.rounded_rectangle([80, 10, W - 16, 34], radius=12, fill="#ffffff")
    d.text((94, 14), url, fill="#4b5563", font=font(13))
    d.text((24, 60), title, fill="#111827", font=font(20))
    return img, d


def miniwob(step):
    img, d = frame("localhost:8000/miniwob/click-test.html", "Click the button labelled “Submit”.")
    d.rectangle([24, 96, W - 24, H - 24], outline="#d1d5db", width=2)
    d.text((44, 116), "Task form", fill="#6b7280", font=font(14))
    for i, label in enumerate(("Name", "Email")):
        y = 146 + i * 50
        d.text((44, y + 6), label, fill="#374151", font=font(14))
        d.rounded_rectangle([130, y, 420, y + 32], radius=6, outline="#9ca3af", width=2)
        if step >= 2 + i:
            d.text((140, y + 7), ("Ada Lovelace", "ada@side.dev")[i], fill="#111827", font=font(14))
    bx = [130, 262, 260, 302]
    pressed = step >= 4
    d.rounded_rectangle(bx, radius=8, fill="#4338ca" if pressed else "#6366f1")
    d.text((166, 272), "Submit", fill="#ffffff", font=font(15))
    if step in (1, 3):
        target = [126, 142, 424, 182] if step == 1 else bx
        d.rectangle([target[0] - 4, target[1] - 4, target[2] + 4, target[3] + 4], outline="#f59e0b", width=3)
        d.text((target[2] + 10, target[1]), "bid=a12" if step == 1 else "bid=a31", fill="#b45309", font=font(13))
    if pressed:
        d.rounded_rectangle([450, 262, W - 44, 302], radius=8, fill="#dcfce7")
        d.text((466, 272), "✓ Reward 1.0", fill="#166534", font=font(15))
    return img


def openended(step):
    img, d = frame("https://example.com/", "Example Domain")
    d.text((24, 100), "This domain is for use in illustrative examples in documents.", fill="#374151", font=font(14))
    d.text((24, 124), "You may use this domain in literature without prior coordination.", fill="#374151", font=font(14))
    d.text((24, 160), "More information...", fill="#2563eb", font=font(14))
    if step >= 1:
        d.rectangle([20, 156, 166, 180], outline="#f59e0b", width=3)
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        miniwob(i).save(OUT / f"step-{i}.png", optimize=True)
    for i in range(2):
        openended(i).save(OUT / f"openended-{i}.png", optimize=True)
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))
