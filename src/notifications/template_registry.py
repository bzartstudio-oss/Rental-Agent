"""`NotificationTemplateRegistry` — where every installed template is known.
Mirrors `NotificationChannelRegistry`'s own self-registration shape. Kept as
its own module (not merged into `registry.py`) since channels and templates
are genuinely different plugin families with different lifecycles — a
channel is chosen by preference, a template is chosen by event type.
"""

from __future__ import annotations

from src.notifications.base_template import NotificationTemplate
from src.notifications.exceptions import NotificationConfigurationError


class NotificationTemplateRegistry:
    _templates: dict[str, NotificationTemplate] = {}

    @classmethod
    def register(cls, template: NotificationTemplate) -> NotificationTemplate:
        if not isinstance(template, NotificationTemplate):
            raise NotificationConfigurationError(
                f"{template!r} is not a NotificationTemplate instance — register_notification_template() "
                "must be called with an instantiated NotificationTemplate subclass"
            )
        if not getattr(template, "template_name", None):
            raise NotificationConfigurationError(
                f"{type(template).__name__} must set a class-level `template_name` before it can be registered"
            )
        cls._templates[template.template_name] = template
        return template

    @classmethod
    def get(cls, template_name: str) -> NotificationTemplate:
        try:
            return cls._templates[template_name]
        except KeyError:
            raise NotificationConfigurationError(
                f"No notification template registered for {template_name!r}. Registered: {sorted(cls._templates)}"
            ) from None

    @classmethod
    def all(cls) -> list[NotificationTemplate]:
        return list(cls._templates.values())

    @classmethod
    def for_event_type(cls, event_type: str) -> NotificationTemplate | None:
        for template in cls._templates.values():
            if event_type in template.event_types:
                return template
        return None

    @classmethod
    def reset(cls) -> None:
        """Test-only: clears every registered template. Real code never calls this."""
        cls._templates.clear()


def register_notification_template(template: NotificationTemplate) -> NotificationTemplate:
    return NotificationTemplateRegistry.register(template)
