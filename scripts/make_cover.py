# -*- coding: utf-8 -*-
"""B站封面生成（1920x1080 黑底白字）。

输出：发布/回溯性重构_格式包/引流视频素材/06_封面_B站.png
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent.parent / '发布' / '回溯性重构_格式包' / '引流视频素材' / '06_封面_B站.png'
W, H = 1920, 1080
BOLD = r'C:\Windows\Fonts\msyhbd.ttc'
REG = r'C:\Windows\Fonts\msyh.ttc'

im = Image.new('RGB', (W, H), (0, 0, 0))
dr = ImageDraw.Draw(im)

f_big = ImageFont.truetype(BOLD, 132)
f_sub = ImageFont.truetype(REG, 56)
f_small = ImageFont.truetype(REG, 40)

# 主标题两行
t1 = '我开源了'
t2 = '但我不给股权'
y = 250
for t in (t1, t2):
    w = dr.textlength(t, font=f_big)
    dr.text(((W - w) / 2, y), t, font=f_big, fill=(255, 255, 255))
    y += 168

# 副标题
sub = '项目归所有人 · 赞助自愿 · 两条底线不退'
w = dr.textlength(sub, font=f_sub)
dr.text(((W - w) / 2, 700), sub, font=f_sub, fill=(180, 180, 180))

# 底部
bot = 'github.com/QiDouZu/retcon-form'
w = dr.textlength(bot, font=f_small)
dr.text(((W - w) / 2, 940), bot, font=f_small, fill=(120, 120, 120))

im.save(OUT)
print('OK', OUT)
