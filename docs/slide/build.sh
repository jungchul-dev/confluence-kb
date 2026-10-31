#!/usr/bin/env bash
# build.sh — index.html + style.css + fonts/ → 단일 자급 HTML (폰트 base64 인라인, CSS/JS/HTML 압축)
# 사용: ./build.sh [출력파일]   기본: ConfluenceKB-DataFlow.html
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$SCRIPT_DIR/ConfluenceKB.html}"
[ -f "$SCRIPT_DIR/index.html" ] || { echo "ERROR: index.html 이 없습니다" >&2; exit 1; }
echo "Building self-contained HTML → $OUT"

python3 - "$SCRIPT_DIR" "$OUT" << 'PYEOF'
import sys, base64, pathlib, re
src = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2])
html = (src / "index.html").read_text(encoding="utf-8")

css = (src / "style.css").read_text(encoding="utf-8")
# CDN @import 는 오프라인 재생을 위해 제거 (로컬 woff2 를 인라인한다)
css = re.sub(r'@import url\("https://cdn\.jsdelivr\.net[^"]*"\);\s*', '', css)
html = html.replace('<link rel="stylesheet" href="style.css">', f'<style>{css}</style>')
print("  Inlined: style.css")

for fnt in sorted((src / "fonts").glob("*.woff2")):
    b64 = base64.b64encode(fnt.read_bytes()).decode("ascii")
    html = html.replace(f'fonts/{fnt.name}', f'data:font/woff2;base64,{b64}')
    print(f"  Embedded: fonts/{fnt.name}")

def minify_css(c):
    c = re.sub(r'/\*.*?\*/', '', c, flags=re.DOTALL)
    c = re.sub(r'\s+', ' ', c)
    c = re.sub(r'\s*([{}:;,>~+])\s*', r'\1', c)
    return c.replace(';}', '}').strip()
html = re.sub(r'<style>(.*?)</style>', lambda m: '<style>' + minify_css(m.group(1)) + '</style>', html, flags=re.DOTALL)

def minify_js(js):
    # 템플릿 리터럴(백틱) 안은 보존하고, 그 외 줄은 앞뒤 공백 제거 + 빈 줄 삭제
    out, inside = [], False
    for line in js.split('\n'):
        if not inside and not line.strip():
            continue
        out.append(line.rstrip() if inside else line.strip())
        if line.count('`') % 2 == 1:
            inside = not inside
    return '\n'.join(out)
html = re.sub(r'<script>(.*?)</script>', lambda m: '<script>' + minify_js(m.group(1)) + '</script>', html, flags=re.DOTALL)
html = re.sub(r'>\s+<', '><', html)

out.write_text(html, encoding="utf-8")
print(f"\nDone: {out} ({out.stat().st_size/1024:.0f} KB)")
PYEOF
