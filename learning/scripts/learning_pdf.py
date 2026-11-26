"""Local A4 handouts from JSON. No AI GO login/network or overwrite; PDF dependencies optional."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

INSTALL = Path(__file__).resolve().parents[1]


def validate_content(content: dict) -> None:
    if not isinstance(content, dict) or not isinstance(content.get("title"), str) or not content["title"].strip():
        raise ValueError("來源需有非空白 title")
    if not isinstance(content.get("pages"), list) or not content["pages"]:
        raise ValueError("來源需有非空白 pages 陣列")
    if "subtitle" in content and not isinstance(content["subtitle"], str):
        raise ValueError("subtitle 必須是文字")
    for page in content["pages"]:
        if not isinstance(page, dict) or not isinstance(page.get("title"), str) or not page["title"].strip():
            raise ValueError("每頁需有 title")
        if not isinstance(page.get("blocks"), list) or not page["blocks"]:
            raise ValueError("每頁需有非空白 blocks 陣列")
        if "intro" in page and not isinstance(page["intro"], str):
            raise ValueError("intro 必須是文字")
        for block in page["blocks"]:
            if not isinstance(block, dict) or not any(key in block for key in ("text", "bullets", "table")):
                raise ValueError("內容區塊需含 text、bullets 或 table")
            for key in ("text", "heading"):
                if key in block and not isinstance(block[key], str):
                    raise ValueError(f"{key} 必須是文字")
            if "bullets" in block and (not isinstance(block["bullets"], list)
                    or not all(isinstance(item, str) for item in block["bullets"])):
                raise ValueError("bullets 必須是文字陣列")
            if "table" in block:
                table = block["table"]
                if (not isinstance(table, list) or not table or not isinstance(table[0], list) or not table[0]
                        or any(not isinstance(row, list) or len(row) != len(table[0])
                               or not all(isinstance(cell, str) for cell in row) for row in table)):
                    raise ValueError("table 必須是欄數相同的非空白文字陣列")


def texts(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from texts(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from texts(item)


def safe_output(path: Path) -> Path:
    path = path.resolve()
    if path.is_relative_to(INSTALL):
        raise ValueError("輸出必須在學員工作區，不能放技能目錄")
    if path.exists():
        raise FileExistsError(f"不覆蓋既有輸出：{path.name}")
    return path


def choose_font(requested: Path | None):
    from reportlab.pdfbase.ttfonts import TTFont
    candidates = [requested] if requested else [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msjh.ttc",
        Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    ]
    for path in candidates:
        if path and path.is_file():
            try:
                return TTFont("LearningCJK", str(path), subfontIndex=0)
            except Exception:
                continue
    raise ValueError("找不到可嵌入的相容字型，請用 --font 指定繁體中文 TTF/TTC")


def build_pdf(content: dict, output: Path, *, font: Path | None = None, expected_pages: int | None = None) -> dict:
    validate_content(content)
    if expected_pages is not None and expected_pages < 1:
        raise ValueError("expected_pages 必須大於零")
    output = safe_output(output)
    if output.suffix.lower() != ".pdf":
        raise ValueError("輸出副檔名必須為 .pdf")
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("缺少 PDF 相依，請依 requirements-pdf.txt 準備環境") from exc
    chosen = choose_font(font)
    required = {ord(char) for text in texts(content) for char in text if not char.isspace()}
    missing = required - set(chosen.face.charToGlyph)
    if missing:
        chars = "".join(chr(value) for value in sorted(missing)[:12])
        raise ValueError(f"字型缺字，請改用涵蓋內容的字型：{chars}")
    pdfmetrics.registerFont(chosen)
    navy, teal = colors.HexColor("#16364A"), colors.HexColor("#087F80")
    ink, muted, line = colors.HexColor("#253747"), colors.HexColor("#61717D"), colors.HexColor("#D8E3E7")
    styles = {
        "title": ParagraphStyle("title", fontName="LearningCJK", fontSize=22, leading=29, textColor=navy, spaceAfter=9, wordWrap="CJK"),
        "heading": ParagraphStyle("heading", fontName="LearningCJK", fontSize=12, leading=18, textColor=teal, spaceBefore=9, spaceAfter=5, keepWithNext=True, wordWrap="CJK"),
        "body": ParagraphStyle("body", fontName="LearningCJK", fontSize=10, leading=15.5, textColor=ink, spaceAfter=6, wordWrap="CJK"),
        "cell": ParagraphStyle("cell", fontName="LearningCJK", fontSize=9.1, leading=14, textColor=ink, wordWrap="CJK"),
        "small": ParagraphStyle("small", fontName="LearningCJK", fontSize=9, leading=14, textColor=muted, spaceAfter=8, wordWrap="CJK"),
    }
    width, height = A4
    usable = width - 88

    def para(text, kind="body"):
        return Paragraph(escape(text).replace("\n", "<br/>"), styles[kind])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(44, 43, width - 44, 43)
        canvas.setFont("LearningCJK", 8)
        canvas.setFillColor(muted)
        canvas.drawString(44, 29, content["title"][:36])
        canvas.drawRightString(width - 44, 29, str(doc.page))
        canvas.restoreState()

    story = []
    for number, page in enumerate(content["pages"]):
        if number:
            story.append(PageBreak())
        story.append(para(page["title"], "title"))
        if number == 0 and content.get("subtitle"):
            story.append(para(content["subtitle"], "small"))
        if page.get("intro"):
            story.append(para(page["intro"]))
        for block in page["blocks"]:
            if block.get("heading"):
                story.append(para(block["heading"], "heading"))
            if block.get("text"):
                story.append(para(block["text"]))
            for item in block.get("bullets", []):
                story.append(para("- " + item))
            if "table" in block:
                rows = [[para(cell, "cell") for cell in row] for row in block["table"]]
                columns = len(rows[0])
                widths = [usable / columns] * columns
                if columns == 2:
                    widths = [usable * .22, usable * .78]
                table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFF5F6")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LINEBELOW", (0, 0), (-1, -1), .35, line),
                ]))
                story.extend([table, Spacer(1, 7)])
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(suffix=".pdf", prefix=".learning-", dir=output.parent)
    os.close(fd)
    temporary = Path(temp)
    try:
        document = SimpleDocTemplate(str(temporary), pagesize=A4, leftMargin=44, rightMargin=44,
                                     topMargin=40, bottomMargin=58, title=content["title"], author="AI GO Learning")
        document.build(story, onFirstPage=footer, onLaterPages=footer)
        reader = PdfReader(temporary)
        count = len(reader.pages)
        if expected_pages is not None and count != expected_pages:
            raise ValueError(f"實際 {count} 頁，與要求 {expected_pages} 頁不符；請調整內容")
        if not count or any(not (page.extract_text() or "").strip() for page in reader.pages):
            raise ValueError("PDF 有空白頁或無法擷取文字")
        if any(abs(float(page.mediabox.width) - width) > 1 or abs(float(page.mediabox.height) - height) > 1 for page in reader.pages):
            raise ValueError("PDF 頁面不是 A4")
        # Exclusive creation protects an existing file even if another process wrote it meanwhile.
        with output.open("xb") as stream:
            stream.write(temporary.read_bytes())
    finally:
        temporary.unlink(missing_ok=True)
    return {"output": str(output), "pages": count, "text_check": "passed", "page_size": "A4",
            "visual_review": "pending", "rendering": "not_requested"}


def render(pdf: Path, directory: Path) -> list[str]:
    directory = safe_output(directory)
    command = shutil.which("pdftoppm")
    if not command:
        raise RuntimeError("找不到 pdftoppm；PDF 已產生，逐頁版面仍待驗證")
    directory.mkdir(parents=True, exist_ok=False)
    subprocess.run([command, "-png", "-scale-to", "1400", str(pdf), str(directory / "page")],
                   check=True, capture_output=True)
    return [str(path) for path in sorted(directory.glob("page-*.png"))]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--font", type=Path)
    parser.add_argument("--expected-pages", type=int)
    parser.add_argument("--render-dir", type=Path)
    args = parser.parse_args(argv)
    result = None
    try:
        content = json.loads(args.source.read_text(encoding="utf-8"))
        result = build_pdf(content, args.output, font=args.font, expected_pages=args.expected_pages)
        if args.render_dir:
            result["images"] = render(args.output, args.render_dir)
            result["rendering"] = "completed_pending_review"
    except Exception as exc:
        failure = {"status": "failed", "error": str(exc)}
        if result is not None:
            failure.update({"partial_output": result["output"], "visual_review": "pending"})
        print(json.dumps(failure, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "created", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(__import__("sys").stdout, "reconfigure"):
        __import__("sys").stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
