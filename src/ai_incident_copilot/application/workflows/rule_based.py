"""Rule-based incident analyzer for the initial workflow implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from ai_incident_copilot.domain.enums import SeverityLevel


@dataclass(slots=True, frozen=True)
class SeverityAssessment:
    """Severity and priority score returned by the analyzer."""

    severity: SeverityLevel
    priority_score: int


class RuleBasedIncidentAnalyzer:
    """Deterministic analyzer that can later be swapped with an LLM-backed one."""

    _SECURITY_KEYWORDS = (
        "security",
        "breach",
        "unauthorized",
        "credential",
        "attack",
        "ddos",
        "утечк",
        "взлом",
        "атак",
        "несанкционирован",
        "доступ",
        "вход",
        "siem",
    )
    _DATA_KEYWORDS = (
        "database",
        "db",
        "replication",
        "backup",
        "data loss",
        "postgres",
        "corruption",
        "данн",
        "репликац",
        "база",
    )
    _INFRA_KEYWORDS = (
        "cpu",
        "memory",
        "disk",
        "kubernetes",
        "container",
        "node",
        "latency",
        "timeout",
        "queue",
        "502",
        "503",
        "504",
        "диск",
        "очеред",
        "таймаут",
        "нод",
    )
    _NETWORK_KEYWORDS = (
        "network",
        "packet",
        "gateway",
        "dns",
        "ingress",
        "load balancer",
        "vpn",
        "сеть",
        "шлюз",
    )
    _CUSTOMER_IMPACT_KEYWORDS = (
        "all users",
        "customer-facing",
        "login failure",
        "checkout failure",
        "payments unavailable",
        "global outage",
        "mass outage",
        "массов",
        "все пользователи",
        "не могут войти",
        "не проходят платежи",
    )
    _BUSINESS_CRITICAL_SERVICE_KEYWORDS = (
        "auth",
        "login",
        "checkout",
        "payment",
        "payments",
        "billing",
        "gateway",
        "api-gateway",
    )
    _METADATA_CLASSIFICATION_HINTS: ClassVar[dict[str, tuple[str, ...]]] = {
        "security": ("siem", "soc", "waf", "iam", "security"),
        "data": ("postgres", "mysql", "redis", "clickhouse", "database", "replica"),
        "network": ("ingress", "gateway", "dns", "loadbalancer", "vpn", "network"),
        "infrastructure": ("kubernetes", "worker", "queue", "node", "cluster", "infra"),
    }

    def classify(self, title: str, description: str, metadata: dict[str, object]) -> str:
        """Classify the incident by text and metadata hints."""

        haystack = self._normalize(title, description, metadata)
        metadata_hint = self._classification_from_metadata(metadata)
        if metadata_hint is not None:
            return metadata_hint
        if self._contains_any(haystack, self._SECURITY_KEYWORDS):
            return "security"
        if self._contains_any(haystack, self._DATA_KEYWORDS):
            return "data"
        if self._contains_any(haystack, self._NETWORK_KEYWORDS):
            return "network"
        if self._contains_any(haystack, self._INFRA_KEYWORDS):
            return "infrastructure"
        return "application"

    def determine_severity(
        self,
        *,
        title: str,
        description: str,
        classification: str,
        metadata: dict[str, object],
    ) -> SeverityAssessment:
        """Calculate severity and priority score from incident signals."""

        haystack = self._normalize(title, description, metadata)
        score = 20

        if any(token in haystack for token in ("prod", "production", "прод", "боев")):
            score += 20
        if any(token in haystack for token in ("down", "outage", "unavailable", "недоступ", "отказ")):
            score += 25
        if any(token in haystack for token in ("queue", "backlog", "очеред", "накопил")):
            score += 15
        if classification == "security":
            score += 25
        if classification in {"data", "network"}:
            score += 15
        if self._contains_any(haystack, self._CUSTOMER_IMPACT_KEYWORDS):
            score += 20
        if self._contains_any(haystack, self._BUSINESS_CRITICAL_SERVICE_KEYWORDS):
            score += 15
        if any(token in haystack for token in ("critical", "p1", "sev1", "критич", "эвакуац")):
            score += 25

        if score >= 80:
            return SeverityAssessment(severity=SeverityLevel.CRITICAL, priority_score=95)
        if score >= 60:
            return SeverityAssessment(severity=SeverityLevel.HIGH, priority_score=75)
        if score >= 40:
            return SeverityAssessment(severity=SeverityLevel.MEDIUM, priority_score=50)
        return SeverityAssessment(severity=SeverityLevel.LOW, priority_score=25)

    def choose_route(self, *, classification: str, severity: SeverityLevel) -> str:
        """Choose the recommendation branch."""

        if classification == "security" or severity == SeverityLevel.CRITICAL:
            return "escalated"
        return "standard"

    def standard_recommendation(self, *, classification: str, severity: SeverityLevel) -> str:
        """Return a default recommendation for regular incidents."""

        next_step = self._recommendation_focus(classification)
        return (
            f"Классификация: {classification}. "
            f"Критичность: {severity.value}. "
            f"Проверьте последние деплои, состояние зависимостей и {next_step}. "
            "Подготовьте rollback-план и обновление статуса для дежурной смены."
        )

    def escalated_recommendation(self, *, classification: str, severity: SeverityLevel) -> str:
        """Return a stronger recommendation for severe incidents."""

        next_step = self._recommendation_focus(classification)
        return (
            f"Классификация: {classification}. "
            f"Критичность: {severity.value}. "
            f"Немедленно соберите war-room, ограничьте blast radius и проверьте {next_step}. "
            "Зафиксируйте артефакты инцидента и инициируйте эскалацию на дежурную смену L2/L3."
        )

    @classmethod
    def _classification_from_metadata(cls, metadata: dict[str, object]) -> str | None:
        metadata_values = " ".join(str(value).lower() for value in metadata.values())
        for classification, hints in cls._METADATA_CLASSIFICATION_HINTS.items():
            if any(hint in metadata_values for hint in hints):
                return classification
        return None

    @staticmethod
    def _recommendation_focus(classification: str) -> str:
        focus_map = {
            "security": "следы компрометации, IAM-события и scope затронутых аккаунтов",
            "data": "репликацию, свежесть бэкапов и риск потери данных",
            "network": "ingress, DNS, балансировку и сетевой маршрут до сервиса",
            "infrastructure": "нагрузку кластера, очередь задач и состояние нод",
            "application": "ошибки приложения, конфигурацию и внешние интеграции",
        }
        return focus_map.get(classification, "ключевые метрики и зависимости")

    @staticmethod
    def _normalize(title: str, description: str, metadata: dict[str, object]) -> str:
        """Merge input fields into one normalized search string."""

        parts = [title, description, " ".join(f"{key} {value}" for key, value in metadata.items())]
        return " ".join(parts).lower()

    @staticmethod
    def _contains_any(haystack: str, patterns: tuple[str, ...]) -> bool:
        """Check whether at least one pattern appears in the text."""

        return any(pattern in haystack for pattern in patterns)
