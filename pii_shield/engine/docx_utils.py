"""
DOCX XML manipulation utilities for PII Shield.

All low-level python-docx / lxml operations live here so the engine
modules stay focused on NLP logic.
"""

from __future__ import annotations
from pathlib import Path
from html import escape as _html_escape
import os
import logging

log = logging.getLogger("pii-shield.docx")


# ── Document iteration ────────────────────────────────────────────────────────

def iter_docx_paragraphs(doc):
    """Yield paragraphs via python-docx API (body, tables, headers/footers)."""
    for p in doc.paragraphs:
        yield p
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p
    for sec in doc.sections:
        for hf in [sec.header, sec.footer]:
            if hf:
                for p in hf.paragraphs:
                    yield p


def _is_inside_tracked_delete(p_elem, wns: str) -> bool:
    parent = p_elem.getparent()
    while parent is not None:
        if parent.tag == f'{{{wns}}}del':
            return True
        parent = parent.getparent()
    return False


def iter_all_wp_elements(doc):
    """Yield ALL w:p elements in the full document XML tree.
    Covers body, tables, text boxes, content controls, tracked insertions,
    headers, and footers. Skips w:p inside w:del (tracked deletions).
    """
    wns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    for p in doc.element.iter(f'{{{wns}}}p'):
        if not _is_inside_tracked_delete(p, wns):
            yield p
    for sec in doc.sections:
        for part in [
            sec.header, sec.footer,
            getattr(sec, 'first_page_header', None),
            getattr(sec, 'first_page_footer', None),
            getattr(sec, 'even_page_header', None),
            getattr(sec, 'even_page_footer', None),
        ]:
            if part and part._element is not None:
                for p in part._element.iter(f'{{{wns}}}p'):
                    if not _is_inside_tracked_delete(p, wns):
                        yield p


# ── Segment collection ────────────────────────────────────────────────────────

def collect_paragraph_segments(p_elem, wns: str) -> list[tuple]:
    """Collect (element, text, kind) for all inline text-producing elements.
    kind: 'wt' | 'br' | 'tab' | 'cr'
    """
    segments = []
    for elem in p_elem.iter():
        tag = elem.tag
        if tag == f'{{{wns}}}t':
            segments.append((elem, elem.text or "", "wt"))
        elif tag == f'{{{wns}}}br':
            if elem.get(f'{{{wns}}}type') not in ('page', 'column'):
                segments.append((elem, "\n", "br"))
        elif tag == f'{{{wns}}}tab':
            segments.append((elem, "\t", "tab"))
        elif tag == f'{{{wns}}}cr':
            segments.append((elem, "\r", "cr"))
    return segments


# ── Single-paragraph text replacement ────────────────────────────────────────

def replace_across_runs(p_elem, old_text: str, new_text: str, wns: str):
    """Replace old_text with new_text within a single paragraph element,
    handling text split across multiple w:t runs, w:br, w:tab, w:cr.
    """
    if not old_text:
        return
    while True:
        segments = collect_paragraph_segments(p_elem, wns)
        if not segments:
            break
        joined = "".join(s[1] for s in segments)
        idx = joined.find(old_text)
        if idx == -1:
            break
        end_idx = idx + len(old_text)

        seg_pos = 0
        first_seg = last_seg = -1
        offset_in_first = offset_in_last_end = 0
        for i, (elem, text, kind) in enumerate(segments):
            seg_end = seg_pos + len(text)
            if first_seg == -1 and seg_end > idx:
                first_seg = i
                offset_in_first = idx - seg_pos
            if seg_end >= end_idx:
                last_seg = i
                offset_in_last_end = end_idx - seg_pos
                break
            seg_pos = seg_end

        if first_seg == -1 or last_seg == -1:
            break

        # Find first w:t in match range to host the replacement text
        host_seg = next((i for i in range(first_seg, last_seg + 1)
                         if segments[i][2] == "wt"), None)
        if host_seg is None:
            break

        for i in range(first_seg, last_seg + 1):
            elem, text, kind = segments[i]
            if i == host_seg:
                prefix = text[:offset_in_first] if i == first_seg else ""
                suffix = text[offset_in_last_end:] if i == last_seg else ""
                elem.text = prefix + new_text + suffix
            elif kind == "wt":
                if i == first_seg:
                    elem.text = text[:offset_in_first]
                elif i == last_seg:
                    elem.text = text[offset_in_last_end:]
                else:
                    elem.text = ""
            else:
                parent = elem.getparent()
                if parent is not None:
                    parent.remove(elem)


# ── Cross-paragraph replacement ───────────────────────────────────────────────

