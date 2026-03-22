"""Unit-тесты rule-based анализатора."""

from ai_incident_copilot.application.workflows.rule_based import RuleBasedIncidentAnalyzer
from ai_incident_copilot.domain.enums import SeverityLevel


def test_classify_security_incident() -> None:
    analyzer = RuleBasedIncidentAnalyzer()

    classification = analyzer.classify(
        title="Признаки несанкционированного доступа",
        description="SIEM фиксирует множественные неуспешные попытки входа в prod.",
        metadata={"environment": "prod"},
    )

    assert classification == "security"


def test_determine_severity_for_prod_security_incident() -> None:
    analyzer = RuleBasedIncidentAnalyzer()

    assessment = analyzer.determine_severity(
        title="Security breach in production",
        description="Unauthorized access detected, service partially unavailable.",
        classification="security",
        metadata={"environment": "prod"},
    )

    assert assessment.severity in {SeverityLevel.HIGH, SeverityLevel.CRITICAL}
    assert assessment.priority_score >= 75


def test_choose_route_escalates_security_incident() -> None:
    analyzer = RuleBasedIncidentAnalyzer()

    route = analyzer.choose_route(classification="security", severity=SeverityLevel.HIGH)

    assert route == "escalated"


def test_classify_data_incident_from_metadata_hints() -> None:
    analyzer = RuleBasedIncidentAnalyzer()

    classification = analyzer.classify(
        title="Рост задержек чтения",
        description="Сервис отвечает медленнее обычного после ночного обслуживания.",
        metadata={"component": "postgres-replica", "team": "data-platform"},
    )

    assert classification == "data"


def test_determine_severity_for_customer_facing_payment_outage() -> None:
    analyzer = RuleBasedIncidentAnalyzer()

    assessment = analyzer.determine_severity(
        title="Payments unavailable in production",
        description="All users cannot complete checkout, global outage is ongoing.",
        classification="application",
        metadata={"service": "payments", "environment": "prod"},
    )

    assert assessment.severity == SeverityLevel.CRITICAL
    assert assessment.priority_score == 95


def test_recommendation_is_tailored_to_classification() -> None:
    analyzer = RuleBasedIncidentAnalyzer()

    recommendation = analyzer.standard_recommendation(
        classification="network",
        severity=SeverityLevel.HIGH,
    )

    assert "DNS" in recommendation or "ingress" in recommendation
