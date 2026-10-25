# -*- coding: utf-8 -*-
"""第 5 期 · 聊天演示段：把"五栏格式"粘给 AI，看它怎么回。

画面：深色聊天窗，用户气泡（右）给格式要求，AI 气泡（左）逐行产出五栏。
输出：发布/回溯性重构_格式包/引流视频素材/08_第5期_聊天演示.mp4（1920x1080 无音）
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SRC = Path(r'D:\大肥鱼工作区\发布\回溯性重构_格式包\引流视频素材')
WORK = SRC / '_build_chat'
W, H = 1920, 1080
FONT = r'C:\Windows\Fonts\msyh.ttc'
BOLD = r'C:\Windows\Fonts\msyhbd.ttc'

BG = (24, 26, 30)
BAR = (38, 41, 47)
PANEL = (38, 41, 47)
USER_BG = (56, 96, 178)
AI_BG = (52, 56, 63)
FG = (235, 235, 235)
GREY = (150, 150, 150)
CYAN = (120, 190, 255)

USER = '结论写成：假设 / 原片 / 后来 / 注释 / 变更史。写完不保证对。'
AI_LINES = [
    ('假设：AI 越聊越傻，是因为它每次都在重读全文；这个结论我还没验。', 1.2),
    ('原片：过去三次对话有 18 万字，真正进上下文的只有头尾两段。', 1.2),
    ('后来：下次再说它变傻，先回去看这三次的截断位置。', 1.4),
    ('注释：我只说"可能更贵"，不保证"一定更傻"。', 1.4),
    ('变更史：从"AI 变傻"改成"我看不见它的上下文被截断了"。', 1.2),
]


def font(sz, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, sz)


def wrap(text, f, maxw):
    lines, cur = [], ''
    for ch in text:
        if f.getlength(cur + ch) > maxw:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def draw_base():
    im = Image.new('RGB', (W, H), BG)
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, W, 64], fill=BAR)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        dr.ellipse([24 + i * 30, 22, 42 + i * 30, 40], fill=c)
    dr.text((150, 18), 'AI 对话 — 五栏格式', font=font(26), fill=GREY)
    return im, dr


def bubble(dr, x, y, w, h, color):
    dr.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=color)


def draw_ai(ai_shown):
    im, dr = draw_base()
    # 用户气泡（右）
    uf = font(30)
    utext = wrap(USER, uf, 900)
    uh = 24 + len(utext) * 46
    uw = 920
    bubble(dr, W - 100 - uw, 120, uw, uh, USER_BG)
    yy = 140
    for ln in utext:
        dr.text((W - 110 - uw + 20, yy), ln, font=uf, fill=(255, 255, 255))
        yy += 46
    # AI 气泡（左），逐行出现
    af = font(30)
    y = 120 + uh + 40
    box_lines = []
    for text, _ in ai_shown:
        box_lines.extend(wrap(text, af, 1400))
    bh = 40 + len(box_lines) * 44 + 10
    bubble(dr, 100, y, 1720, bh, AI_BG)
    yy = y + 24
    for ln in box_lines:
        color = FG
        if ln.startswith('假设') or ln.startswith('原片'):
            color = CYAN
        elif ln.startswith('后来') or ln.startswith('注释') or ln.startswith('变更史'):
            color = (255, 210, 120)
        dr.text((136, yy), ln, font=af, fill=color)
        yy += 44
    return im


def build(seq):
    WORK.mkdir(parents=True, exist_ok=True)
    for f in WORK.glob('*'):
        if f.is_file():
            f.unlink()
    parts = []
    for i, (im, dur) in enumerate(seq):
        png = WORK / f'f_{i:04d}.png'
        mp4 = WORK / f'f_{i:04d}.mp4'
        im.save(png)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-loop', '1',
                        '-i', str(png), '-t', f'{dur:.3f}', '-r', '30',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                        '-pix_fmt', 'yuv420p', str(mp4)], check=True)
        parts.append(mp4)
    lst = WORK / 'list.txt'
    lst.write_text('\n'.join(f"file '{p.name}'" for p in parts), encoding='utf-8')
    final = SRC / '08_第5期_聊天演示.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
                    '-i', str(lst), '-c', 'copy', str(final)], check=True, cwd=str(WORK))
    return final, sum(d for _, d in seq)


def main():
    seq = []
    # 用户消息先出现（1.0s 停顿后逐字？直接整段出现 + 停顿）
    seq.append((draw_ai([]), 1.6))
    shown = []
    for text, hold in AI_LINES:
        shown = shown + [(text, hold)]
        seq.append((draw_ai(shown), hold))
    seq.append((draw_ai(shown), 2.0))
    final, total = build(seq)
    print(f'OK {final} 约 {total:.1f}s')


if __name__ == '__main__':
    main()
