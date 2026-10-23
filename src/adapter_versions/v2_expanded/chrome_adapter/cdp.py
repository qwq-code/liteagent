from __future__ import annotations

import json
import re
import time
from typing import Any

import pychrome

from .errors import AdapterError


def _tab_field(tab: Any, field: str, default: str = "") -> str:
    value = getattr(tab, "_kwargs", {}).get(field, default)
    return value if isinstance(value, str) else str(value)


def _tab_info(tab: Any, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "target_id": tab.id,
        "type": _tab_field(tab, "type", "page"),
        "url": _tab_field(tab, "url"),
        "title": _tab_field(tab, "title"),
    }


class CDPClient:
    def __init__(self, url: str = "http://127.0.0.1:1337") -> None:
        self.url = url.rstrip("/")
        self.browser = pychrome.Browser(url=self.url)

    def tabs(self) -> list[Any]:
        return [
            tab
            for tab in self.browser.list_tab()
            if getattr(tab, "type", "page") == "page"
        ]

    def list_tabs(self) -> list[dict[str, Any]]:
        return [_tab_info(tab, index) for index, tab in enumerate(self.tabs())]

    def select_tab(self, selector: dict[str, Any] | None = None) -> Any:
        selector = selector or {}
        tabs = self.tabs()
        if not tabs:
            raise AdapterError(
                "TAB_NOT_FOUND", "Chrome has no page tabs", http_status=404
            )
        if not selector:
            raise AdapterError(
                "TAB_SELECTOR_REQUIRED",
                "an exact Chrome tab selector is required; call tab.list first",
                {"tabs": [_tab_info(tab, index) for index, tab in enumerate(tabs)]},
                422,
            )
        matches = tabs
        if "target_id" in selector:
            matches = [tab for tab in matches if tab.id == selector["target_id"]]
        if "url" in selector:
            matches = [
                tab for tab in matches if _tab_field(tab, "url") == selector["url"]
            ]
        if "title" in selector:
            matches = [
                tab for tab in matches if _tab_field(tab, "title") == selector["title"]
            ]
        if "index" in selector:
            index = selector["index"]
            indexed = tabs[index] if index < len(tabs) else None
            matches = [indexed] if indexed is not None and indexed in matches else []
        if not matches:
            raise AdapterError(
                "TAB_NOT_FOUND", "no Chrome tab matched the selector", selector, 404
            )
        if len(matches) > 1:
            raise AdapterError(
                "TAB_AMBIGUOUS",
                "multiple Chrome tabs matched the selector",
                {
                    "selector": selector,
                    "matches": [_tab_info(tab, tabs.index(tab)) for tab in matches],
                },
                409,
            )
        return matches[0]

    def activate(self, tab: Any) -> None:
        self.browser.activate_tab(tab.id)

    @staticmethod
    def _run(tab: Any, callback):
        try:
            tab.start()
            tab.Runtime.enable()
            return callback(tab)
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(
                "CDP_ERROR", "Chrome CDP operation failed", str(exc), 502
            ) from exc
        finally:
            # Each Adapter action runs in a short-lived worker process. Closing
            # pychrome's websocket triggers a known JSONDecodeError in its
            # receive thread, so process exit is the clean disconnect here.
            pass

    def evaluate(self, tab: Any, expression: str, await_promise: bool = False) -> Any:
        def callback(current):
            response = current.Runtime.evaluate(
                expression=expression,
                returnByValue=True,
                awaitPromise=await_promise,
                userGesture=True,
            )
            if response.get("exceptionDetails"):
                raise AdapterError(
                    "PAGE_SCRIPT_FAILED",
                    "page expression failed",
                    response["exceptionDetails"],
                    422,
                )
            return response.get("result", {}).get("value")

        return self._run(tab, callback)

    def goto(self, tab: Any, url: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
        def callback(current):
            current.Page.enable()
            response = current.Page.navigate(url=url)
            if response.get("errorText"):
                raise AdapterError(
                    "NAVIGATION_FAILED", "Chrome navigation failed", response, 502
                )
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                state = (
                    current.Runtime.evaluate(
                        expression="document.readyState",
                        returnByValue=True,
                    )
                    .get("result", {})
                    .get("value")
                )
                if state in {"interactive", "complete"}:
                    break
                time.sleep(0.1)
            value = (
                current.Runtime.evaluate(
                    expression="({url:location.href,title:document.title,ready_state:document.readyState})",
                    returnByValue=True,
                )
                .get("result", {})
                .get("value")
            )
            return value or {"url": url}

        result = self._run(tab, callback)
        if isinstance(result, dict):
            tab._kwargs["url"] = result.get("url", tab._kwargs.get("url", ""))
            tab._kwargs["title"] = result.get("title", tab._kwargs.get("title", ""))
        self.activate(tab)
        return result

    def new_tab(self, url: str) -> Any:
        try:
            tab = self.browser.new_tab(url)
            self.activate(tab)
            return tab
        except Exception as exc:
            raise AdapterError(
                "CDP_ERROR", "failed to create Chrome tab", str(exc), 502
            ) from exc

    def close_tab(self, tab: Any) -> None:
        try:
            self.browser.close_tab(tab.id)
        except Exception as exc:
            raise AdapterError(
                "CDP_ERROR", "failed to close Chrome tab", str(exc), 502
            ) from exc

    def press(self, tab: Any, key: str) -> None:
        key_map = {
            "ENTER": ("Enter", "\r", 13),
            "TAB": ("Tab", "\t", 9),
            "ESCAPE": ("Escape", "", 27),
            "ARROWDOWN": ("ArrowDown", "", 40),
            "ARROWUP": ("ArrowUp", "", 38),
            "ARROWLEFT": ("ArrowLeft", "", 37),
            "ARROWRIGHT": ("ArrowRight", "", 39),
            "BACKSPACE": ("Backspace", "", 8),
            "DELETE": ("Delete", "", 46),
            "SPACE": (" ", " ", 32),
        }
        normalized = key.upper()
        if normalized not in key_map and len(key) != 1:
            raise AdapterError("INVALID_REQUEST", "unsupported key", {"key": key})
        dom_key, text, code = key_map.get(normalized, (key, key, ord(key.upper())))

        def callback(current):
            current.Input.dispatchKeyEvent(
                type="keyDown", key=dom_key, text=text, windowsVirtualKeyCode=code
            )
            current.Input.dispatchKeyEvent(
                type="keyUp", key=dom_key, windowsVirtualKeyCode=code
            )

        self._run(tab, callback)

    def print_pdf(self, tab: Any, landscape: bool, print_background: bool) -> bytes:
        def callback(current):
            current.Page.enable()
            response = current.Page.printToPDF(
                landscape=landscape,
                printBackground=print_background,
                marginTop=0,
                marginBottom=0,
                marginLeft=0,
                marginRight=0,
                preferCSSPageSize=True,
            )
            return response["data"]

        import base64

        return base64.b64decode(self._run(tab, callback))


def locator_expression(
    locator: dict[str, Any], operation: str, value: Any = None
) -> str:
    payload = json.dumps({"locator": locator, "operation": operation, "value": value})
    return f"""
(() => {{
  const spec = {payload};
  const roots = [document];
  for (let i = 0; i < roots.length; i++) {{
    const nodes = roots[i].querySelectorAll ? roots[i].querySelectorAll('*') : [];
    for (const node of nodes) if (node.shadowRoot) roots.push(node.shadowRoot);
  }}
  const all = roots.flatMap(root => Array.from(root.querySelectorAll ? root.querySelectorAll('*') : []));
  const norm = value => String(value || '').replace(/\\s+/g, ' ').trim();
  const exact = !!spec.locator.exact;
  const textMatches = (actual, expected) => exact ? norm(actual) === norm(expected) : norm(actual).includes(norm(expected));
  let matches = [];
  if (spec.locator.css) matches = roots.flatMap(root => Array.from(root.querySelectorAll(spec.locator.css)));
  else if (spec.locator.xpath) {{
    for (const root of roots) {{
      const doc = root.ownerDocument || document;
      const result = doc.evaluate(spec.locator.xpath, root, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      for (let i = 0; i < result.snapshotLength; i++) matches.push(result.snapshotItem(i));
    }}
  }} else if (spec.locator.text) matches = all.filter(node => textMatches(node.innerText || node.textContent, spec.locator.text));
  else if (spec.locator.label) {{
    const labels = all.filter(node => node.tagName === 'LABEL' && textMatches(node.innerText || node.textContent, spec.locator.label));
    for (const label of labels) {{
      if (label.control) matches.push(label.control);
      else if (label.htmlFor) {{ const found = document.getElementById(label.htmlFor); if (found) matches.push(found); }}
      else {{ const found = label.querySelector('input,textarea,select,[contenteditable=true]'); if (found) matches.push(found); }}
    }}
  }} else if (spec.locator.role) {{
    const implicit = node => {{
      const tag = (node.tagName || '').toLowerCase();
      if (tag === 'button') return 'button';
      if (tag === 'a' && node.href) return 'link';
      if (tag === 'select') return 'combobox';
      if (tag === 'textarea') return 'textbox';
      if (tag === 'input') return ['button','submit','reset'].includes(node.type) ? 'button' : 'textbox';
      return '';
    }};
    matches = all.filter(node => (node.getAttribute('role') || implicit(node)) === spec.locator.role);
    if (spec.locator.name) matches = matches.filter(node => textMatches(node.getAttribute('aria-label') || node.innerText || node.value || node.title, spec.locator.name));
  }}
  matches = [...new Set(matches)].filter(Boolean);
  const hasIndex = Number.isInteger(spec.locator.index);
  if (!hasIndex && matches.length > 1) return {{ok:false,error:'LOCATOR_AMBIGUOUS',count:matches.length}};
  const index = hasIndex ? spec.locator.index : 0;
  if (matches.length <= index) return {{ok:false,error:'LOCATOR_NOT_FOUND',count:matches.length}};
  const element = matches[index];
  if (spec.operation === 'inspect') return {{ok:true,count:matches.length,tag:element.tagName,text:norm(element.innerText || element.textContent),value:element.value ?? null,checked:element.checked ?? null,attributes:Object.fromEntries(Array.from(element.attributes || []).map(a => [a.name,a.value]))}};
  element.scrollIntoView({{block:'center',inline:'center'}});
  element.focus();
  if (spec.operation === 'click') {{ element.click(); return {{ok:true,count:matches.length}}; }}
  if (spec.operation === 'fill') {{
    if (element.isContentEditable) element.textContent = spec.value;
    else {{ const proto = element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype; const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set; if (setter) setter.call(element, spec.value); else element.value = spec.value; }}
    element.dispatchEvent(new InputEvent('input', {{bubbles:true,inputType:'insertText',data:spec.value}}));
    element.dispatchEvent(new Event('change', {{bubbles:true}}));
    return {{ok:true,value:element.value ?? element.textContent}};
  }}
  if (spec.operation === 'select') {{
    element.value = spec.value;
    element.dispatchEvent(new Event('input', {{bubbles:true}}));
    element.dispatchEvent(new Event('change', {{bubbles:true}}));
    return {{ok:true,value:element.value}};
  }}
  return {{ok:false,error:'UNSUPPORTED_OPERATION'}};
}})()
"""


def ensure_locator_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict) or not result.get("ok"):
        code = (
            result.get("error", "PAGE_OPERATION_FAILED")
            if isinstance(result, dict)
            else "PAGE_OPERATION_FAILED"
        )
        status = (
            404
            if code == "LOCATOR_NOT_FOUND"
            else 409
            if code == "LOCATOR_AMBIGUOUS"
            else 422
        )
        raise AdapterError(code, "page locator operation failed", result, status)
    return result


def url_matches(actual: str, expected: str, regex: bool = False) -> bool:
    return bool(re.search(expected, actual)) if regex else expected in actual
