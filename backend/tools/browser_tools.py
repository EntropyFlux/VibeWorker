import asyncio
import uuid
from typing import Dict, Any, Optional
from langchain_core.tools import tool
import logging

logger = logging.getLogger(__name__)

class BrowserGate:
    """Manages pending browser automation callbacks from the frontend."""
    def __init__(self):
        self._pending: Dict[str, Dict[str, Any]] = {}

    async def wait_for_callback(self, action: str, payload: dict, timeout: float = 300.0) -> dict:
        request_id = uuid.uuid4().hex[:8]
        event = asyncio.Event()
        
        self._pending[request_id] = {
            "event": event,
            "result": None
        }

        # Issue the SSE event to the frontend
        # The frontend expects 'approval_request' or a custom event.
        # We'll use 'approval_request' format to leverage the unified output_queue.
        # Actually, if we just rely on tool_start, the frontend might not get all args.
        # Let's import the specific module or use the security gate SSE callback.
        try:
            from security.gate import security_gate
            if security_gate._sse_callback:
                await security_gate._sse_callback({
                    "type": "browser_action_required",
                    "request_id": request_id,
                    "action": action,
                    "payload": payload
                })
            else:
                logger.warning("No SSE callback registered, frontend might not receive browser action.")
        except Exception as e:
            logger.error(f"Failed to send browser action SSE: {e}")

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            return {"status": "error", "message": "Browser action timed out."}

        pending_data = self._pending.pop(request_id, None)
        if pending_data and pending_data.get("result"):
            return pending_data["result"]
        return {"status": "error", "message": "No result provided."}

    def resolve_callback(self, request_id: str, result: dict) -> bool:
        if request_id in self._pending:
            self._pending[request_id]["result"] = result
            self._pending[request_id]["event"].set()
            return True
        return False

browser_gate = BrowserGate()

@tool
async def browser_open(url: str, require_focus: bool = True, wait_for_user: bool = False) -> Dict[str, Any]:
    """
    Open a webpage in the browser extension.

    IMPORTANT PROMPT INSTRUCTIONS FOR `require_focus` & `wait_for_user`:
    - Set `require_focus=False` (Background/Silent mode) when you only need to open the page to read/extract content or perform automated actions that do not require the user's attention. This prevents interrupting the user's workflow. `wait_for_user` MUST be False in this case.
    - Set `require_focus=True` (Foreground/Active mode) ONLY when the user explicitly needs to see the page, or when you want to visually present the final result to the user.
    - Set `wait_for_user=True` (ONLY valid if require_focus=True) when you encounter a scenario that requires manual user intervention before you can proceed (like a complex login, solving a CAPTCHA, or authenticating via a QR code). The system will inject a "Finish Work" button into the page and pause execution until the user clicks it.

    IMPORTANT USAGE NOTE:
    - If you are trying to read a URL using standard fetching tools (like `fetch_url`) and it fails, times out, or returns a block/CAPTCHA page, you should FALLBACK to this tool.
    - Open the page using `browser_open(..., require_focus=False)`, then use `browser_read` to extract the content, and finally `browser_close`.
    """
    return await browser_gate.wait_for_callback("OPEN", {"url": url, "require_focus": require_focus, "wait_for_user": wait_for_user})

@tool
async def browser_read() -> Dict[str, Any]:
    """
    Read the extracted markdown content of the currently focused browser tab.
    """
    return await browser_gate.wait_for_callback("READ", {})

@tool
async def browser_type(selector: str, text: str) -> Dict[str, Any]:
    """
    Simulate typing text into an input element (like a search bar or textarea) on the current browser page.

    Args:
        selector: A valid CSS selector to locate the target element (e.g., 'input[name="q"]').
        text: The string to type into the element.
    """
    return await browser_gate.wait_for_callback("TYPE", {"selector": selector, "text": text})

@tool
async def browser_click(selector: str) -> Dict[str, Any]:
    """
    Simulate a click on a specified element on the current browser page.

    Args:
        selector: A valid CSS selector to locate the target element to click.
    """
    return await browser_gate.wait_for_callback("CLICK", {"selector": selector})

@tool
async def browser_close() -> Dict[str, Any]:
    """
    Close the currently focused browser tab that was previously opened by `browser_open` if it is no longer needed.
    """
    return await browser_gate.wait_for_callback("CLOSE", {})

def get_browser_tools():
    """Returns the list of all browser automation tools."""
    return [
        browser_open,
        browser_read,
        browser_type,
        browser_click,
        browser_close
    ]
