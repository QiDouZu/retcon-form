# -*- coding: utf-8 -*-
"""第 5 期封面（1920x1080）。"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent.parent / '发布' / '回溯性重构_格式包' / '引流视频素材' / '10_第5期_封面.png'
W, H = 1920, 1080
BOLD = r'C:\Windows\Fonts\msyhbd.ttc'
REG = r'C:\Windows\Fonts\msyh.ttc'

im = Image.new('RGB', (W, H), (0, 0, 0))
dr = ImageDraw.Draw(im)

f_big = ImageFont.truetype(BOLD, 118)
f_sub = ImageFont.truetype(REG, 52)
f_small = ImageFont.truetype(REG, 38)

lines = ['给任何 AI', '粘一句话']
y = 260
for t in lines:
    w = dr.textlength(t, font=f_big)
    dr.text(((W - w) / 2, y), t, font=f_big, fill=(255, 255, 255))
    y += 150

sub = '让它把结论写成可推翻的'
w = dr.textlength(sub, font=f_sub)
dr.text(((W - w) / 2, 640), sub, font=f_sub, fill=(190, 190, 190))

mid = '假设 / 原片 / 后来 / 注释 / 变更史'
w = dr.textlength(mid, font=f_sub)
dr.text(((W - w) / 2, 760), mid, font=f_sub, fill=(255, 210, 120))

bot = '不用插件，不读文件 · GitHub 搜 QiDouZu/retcon-form'
w = dr.textlength(bot, font=f_small)
dr.text(((W - w) / 2, 940), bot, font=f_small, fill=(110, 110, 110))

im.save(OUT)
print('OK', OUT)
