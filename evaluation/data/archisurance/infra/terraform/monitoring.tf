# Monitoring Server (Node) — Elasticsearch (SystemSoftware)
# TechnologyService: Monitoring, Logging, Alerting

resource "google_monitoring_alert_policy" "high_error_rate" {
  display_name = "High Error Rate — Claims Service"
  combiner     = "OR"

  conditions {
    display_name = "Error rate > 5%"
    condition_threshold {
      filter          = "resource.type = \"k8s_container\" AND metric.type = \"logging.googleapis.com/user/error_count\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5
    }
  }

  notification_channels = []

  documentation {
    content   = "High error rate detected on Claims Management Platform. Check application logs and database connectivity to PostgreSQL 15."
    mime_type = "text/markdown"
  }

  labels = {
    environment = var.environment
    team        = "claims-team"
    service     = "claims-management-platform"
  }
}

resource "google_logging_metric" "claims_errors" {
  name   = "claims-service-errors"
  filter = "resource.type=\"k8s_container\" AND resource.labels.container_name=\"claims-service\" AND severity>=ERROR"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}
