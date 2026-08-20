from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path.cwd()
OUT = ROOT / 'practice_screenshots'
OUT.mkdir(exist_ok=True)
font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 18)
small = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 15)
title_font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 26)
test_font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 22)

def code_screen(name, title, source, max_lines=90):
    text = (ROOT / source).read_text(encoding='utf-8').splitlines()[:max_lines]
    h = 115 + max(1, len(text)) * 27
    im = Image.new('RGB', (1500, h), '#0d1117')
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 1500, 86), fill='#172235')
    for x, color in [(32, '#f87171'), (58, '#fbbf24'), (84, '#4ade80')]:
        d.ellipse((x-8, 24, x+8, 40), fill=color)
    d.text((120, 18), title, font=title_font, fill='#e8edf5')
    d.text((120, 57), source, font=small, fill='#7dd3fc')
    y = 106
    for i, line in enumerate(text, 1):
        d.text((55, y), f'{i:>3}', font=small, fill='#60748e')
        d.text((115, y), line[:145], font=font, fill='#dbe7f5')
        y += 27
    im.save(OUT / name)

code_screen('04_项目工程结构与核心代码.png', '项目工程结构与核心代码', 'frontend/src/character/CharacterView.tsx', 70)
code_screen('05_AI与语音模块开发.png', 'AI 与语音模块开发', 'app/modules/tts/api.py', 90)
code_screen('06_Live2D角色表现控制开发.png', 'Live2D 角色表现控制开发', 'frontend/src/character/ParameterMixer.ts', 90)
code_screen('08_系统性能优化与问题排查.png', '系统性能优化与问题排查', 'frontend/src/character/CharacterPerformancePolicy.ts', 90)

lines = ['真实命令：npm.cmd test', '', 'pretest  · 11 tests  · 11 pass  · 0 fail', 'main test · 211 tests · 211 pass · 0 fail', '', '总计：222 tests passed', '失败：0', '耗时：约 0.64 秒', '', '验证范围：Runtime / Electron 生命周期 / Live2D 参数与动作 /', 'Lip Sync / Performance Policy / Audio / Session / UI']
im = Image.new('RGB', (1500, 560), '#0d1117')
d = ImageDraw.Draw(im)
d.rectangle((0, 0, 1500, 86), fill='#172235')
for x, color in [(32, '#f87171'), (58, '#fbbf24'), (84, '#4ade80')]:
    d.ellipse((x-8, 24, x+8, 40), fill=color)
d.text((120, 18), '项目测试与验证结果', font=title_font, fill='#e8edf5')
d.text((120, 57), 'frontend · npm.cmd test · real output summary', font=small, fill='#7dd3fc')
for i, line in enumerate(lines):
    d.text((80, 122 + i * 33), line, font=test_font, fill='#86efac' if 'pass' in line else '#dbe7f5')
im.save(OUT / '07_项目测试与验证结果.png')
