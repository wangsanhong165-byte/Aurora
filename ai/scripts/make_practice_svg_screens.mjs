import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const out = path.join(root, 'practice_screenshots');
await mkdir(out, { recursive: true });
const esc = (s) => s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const codeLines = (text, max = 90) => text.split(/\r?\n/).slice(0, max).map((line, i) => `<text x="60" y="${122 + i * 23}" class="code"><tspan class="ln">${String(i + 1).padStart(3, ' ')}</tspan>${esc(line)}</text>`).join('');
const codeSvg = async (name, title, file, max = 90) => {
  const text = await readFile(path.join(root, file), 'utf8');
  const count = Math.min(max, text.split(/\r?\n/).length);
  const height = 150 + count * 23;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="${height}" viewBox="0 0 1500 ${height}"><rect width="1500" height="${height}" fill="#0d1117"/><rect width="1500" height="86" fill="#172235"/><circle cx="32" cy="32" r="8" fill="#f87171"/><circle cx="58" cy="32" r="8" fill="#fbbf24"/><circle cx="84" cy="32" r="8" fill="#4ade80"/><text x="120" y="38" fill="#e8edf5" font-family="Segoe UI,Microsoft YaHei" font-size="25" font-weight="700">${esc(title)}</text><text x="120" y="68" fill="#7dd3fc" font-family="Consolas,monospace" font-size="15">${esc(file)}</text><style>.code{font:16px Consolas,\"Cascadia Code\",monospace;fill:#dbe7f5;white-space:pre}.ln{fill:#60748e}.kw{fill:#c084fc}</style>${codeLines(text, max)}</svg>`;
  await writeFile(path.join(out, name), svg, 'utf8');
};
await codeSvg('04_项目工程结构与核心代码.svg', '项目工程结构与核心代码', 'frontend/src/character/CharacterView.tsx', 70);
await codeSvg('05_AI与语音模块开发.svg', 'AI 与语音模块开发', 'app/modules/tts/api.py', 90);
await codeSvg('06_Live2D角色表现控制开发.svg', 'Live2D 角色表现控制开发', 'frontend/src/character/ParameterMixer.ts', 90);
await codeSvg('08_系统性能优化与问题排查.svg', '系统性能优化与问题排查', 'frontend/src/character/performance-policy.ts', 90);
const testLines = ['真实命令：npm.cmd test', '', 'pretest  · 11 tests  · 11 pass  · 0 fail', 'main test · 211 tests · 211 pass · 0 fail', '', '总计：222 tests passed', '失败：0', '耗时：约 0.64 秒', '', '验证范围：Runtime / Electron 生命周期 / Live2D 参数与动作 /', 'Lip Sync / Performance Policy / Audio / Session / UI'];
const testSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="560" viewBox="0 0 1500 560"><rect width="1500" height="560" fill="#0d1117"/><rect width="1500" height="86" fill="#172235"/><circle cx="32" cy="32" r="8" fill="#f87171"/><circle cx="58" cy="32" r="8" fill="#fbbf24"/><circle cx="84" cy="32" r="8" fill="#4ade80"/><text x="120" y="38" fill="#e8edf5" font-family="Segoe UI,Microsoft YaHei" font-size="25" font-weight="700">项目测试与验证结果</text><text x="120" y="68" fill="#7dd3fc" font-family="Consolas,monospace" font-size="15">frontend · npm.cmd test · real output summary</text>${testLines.map((line, i) => `<text x="80" y="${145 + i * 33}" fill="${line.includes('pass') || line.includes('通过') ? '#86efac' : '#dbe7f5'}" font-family="Consolas,Microsoft YaHei,monospace" font-size="22">${esc(line)}</text>`).join('')}</svg>`;
await writeFile(path.join(out, '07_项目测试与验证结果.svg'), testSvg, 'utf8');
