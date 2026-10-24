"""Batch coverage from public discovery, reads and output receipts only."""
from __future__ import annotations

import re
from typing import Any

from .completion_policy import effective_canonical_action


def _hint(event: Any) -> dict:
    result = event.result or {}
    hint = result.get('context_hint') or {}
    return hint.get('downstream_context', hint)


def _issue(code: str, remaining: list, message: str) -> dict:
    return {'code': code, 'kind': 'missing_observation', 'remaining_count': len(remaining),
            'remaining': remaining[:12], 'repair_actions': [], 'message': message}


def batch_coverage_issues(state: Any) -> list[dict]:
    """Do not infer unknown inputs or supply output names/content to the model."""
    text = str(state.instruction)
    events = [(e, *effective_canonical_action(e, state.domain), _hint(e))
              for e in state.events if e.executed and not e.error
              and e.proposed.get('kind') == 'adapter']
    issues = []
    if (re.search(r'(?i)\b(?:merge|concatenate|combine)\b', text)
        and re.search(r'(?i)\b(?:all|every)\b', text)
        and re.search(r'(?i)\.txt\b', text)):
        paths = set()
        read_spans = {}
        source_sizes = {}
        for _event, _domain, action, _args, hint in events:
            if action in {'workspace.find_files', 'filesystem.find'}:
                paths.update(m['path'] for m in hint.get('matches', [])
                             if isinstance(m, dict) and isinstance(m.get('path'), str)
                             and m['path'].lower().endswith('.txt') and m.get('kind') == 'file')
            if action == 'file.read_text':
                for file in hint.get('files', []):
                    if not isinstance(file, dict):
                        continue
                    path = file.get('path')
                    if not isinstance(path, str):
                        continue
                    total = file.get('source_total_chars')
                    if isinstance(total, int) and not isinstance(total, bool):
                        source_sizes[path] = total
                    for chunk in file.get('chunks', []):
                        start = chunk.get('start_char')
                        end = chunk.get('end_char')
                        content = chunk.get('text')
                        if (chunk.get('offset_basis') == 'unicode_characters'
                            and isinstance(start, int) and isinstance(end, int)
                            and isinstance(content, str) and end - start == len(content)):
                            read_spans.setdefault(path, []).append((start, end))
            # A model-selected shell command can consume files without returning
            # their text. This read-coverage check does not judge that alternate path.
            if action == 'command.run':
                paths.clear()
                read_spans.clear()
                source_sizes.clear()
        read_paths = set()
        for path, spans in read_spans.items():
            end = 0
            for start, stop in sorted(spans):
                if start > end:
                    break
                end = max(end, stop)
            if path in source_sizes and end >= source_sizes[path]:
                read_paths.add(path)
        missing = sorted(paths - read_paths)
        if missing:
            issues.append(_issue('unread_batch_sources', missing,
                f'{len(missing)} discovered text sources have not been fully read. '
                'Read their actual contents before composing the merged output; do not invent missing text. '
                f'Unobserved sources: {missing[:12]!r}'))
    if (re.search(r'(?i)\b(?:split|divide|separate)\b', text)
        and re.search(r'(?i)\b(?:each|every|all)\b', text)
        and re.search(r'(?i)\b(?:chapters?|sections?)\b', text)):
        outlines = {}
        outputs = {}
        for event, domain, action, _args, hint in events:
            if domain != 'os':
                continue
            if action == 'pdf.outline.inspect' and hint.get('input_path'):
                if hint.get('truncated') or hint.get('offset', 0) != 0:
                    continue
                sections = hint.get('sections', [])
                if not sections or len(sections) != hint.get('section_count'):
                    continue
                outlines[hint['input_path']] = (event.step, sections)
            if action == 'pdf.pages.extract' and hint.get('output_path'):
                # Latest receipt wins: overwriting one filename cannot count as
                # several simultaneously existing chapter outputs.
                outputs[hint['output_path']] = (event.step, hint)
            if action == 'command.run':
                outlines.clear()
                outputs.clear()
        missing = []
        for source, (step, sections) in outlines.items():
            covered = {(h.get('start_page'), h.get('end_page'))
                       for receipt_step, h in outputs.values()
                       if receipt_step > step and h.get('input_path') == source
                       and h.get('verification_passed') is True}
            for section in sections:
                if (section.get('start_page'), section.get('end_page')) not in covered:
                    missing.append({'source': source, **{k:section.get(k) for k in
                        ('title', 'start_page', 'end_page')}})
        if missing:
            issues.append(_issue('unconfirmed_pdf_sections', missing,
                f'{len(missing)} observed PDF sections lack a verified distinct output. '
                'These are unconfirmed, not known absent: inspect existing outputs or extract what remains. '
                f'Pending sections: {missing[:12]!r}'))
            issues[-1]['advisory'] = True  # Existing chapter files may already satisfy part of the request.
    return issues
