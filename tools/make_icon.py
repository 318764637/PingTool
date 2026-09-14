"""生成应用图标 assets/app.ico（可重复运行）。

设计：蓝色渐变圆角方块 + 从左下角向右上辐射的三道白色信号弧 + 绿色原点，
对应「Ping 延迟监测」。几何图形按画布比例绘制，因此缩小到 16px 仍然清晰。

用法：
    python tools/make_icon.py            # 生成 ico + 预览图
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

MASTER = 1024          # 主图尺寸（从它缩放派生各尺寸）
SS = 4                 # 超采样倍数：先画 4 倍大再缩回，边缘更平滑
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]

# 配色（与界面深色主题呼应：蓝色主色 + 绿色「正常」色）
GRAD_TOP = (79, 142, 247)      # #4F8EF7
GRAD_BOTTOM = (22, 50, 122)    # #16327A
DOT_COLOR = (74, 222, 128)     # #4ADE80
ARC_COLORS = [
    (255, 255, 255, 255),
    (255, 255, 255, 225),
    (255, 255, 255, 190),
]


def _rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=radius, fill=255
    )
    return mask


def _gradient(size, top, bottom):
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(1, size - 1)
        # 用平方插值让上半部分亮色停留更久，观感更接近现代图标
        t = t ** 0.85
        grad.putpixel((0, y), tuple(
            round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)
        ))
    return grad.resize((size, size))


def render(size):
    """按目标尺寸渲染图标（内部按 SS 倍超采样后缩小）。"""
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # 圆角方块底色 + 渐变
    mask = _rounded_mask(s, radius=round(s * 0.235))
    img.paste(_gradient(s, GRAD_TOP, GRAD_BOTTOM).convert("RGBA"), (0, 0), mask)

    draw = ImageDraw.Draw(img)

    # 信号弧：原点在中下方，弧线向上放射（标准「信号」形状，缩小后仍好认）
    origin = (s * 0.5, s * 0.775)
    for i, (ratio, color) in enumerate(zip((0.205, 0.350, 0.495), ARC_COLORS)):
        radius = s * ratio
        width = round(s * (0.085 - i * 0.010))
        box = (
            origin[0] - radius, origin[1] - radius,
            origin[0] + radius, origin[1] + radius,
        )
        draw.arc(box, -142, -38, fill=color, width=width)

    # 原点
    dot = s * 0.088
    draw.ellipse(
        (origin[0] - dot, origin[1] - dot, origin[0] + dot, origin[1] + dot),
        fill=DOT_COLOR + (255,),
    )

    return img.resize((size, size), Image.LANCZOS)


def build_preview(sizes, path, scale=4, pad=12):
    """把各尺寸摆在一张预览图上（棋盘格底），便于人工检查清晰度。"""
    cells = []
    for size in sizes:
        shown = size * scale if size <= 64 else size
        cells.append((size, shown, shown + pad * 2))
    width = sum(c[2] for c in cells)
    height = max(c[2] for c in cells)
    sheet = Image.new("RGB", (width, height), (245, 246, 248))
    draw = ImageDraw.Draw(sheet)
    x_offset = 0
    for size, shown, cell in cells:
        for y in range(0, height, 16):          # 棋盘格
            for x in range(0, cell, 16):
                if (x // 16 + y // 16) % 2 == 0:
                    draw.rectangle((x_offset + x, y, x_offset + x + 15, y + 15),
                                   fill=(226, 229, 234))
        icon = render(size)
        if shown != size:
            icon = icon.resize((shown, shown), Image.NEAREST)
        sheet.paste(icon, (x_offset + pad, (height - shown) // 2), icon)
        x_offset += cell
    sheet.save(path)
    return sheet


def main():
    ASSETS.mkdir(exist_ok=True)

    master = render(MASTER)
    ico_path = ASSETS / "app.ico"
    master.resize((256, 256), Image.LANCZOS).save(
        ico_path, format="ICO", sizes=[(s, s) for s in ICO_SIZES]
    )
    master.resize((256, 256), Image.LANCZOS).save(ASSETS / "app.png")

    preview = build_preview([16, 24, 32, 48, 256], ASSETS / "icon_preview.png")
    print(f"已生成: {ico_path} ({ico_path.stat().st_size} B, 含 {len(ICO_SIZES)} 种尺寸)")
    print(f"预览图: {ASSETS / 'icon_preview.png'} {preview.size}")


if __name__ == "__main__":
    main()
