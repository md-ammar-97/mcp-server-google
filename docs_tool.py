from auth import get_credentials
from googleapiclient.discovery import build


def _parse_inline(raw: str) -> tuple[str, list[dict]]:
    """Return (plain_text, format_list) where each format is {start, end, bold, italic}."""
    formats = []
    plain = ""
    i = 0
    while i < len(raw):
        matched = False
        for open_m, close_m, bold, italic in [
            ("***", "***", True,  True),
            ("**",  "**",  True,  False),
            ("*",   "*",   False, True),
            ("_",   "_",   False, True),
        ]:
            ol = len(open_m)
            if raw[i:i + ol] == open_m:
                ci = raw.find(close_m, i + ol)
                if ci != -1 and ci > i + ol:
                    s = len(plain)
                    plain += raw[i + ol:ci]
                    formats.append({"start": s, "end": len(plain), "bold": bold, "italic": italic})
                    i = ci + len(close_m)
                    matched = True
                    break
        if not matched:
            plain += raw[i]
            i += 1
    return plain, formats


def _parse_content(content: str) -> list[dict]:
    """Parse markdown into Docs segments: {text, style, bullet, formats}."""
    segments = []
    for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith("# "):
            plain, fmts = _parse_inline(line[2:])
            segments.append({"text": plain + "\n", "style": "HEADING_1", "bullet": False, "formats": fmts})
        elif line.startswith("## "):
            plain, fmts = _parse_inline(line[3:])
            segments.append({"text": plain + "\n", "style": "HEADING_2", "bullet": False, "formats": fmts})
        elif line.startswith("### "):
            plain, fmts = _parse_inline(line[4:])
            segments.append({"text": plain + "\n", "style": "HEADING_3", "bullet": False, "formats": fmts})
        elif line.startswith("- ") or line.startswith("* "):
            plain, fmts = _parse_inline(line[2:])
            segments.append({"text": plain + "\n", "style": "NORMAL_TEXT", "bullet": True, "formats": fmts})
        elif line.strip() in ("---", "***", "___"):
            segments.append({"text": "\n", "style": "NORMAL_TEXT", "bullet": False, "formats": []})
        else:
            plain, fmts = _parse_inline(line)
            segments.append({"text": plain + "\n", "style": "NORMAL_TEXT", "bullet": False, "formats": fmts})
    return segments


def append_to_doc(doc_id: str, content: str) -> dict:
    """Append *content* (supports markdown) as formatted text at the end of the specified Google Doc."""
    if not doc_id.strip():
        raise ValueError("doc_id must not be empty.")

    creds = get_credentials()
    service = build("docs", "v1", credentials=creds)

    doc = service.documents().get(documentId=doc_id).execute()
    body_content = doc["body"]["content"]
    end_index = body_content[-1]["endIndex"] - 1

    segments = _parse_content(content)
    plain_text = "".join(seg["text"] for seg in segments)

    requests = [
        {"insertText": {"location": {"index": end_index}, "text": "\n" + plain_text}}
    ]

    cursor = end_index + 1  # skip the leading \n we inserted

    for seg in segments:
        seg_len = len(seg["text"])
        seg_start = cursor
        seg_end = cursor + seg_len

        if seg["style"] != "NORMAL_TEXT":
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": seg_start, "endIndex": seg_end},
                    "paragraphStyle": {"namedStyleType": seg["style"]},
                    "fields": "namedStyleType",
                }
            })

        if seg["bullet"]:
            requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": seg_start, "endIndex": seg_end},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                }
            })

        for fmt in seg["formats"]:
            style = {}
            fields = []
            if fmt["bold"]:
                style["bold"] = True
                fields.append("bold")
            if fmt["italic"]:
                style["italic"] = True
                fields.append("italic")
            if style:
                requests.append({
                    "updateTextStyle": {
                        "range": {
                            "startIndex": seg_start + fmt["start"],
                            "endIndex": seg_start + fmt["end"],
                        },
                        "textStyle": style,
                        "fields": ",".join(fields),
                    }
                })

        cursor += seg_len

    service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()

    return {"status": "ok", "doc_id": doc_id, "chars_added": len(plain_text)}
