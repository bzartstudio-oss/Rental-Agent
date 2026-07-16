"""`WebDependencies` — the one place every existing engine/service instance
the web layer needs is constructed, once per process. See
docs/32_Web_Dashboard.md "Service Facade".

Nothing here is business logic — it's wiring, the same role
`RentalResearchAgent.__init__`'s own optional-engine parameters already play,
just at the process level instead of per-search.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.discovery.automatic.agent import AutomaticDiscoveryAgent
from src.feedback.engine import FeedbackEngine
from src.monitoring.engine import MonitoringEngine
from src.notifications.engine import NotificationEngine
from src.storage.database import Database
from src.web.configuration import WebConfiguration
from src.web.jobs.runner import JobRunner


@dataclass
class WebDependencies:
    db: Database
    configuration: WebConfiguration = field(default_factory=WebConfiguration.from_env)
    monitoring_engine: MonitoringEngine = field(default_factory=MonitoringEngine)
    notification_engine: NotificationEngine = field(default_factory=NotificationEngine)
    feedback_engine: FeedbackEngine = field(default_factory=FeedbackEngine)
    discovery_agent: AutomaticDiscoveryAgent = field(default_factory=AutomaticDiscoveryAgent)
    job_runner: JobRunner = field(init=False)

    def __post_init__(self) -> None:
        self.job_runner = JobRunner(self.db)
