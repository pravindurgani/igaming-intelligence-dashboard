"""
Content Brief Generator for Reader Advantage Briefs.

Generates markdown briefs from Advantage dicts that are ready
for editorial, product, and commercial teams.
"""

from datetime import datetime


def render_content_brief(advantage: dict) -> str:
    """
    Render a content brief from an Advantage dict.

    The brief includes:
    - Headline and 2-sentence value statement
    - 3 editorial bullet points
    - 2 product tasks
    - 2 commercial ideas
    - KPIs to track
    - Example links

    Args:
        advantage: Advantage dict from build_reader_advantages

    Returns:
        Markdown string ready for display or download
    """
    topic = advantage.get('topic', 'Unknown Topic')
    topic_name = advantage.get('topic_name', topic.split(',')[0].strip())
    reader_value = advantage.get('reader_value', '')
    evidence = advantage.get('evidence', {})
    our_articles = evidence.get('our_articles', 0)
    their_articles = evidence.get('their_articles', 0)
    examples = evidence.get('examples', [])

    do_more = advantage.get('do_more_of_this', [])
    product = advantage.get('product_enablers', [])
    commercial = advantage.get('commercial_levers', [])
    distribution = advantage.get('distribution', [])
    risk = advantage.get('risk_if_we_stop', '')
    kpis = advantage.get('kpis', [])

    # Build the brief
    lines = []

    # Header
    lines.append(f"# Content Brief: {topic_name}")
    lines.append("")
    lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")

    # Value Statement
    lines.append("## Why This Matters")
    lines.append("")
    lines.append(reader_value)
    lines.append("")
    lines.append(f"**Evidence:** We published {our_articles} articles vs {their_articles} from competitors in the last 30 days.")
    lines.append("")

    # Editorial Section
    lines.append("## Editorial Actions")
    lines.append("")
    for i, action in enumerate(do_more[:3], 1):
        lines.append(f"{i}. {action}")
    lines.append("")

    # Product Section
    lines.append("## Product Enablers")
    lines.append("")
    for i, task in enumerate(product[:2], 1):
        lines.append(f"{i}. {task}")
    lines.append("")

    # Commercial Section
    lines.append("## Commercial Ideas")
    lines.append("")
    for i, idea in enumerate(commercial[:2], 1):
        lines.append(f"{i}. {idea}")
    lines.append("")

    # Distribution
    if distribution:
        lines.append("## Distribution Notes")
        lines.append("")
        for note in distribution[:3]:
            lines.append(f"- {note}")
        lines.append("")

    # KPIs
    lines.append("## KPIs to Track")
    lines.append("")
    for kpi in kpis[:4]:
        lines.append(f"- {kpi}")
    lines.append("")

    # Risk
    lines.append("## Risk if We Stop")
    lines.append("")
    lines.append(f"> {risk}")
    lines.append("")

    # Example Articles
    if examples:
        lines.append("## Reference Articles")
        lines.append("")
        for ex in examples[:3]:
            title = ex.get('title', 'Untitled')
            link = ex.get('link', '#')
            date = ex.get('date', '')
            date_str = f" ({date})" if date else ""
            lines.append(f"- [{title}]({link}){date_str}")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("*Brief generated from Reader Advantage analysis.*")

    return "\n".join(lines)


def render_brief_preview(advantage: dict, max_lines: int = 15) -> str:
    """
    Render a short preview of the content brief.

    Args:
        advantage: Advantage dict
        max_lines: Maximum lines to include

    Returns:
        Truncated markdown string
    """
    full_brief = render_content_brief(advantage)
    lines = full_brief.split('\n')

    if len(lines) <= max_lines:
        return full_brief

    preview_lines = lines[:max_lines]
    preview_lines.append("")
    preview_lines.append("*[Preview truncated - click Generate to see full brief]*")

    return "\n".join(preview_lines)


def brief_to_dict(advantage: dict) -> dict:
    """
    Convert advantage to a structured brief dict for JSON export.

    Args:
        advantage: Advantage dict

    Returns:
        Structured dict suitable for JSON serialization
    """
    return {
        'topic': advantage.get('topic', ''),
        'topic_name': advantage.get('topic_name', ''),
        'generated_at': datetime.now().isoformat(),
        'value_statement': advantage.get('reader_value', ''),
        'evidence': {
            'our_articles': advantage.get('evidence', {}).get('our_articles', 0),
            'their_articles': advantage.get('evidence', {}).get('their_articles', 0),
        },
        'editorial_actions': advantage.get('do_more_of_this', [])[:3],
        'product_enablers': advantage.get('product_enablers', [])[:2],
        'commercial_ideas': advantage.get('commercial_levers', [])[:2],
        'distribution_notes': advantage.get('distribution', [])[:3],
        'kpis': advantage.get('kpis', [])[:4],
        'risk_if_we_stop': advantage.get('risk_if_we_stop', ''),
        'example_links': [
            ex.get('link', '') for ex in advantage.get('evidence', {}).get('examples', [])[:3]
        ]
    }
