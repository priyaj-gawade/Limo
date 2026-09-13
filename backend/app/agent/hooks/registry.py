"""Hook Registry managing lifecycle interceptors for agent execution."""

import logging
from typing import Any, Callable, Dict, List, Optional

from ..contracts import BaseHook, HookEvent

logger = logging.getLogger("limo.agent.hooks")


class SecurityViolationError(Exception):
    """Raised when a lifecycle hook detects an unsafe or unauthorized action."""
    pass


class HookRegistry:
    """Central registry dispatching lifecycle hooks across all agent execution stages."""

    def __init__(self):
        self._hooks: Dict[HookEvent, List[BaseHook]] = {event: [] for event in HookEvent}

    def register_hook(self, hook: BaseHook) -> None:
        """Register a hook instance for its declared HookEvent."""
        if hook.event not in self._hooks:
            self._hooks[hook.event] = []
        self._hooks[hook.event].append(hook)
        logger.debug("Registered hook %s for event %s", hook.__class__.__name__, hook.event.value)

    def unregister_hook(self, hook: BaseHook) -> None:
        """Unregister a hook instance."""
        if hook.event in self._hooks and hook in self._hooks[hook.event]:
            self._hooks[hook.event].remove(hook)

    def list_hooks(self, event: Optional[HookEvent] = None) -> List[BaseHook]:
        """List registered hooks, optionally filtered by HookEvent."""
        if event is not None:
            return list(self._hooks.get(event, []))
        all_hooks = []
        for hooks in self._hooks.values():
            all_hooks.extend(hooks)
        return all_hooks

    def clear(self) -> None:
        """Clear all registered hooks."""
        self._hooks = {event: [] for event in HookEvent}

    async def trigger(
        self,
        event: HookEvent,
        payload: Dict[str, Any],
        context: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Sequentially execute all hooks registered for an event.
        
        Each hook may inspect, validate, or mutate the payload.
        If a hook raises SecurityViolationError or ValueError, execution halts immediately.
        """
        current_payload = dict(payload)
        hooks = self._hooks.get(event, [])
        for hook in hooks:
            try:
                res = await hook.execute(current_payload, context)
                if isinstance(res, dict):
                    current_payload = res
            except Exception as e:
                logger.warning(
                    "Hook %s raised exception on event %s: %s",
                    hook.__class__.__name__,
                    event.value,
                    str(e),
                )
                raise
        return current_payload
