"""Reject inconsistent model-selected inputs without choosing replacement values."""
from __future__ import annotations

import re
from typing import Any

from .completion_policy import canonical_action_request, effective_canonical_action


def argument_contract_errors(state: Any, action: str, arguments: dict) -> list[str]:
    domain, operation, params = canonical_action_request(state.domain, action, arguments)
    if domain == 'libreoffice_calc' and operation == 'range.write':
        target = params.get('range', params.get('used_range_a1'))
        values = params.get('values')
        match = re.fullmatch(r'\$?([A-Za-z]+)\$?([1-9][0-9]*):\$?([A-Za-z]+)\$?([1-9][0-9]*)', str(target))
        if match and isinstance(values, list) and values and all(isinstance(row, list) for row in values):
            # Preserve the adapter's documented flat-vector orientation rules.
            def column(label):
                result = 0
                for char in label.upper():
                    result = result * 26 + ord(char) - ord('A') + 1
                return result
            left, top, right, bottom = match.groups()
            rows, cols = int(bottom) - int(top) + 1, column(right) - column(left) + 1
            widths = {len(row) for row in values}
            if rows > 0 and cols > 0 and (len(values) != rows or widths != {cols}):
                return [f'RANGE_DIMENSIONS_MISMATCH: target has {rows} rows x {cols} columns; values has {len(values)} rows with widths {sorted(widths)}. No write executed. Re-read the intended headers/target and regenerate a matching rectangle and matrix; do not pad, drop or invent data.']
    if domain == 'thunderbird' and operation in {'attachments.save', 'messages.update_flags'}:
        supplied_id = params.get('message_id')
        if not isinstance(supplied_id, str):
            return []
        for event in reversed(state.events):
            if not event.executed or event.error:
                continue
            owner, read, _ = effective_canonical_action(event, state.domain)
            if (owner, read) != ('thunderbird', 'messages.query'):
                continue
            hint = (event.result or {}).get('context_hint', {})
            hint = hint.get('downstream_context', hint)
            if hint.get('folder') != params.get('folder_name'):
                continue
            messages = hint.get('messages', [])
            if any(m.get('message_id') == supplied_id for m in messages):
                return []
            if any(type(m.get('mailbox_index')) is int and str(m['mailbox_index']) == supplied_id for m in messages):
                return ['MESSAGE_SELECTOR_MISMATCH: message_id is a Message-ID header, not the mailbox row number. The latest messages.query returned this number as mailbox_index. Regenerate the call using the observed integer mailbox_index; omit message_id when no Message-ID was returned. No action executed.']
            break
    return []
