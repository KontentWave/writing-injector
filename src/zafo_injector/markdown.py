import re


class SourceFormatError(ValueError):
    """A required upstream Markdown section is missing or malformed."""


_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def numbered_section(text: str, number: int) -> str:
    headings: list[re.Match[str]] = []
    fence = ""
    offset = 0
    for line in text.splitlines(keepends=True):
        marker = re.match(r" {0,3}(`{3,}|~{3,})", line)
        if marker:
            delimiter = marker.group(1)
            if not fence:
                fence = delimiter
            elif delimiter[0] == fence[0] and len(delimiter) >= len(fence):
                fence = ""
        elif not fence:
            heading = _HEADING.match(text, offset)
            if heading:
                headings.append(heading)
        offset += len(line)
    for index, heading in enumerate(headings):
        title = heading.group(2).replace("\\.", ".")
        if not re.match(rf"(?:§\s*)?{number}(?:[.)\s:]|$)", title):
            continue
        end = len(text)
        for following in headings[index + 1 :]:
            if len(following.group(1)) <= len(heading.group(1)):
                end = following.start()
                break
        result = text[heading.end() : end].strip()
        if result:
            return result
        break
    raise SourceFormatError(f"Required nonempty Markdown section {number} was not found.")


def rule_table(section: str) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip().strip("`* ") for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        if re.fullmatch(r"[:\-\s]+", cells[0]):
            continue
        rows.append((cells[0], cells[1]))
    if len(rows) < 2:
        raise SourceFormatError("Expected a header and rule rows in a two-column Markdown table.")
    rules = tuple((term, replacement) for term, replacement in rows[1:] if term and replacement)
    if not rules:
        raise SourceFormatError("The Markdown rule table contains no usable rules.")
    return rules
