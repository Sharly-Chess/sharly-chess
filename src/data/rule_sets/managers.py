from typing import override

from data.rule_sets.rule_sets import RuleSet
from plugins.manager import plugin_manager
from utils.entity import EventBoundEntityManager
from utils.enum import EventType


class RuleSetManager(EventBoundEntityManager[RuleSet]):
    """Registry of plugin-contributed rule sets. Use
    :meth:`for_event_type` to filter the registry down to the rule
    sets applicable to a specific event type."""

    @override
    def entity_types(self) -> list[type[RuleSet]]:
        rule_sets: list[type[RuleSet]] = []
        plugin_manager.hook_for_event(self.event, 'insert_rule_sets')(
            rule_sets=rule_sets
        )
        return rule_sets

    def for_event_type(self, event_type: EventType) -> list[RuleSet]:
        """Rule-set instances applicable to *event_type*. Empty list
        when no plugin contributes any — the tournament modal hides
        the picker in that case."""
        return [
            rule_set for rule_set in self.objects() if rule_set.event_type == event_type
        ]
