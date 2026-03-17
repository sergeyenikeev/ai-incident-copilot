"""Rule-based анализатор инцидентов для начальной версии workflow."""

from __future__ import annotations

from dataclasses import dataclass

from ai_incident_copilot.domain.enums import SeverityLevel


@dataclass(slots=True, frozen=True)
class SeverityAssessment:
    """Результат определения критичности инцидента."""

    severity: SeverityLevel
    priority_score: int


class RuleBasedIncidentAnalyzer:
    """Простой эвристический анализатор, готовый к последующей замене на LLM."""

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
        "dns",
    )

    def classify(self, title: str, description: str, metadata: dict[str, object]) -> str:
        """Классифицирует инцидент по тексту и метаданным."""

        haystack = self._normalize(title, description, metadata)
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
        """Определяет уровень критичности и приоритетный score."""

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
        """Определяет ветку рекомендации."""

        if classification == "security" or severity == SeverityLevel.CRITICAL:
            return "escalated"
        return "standard"

    def standard_recommendation(self, *, classification: str, severity: SeverityLevel) -> str:
        """Формирует стандартную рекомендацию."""

        return (
            f"Классификация: {classification}. "
            f"Критичность: {severity.value}. "
            "Проверьте последние деплои, состояние зависимостей, ключевые метрики и подготовьте rollback-план."
        )

    def escalated_recommendation(self, *, classification: str, severity: SeverityLevel) -> str:
        """Формирует усиленную рекомендацию для тяжёлых сценариев."""

        return (
            f"Классификация: {classification}. "
            f"Критичность: {severity.value}. "
            "Немедленно соберите war-room, ограничьте blast radius, зафиксируйте артефакты инцидента "
            "и инициируйте эскалацию на дежурную смену L2/L3."
        )

    @staticmethod
    def _normalize(title: str, description: str, metadata: dict[str, object]) -> str:
        parts = [title, description, " ".join(f"{key} {value}" for key, value in metadata.items())]
        return " ".join(parts).lower()

    @staticmethod
    def _contains_any(haystack: str, patterns: tuple[str, ...]) -> bool:
        return any(pattern in haystack for pattern in patterns)