def replace_cross_paragraphs(all_p_elems: list, old_text: str,
                              new_text: str, wns: str) -> bool:
    """Replace text spanning multiple paragraphs (contains \\n).
    Loops to handle repeated occurrences.
    """
    raw_parts = old_text.split("\n")
    parts = [p for p in raw_parts if p]
    if len(parts) < 2:
        return False

    replaced_any = False
    while True:
        para_data = []
        for p_elem in all_p_elems:
            segs = collect_paragraph_segments(p_elem, wns)
            vtext = "".join(s[1] for s in segs)
            para_data.append((p_elem, vtext))

        found = False
        for start in range(len(para_data) - len(parts) + 1):
            matched = all(
                (j == 0 and parts[j] and para_data[start + j][1].endswith(parts[j])) or
                (j == len(parts) - 1 and parts[j] and para_data[start + j][1].startswith(parts[j])) or
                (0 < j < len(parts) - 1 and para_data[start + j][1] == parts[j])
                for j in range(len(parts))
            )
            if not matched:
                continue

            replace_across_runs(all_p_elems[start], parts[0], new_text, wns)
            for j in range(1, len(parts) - 1):
                for seg_elem, _, seg_kind in collect_paragraph_segments(all_p_elems[start + j], wns):
                    if seg_kind == "wt":
                        seg_elem.text = ""
                    else:
                        parent = seg_elem.getparent()
                        if parent is not None:
                            parent.remove(seg_elem)
            replace_across_runs(all_p_elems[start + len(parts) - 1], parts[-1], "", wns)
            found = True
            replaced_any = True
            break

        if not found:
            break
    return replaced_any


# ── Run-level replacement (used during NER-based anonymization) ───────────────

def get_runs(para) -> tuple[str, list[dict]]:
    runs_info = []
    offset = 0
    for run in para.runs:
        runs_info.append({"run": run, "text": run.text, "start": offset, "end": offset + len(run.text)})
        offset += len(run.text)
    return "".join(r["text"] for r in runs_info), runs_info


def replace_in_runs(runs_info: list[dict], start: int, end: int, replacement: str):
    """Replace [start, end) with replacement across paragraph runs."""
    affected = [i for i, ri in enumerate(runs_info) if ri["end"] > start and ri["start"] < end]
    if not affected:
        return

    first_idx, last_idx = affected[0], affected[-1]
    for idx in affected:
        ri = runs_info[idx]
        old_text = ri["text"]
        local_start = max(0, start - ri["start"])
        local_end = min(len(old_text), end - ri["start"])

        if idx == first_idx == last_idx:
            new_text = old_text[:local_start] + replacement + old_text[local_end:]
        elif idx == first_idx:
            new_text = old_text[:local_start] + replacement
        elif idx == last_idx:
            new_text = old_text[local_end:]
        else:
            new_text = ""

        ri["run"].text = new_text
        ri["text"] = new_text

    offset = 0
    for ri in runs_info:
        ri["start"] = offset
        ri["end"] = offset + len(ri["text"])
        offset += len(ri["text"])


# ── DOCX → HTML (for HITL review UI) ─────────────────────────────────────────

def docx_to_html(doc) -> str:
    """Convert docx to simple HTML preserving bold/italic/underline and headings."""
    from lxml import etree
    wns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

    def _run_fmt(r_elem):
        rPr = r_elem.find(f'{{{wns}}}rPr')
        if rPr is None:
            return False, False, False
        b = rPr.find(f'{{{wns}}}b')
        bold = b is not None and b.get(f'{{{wns}}}val', 'true') != 'false'
        i = rPr.find(f'{{{wns}}}i')
        italic = i is not None and i.get(f'{{{wns}}}val', 'true') != 'false'
        u = rPr.find(f'{{{wns}}}u')
        underline = u is not None and u.get(f'{{{wns}}}val', 'none') != 'none'
        return bold, italic, underline

    parts = []
    for para in iter_docx_paragraphs(doc):
        style_name = para.style.name if para.style else ""
        tag = "p"
        if "Heading 1" in style_name or "Title" in style_name:
            tag = "h1"
        elif "Heading 2" in style_name or "Subtitle" in style_name:
            tag = "h2"
        elif "Heading 3" in style_name:
            tag = "h3"
        elif "Heading" in style_name:
            tag = "h4"

        runs_html = []

        def _process_run(r_elem):
            bold, italic, underline = _run_fmt(r_elem)
            for child in r_elem:
                child_tag = etree.QName(child.tag).localname if '}' in child.tag else child.tag
                if child_tag == 't':
                    if child.text:
                        t = _html_escape(child.text)
                        if bold:      t = f"<b>{t}</b>"
                        if italic:    t = f"<i>{t}</i>"
                        if underline: t = f"<u>{t}</u>"
                        runs_html.append(t)
                elif child_tag == 'br':
                    br_type = child.get(f'{{{wns}}}type')
                    if br_type is None or br_type == 'textWrapping':
                        runs_html.append('<br>')
                elif child_tag in ('tab', 'ptab'):
                    runs_html.append('&#9;')
                elif child_tag in ('cr', 'noBreakHyphen'):
                    runs_html.append('<br>' if child_tag == 'cr' else '-')

        for child in para._element:
            child_tag = etree.QName(child.tag).localname if '}' in child.tag else child.tag
            if child_tag == 'r':
                _process_run(child)
            elif child_tag == 'hyperlink':
                for sub in child:
                    sub_tag = etree.QName(sub.tag).localname if '}' in sub.tag else sub.tag
                    if sub_tag == 'r':
                        _process_run(sub)
        parts.append(f"<{tag}>{''.join(runs_html)}</{tag}>")
    return "\n".join(parts)


# ── Save helper ───────────────────────────────────────────────────────────────

def save_docx(doc, out_path: Path):
    """Save docx and fsync to ensure filesystem visibility (e.g. VirtioFS mounts)."""
    doc.save(str(out_path))
    try:
        fd = os.open(str(out_path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)   # always close — Windows locks file if fd leaks
    except OSError:
        pass
