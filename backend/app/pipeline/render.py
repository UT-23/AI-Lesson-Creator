"""Render a `LessonContent` to learner-facing Markdown.

The reference list is built from stored `Source` rows — never from LLM text —
so every listed reference is something the research step actually found.
"""

from app.models import Source, SourceType
from app.schemas import LessonContent


def _fmt_minutes(minutes: float) -> str:
    return f"{minutes:g}"


def render_reference(src: Source) -> str:
    who = f" — {src.publisher}" if src.publisher else ""
    link = f" <{src.url}>" if src.url else ""
    kind = {SourceType.web: "Web", SourceType.book: "Book", SourceType.video: "Video"}[src.type]
    note = " (metadata/description only)" if src.type == SourceType.book else ""
    return f"- **[{src.sid}]** {src.title}{who}.{link} _{kind}, reliability tier {src.reliability_tier}{note}_"


def render_quiz(content: LessonContent) -> list[str]:
    lines: list[str] = []
    for n, item in enumerate(content.knowledge_check, start=1):
        lines.append(f"{n}. {item.q}")
        for letter, option in zip("ABCDEFGH", item.options):
            lines.append(f"   - {letter}) {option}")
        lines.append(f"   - **Answer:** {item.answer} — {item.explanation}")
        lines.append("")
    return lines


def render_markdown(content: LessonContent, sources: dict[str, Source]) -> str:
    lines = [
        f"# {content.title}",
        "",
        f"**Objective:** {content.objective}",
        "",
        f"**Estimated time:** {_fmt_minutes(content.total_minutes)} minutes",
        "",
        "## Learning outcomes",
        "",
        *[f"- {o}" for o in content.outcomes],
        "",
    ]

    quiz_rendered = False
    for section in content.sections:
        lines += [f"## {section.heading} (~{_fmt_minutes(section.minutes)} min)", "", section.content_md.strip(), ""]
        if section.type == "video" and content.videos:
            for v in content.videos:
                segment = f" — watch {v.watch_segment}" if v.watch_segment else ""
                lines.append(f"- ▶ [{v.title}]({v.url}) ({_fmt_minutes(v.duration_min)} min{segment}) — {v.why} [{v.sid}]")
            lines.append("")
        if section.type == "knowledge_check" and content.knowledge_check:
            lines += render_quiz(content)
            quiz_rendered = True

    if content.knowledge_check and not quiz_rendered:
        lines += ["## Knowledge check", "", *render_quiz(content)]

    cited = sorted(content.cited_sids() | set(content.references), key=lambda s: int(s[1:]))
    lines += ["## References", ""]
    lines += [render_reference(sources[sid]) for sid in cited if sid in sources]

    books = [sources[sid] for sid in getattr(content, "further_reading", []) if sid in sources]
    if books:
        lines += ["", "## Further reading", "",
                  "_Suggested books. Only their catalogue details and publisher descriptions were reviewed; "
                  "they were not used as evidence for this lesson._", ""]
        for book in books:
            year = book.metadata_json.get("year")
            by = f" — {book.publisher}" if book.publisher else ""
            link = f" <{book.url}>" if book.url else ""
            lines.append(f"- {book.title}{by}{f' ({year})' if year else ''}.{link}")
    return "\n".join(lines).rstrip() + "\n"
