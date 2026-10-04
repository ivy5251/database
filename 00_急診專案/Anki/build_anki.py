#!/usr/bin/env python3
"""把 Anki/*.tsv 打包成 Anki 匯入檔（.apkg）。

用法：
    pip install genanki
    python3 00_急診專案/Anki/build_anki.py          # 全部 tsv
    python3 00_急診專案/Anki/build_anki.py 神經      # 只打包 神經.tsv

TSV 欄位：id / type（basic 或 cloze）/ deck / front / back
- id 是卡片的永久身分：改內容不改 id，重新匯入 Anki 會「更新」而不是新增、複習紀錄保留
- cloze 的 front 用 {{c1::答案}}；back 是補充（可空）
- 換行用 <br>；插圖用 [[img:檔名]]，圖片從對應科別筆記的 assets/ 找
"""
import csv
import hashlib
import re
import sys
import tempfile
import shutil
from pathlib import Path

import genanki

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

ROOT_DECK = "急診醫學"

# tsv 檔名 → 科別資料夾、各子牌組對應的筆記
SOURCES = {
    "神經": {
        "folder": "06_神經",
        "notes": {
            "Stroke": "中風Stroke.md",
            "IICP": "IICP.md",
            "Seizure": "Seizure與Status_epilepticus.md",
            "意識改變": "意識改變_AMS.md",
            "頭暈": "頭暈.md",
            "頭痛": "頭痛.md",
        },
    },
}

# 固定的 ID：不要改，否則 Anki 會當成新的 note type
BASIC_MODEL_ID = 1730000001
CLOZE_MODEL_ID = 1730000002
MEDIA_PREFIX = "emnotes_"  # Anki 媒體是全域平面目錄，加前綴避免撞名

CSS = """
.card {
  font-family: -apple-system, "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", sans-serif;
  font-size: 20px; line-height: 1.6; text-align: left;
  color: #1f2328; background: #ffffff; padding: 8px 16px;
}
.nightMode.card, .night_mode .card { color: #e6edf3; background: #1e1e1e; }
.front { font-weight: 600; }
.back { margin-top: 4px; }
.extra { margin-top: 12px; font-size: 17px; color: #57606a; }
.nightMode .extra, .night_mode .extra { color: #9da7b3; }
.source { margin-top: 18px; font-size: 13px; color: #8c959f; }
.cloze { font-weight: 700; color: #0969da; }
.nightMode .cloze, .night_mode .cloze { color: #58a6ff; }
b { color: #cf222e; }
.nightMode b, .night_mode b { color: #ff7b72; }
img { max-width: 100%; height: auto; margin-top: 8px; border-radius: 6px; }
hr#answer { margin: 14px 0; }
"""

BASIC_MODEL = genanki.Model(
    BASIC_MODEL_ID,
    "急診筆記-問答",
    fields=[{"name": "Front"}, {"name": "Back"}, {"name": "Source"}],
    templates=[{
        "name": "Card 1",
        "qfmt": '<div class="front">{{Front}}</div>',
        "afmt": '<div class="front">{{Front}}</div><hr id="answer">'
                '<div class="back">{{Back}}</div>'
                '<div class="source">📄 {{Source}}</div>',
    }],
    css=CSS,
)

CLOZE_MODEL = genanki.Model(
    CLOZE_MODEL_ID,
    "急診筆記-克漏字",
    fields=[{"name": "Text"}, {"name": "Extra"}, {"name": "Source"}],
    templates=[{
        "name": "Cloze",
        "qfmt": "{{cloze:Text}}",
        "afmt": "{{cloze:Text}}"
                '{{#Extra}}<div class="extra">{{Extra}}</div>{{/Extra}}'
                '<div class="source">📄 {{Source}}</div>',
    }],
    css=CSS,
    model_type=genanki.Model.CLOZE,
)

IMG_RE = re.compile(r"\[\[img:([^\]]+)\]\]")


def deck_id(name: str) -> int:
    # 由牌組名稱算出固定 ID，重新打包不會變
    return int(hashlib.sha1(name.encode()).hexdigest()[:8], 16) % (1 << 31) or 1


def build(name: str, out_dir: Path, media_dir: Path) -> Path:
    cfg = SOURCES[name]
    folder = ROOT / cfg["folder"]
    decks: dict[str, genanki.Deck] = {}
    media: set[Path] = set()

    def fill_images(text: str) -> str:
        def repl(m):
            src = folder / "assets" / m.group(1)
            if not src.exists():
                sys.exit(f"找不到圖片：{src}")
            dst = media_dir / (MEDIA_PREFIX + src.name)
            shutil.copyfile(src, dst)
            media.add(dst)
            return f'<img src="{dst.name}">'
        return IMG_RE.sub(repl, text)

    seen = set()
    with open(HERE / f"{name}.tsv", encoding="utf-8", newline="") as f:
        for n, row in enumerate(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE), start=2):
            cid, kind, sub = row["id"].strip(), row["type"].strip(), row["deck"].strip()
            if cid in seen:
                sys.exit(f"{name}.tsv 第 {n} 行：id 重複 {cid}")
            seen.add(cid)
            if sub not in cfg["notes"]:
                sys.exit(f"{name}.tsv 第 {n} 行：未知子牌組 {sub}")

            front = fill_images(row["front"].strip())
            back = fill_images((row["back"] or "").strip())
            source = f'{cfg["folder"]}/{cfg["notes"][sub]}'
            tags = [name, sub.replace(" ", "_")]

            if kind == "basic":
                model, fields = BASIC_MODEL, [front, back, source]
            elif kind == "cloze":
                if "{{c" not in front:
                    sys.exit(f"{name}.tsv 第 {n} 行：cloze 卡沒有 {{{{c1::}}}}")
                model, fields = CLOZE_MODEL, [front, back, source]
            else:
                sys.exit(f"{name}.tsv 第 {n} 行：type 必須是 basic 或 cloze")

            deck_name = f"{ROOT_DECK}::{cfg['folder']}::{sub}"
            if deck_name not in decks:
                decks[deck_name] = genanki.Deck(deck_id(deck_name), deck_name)
            decks[deck_name].add_note(genanki.Note(
                model=model, fields=fields, tags=tags, guid=genanki.guid_for(cid)))

    out = out_dir / f"{cfg['folder']}.apkg"
    pkg = genanki.Package(list(decks.values()))
    pkg.media_files = [str(p) for p in sorted(media)]
    pkg.write_to_file(str(out))

    counts = {d.name.split("::")[-1]: len(d.notes) for d in decks.values()}
    print(f"{out.relative_to(ROOT)}：{sum(counts.values())} 張 note {counts}，圖片 {len(media)} 張")
    return out


def main():
    names = sys.argv[1:] or [p.stem for p in sorted(HERE.glob("*.tsv"))]
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            if name not in SOURCES:
                sys.exit(f"SOURCES 裡沒有設定「{name}」")
            build(name, HERE, Path(tmp))


if __name__ == "__main__":
    main()
