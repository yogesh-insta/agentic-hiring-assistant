locals {
  services = [
    "run.googleapis.com",
    "workflows.googleapis.com",
    "firestore.googleapis.com",
    "pubsub.googleapis.com",
    "storage.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com",
    "eventarc.googleapis.com",
    "identitytoolkit.googleapis.com",
    "aiplatform.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "billingbudgets.googleapis.com",
    "artifactregistry.googleapis.com",
    "firebaserules.googleapis.com",
  ]
}

resource "google_project_service" "required" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "api" {
  account_id   = "hiring-api"
  display_name = "Hiring API"
}

resource "google_service_account" "agents" {
  account_id   = "hiring-agents"
  display_name = "Hiring agents"
}

resource "google_service_account" "worker" {
  account_id   = "hiring-worker"
  display_name = "Hiring ingest worker"
}

resource "google_service_account" "workflow" {
  account_id   = "hiring-workflow"
  display_name = "Hiring workflow"
}

resource "google_service_account" "killswitch" {
  account_id   = "hiring-killswitch"
  display_name = "Hiring budget kill switch"
}

resource "google_cloud_run_v2_service" "api" {
  name     = "hiring-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  template {
    service_account = google_service_account.api.email
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.api_image
      ports {
        container_port = 8080
      }
      env {
        name  = "ENV"
        value = "cloud"
      }
      env {
        name  = "AGENTS_URL"
        value = google_cloud_run_v2_service.agents.uri
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "WORKFLOW_NAME"
        value = google_workflows_workflow.hiring.name
      }
      env {
        name  = "WORKFLOW_LOCATION"
        value = var.region
      }
      env {
        name  = "SESSION_SECRET"
        value = var.session_secret
      }
      env {
        name  = "HIRER_EMAIL"
        value = var.hirer_email
      }
      env {
        name  = "CANDIDATE_EMAIL"
        value = var.candidate_email
      }
      env {
        name  = "GOOGLE_CLIENT_ID"
        value = var.google_oauth_client_id
      }
    }
  }
  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_service" "agents" {
  name     = "hiring-agents"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  template {
    service_account = google_service_account.agents.email
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    timeout = "200s"
    containers {
      image = var.agents_image
      ports {
        container_port = 8080
      }
      env {
        name  = "ENV"
        value = "cloud"
      }
      env {
        name  = "FIRESTORE_PROJECT"
        value = var.project_id
      }
      env {
        name  = "WORKFLOW_SERVICE_ACCOUNT"
        value = google_service_account.workflow.email
      }
      env {
        name  = "API_SERVICE_ACCOUNT"
        value = google_service_account.api.email
      }
      env {
        name  = "WORKER_SERVICE_ACCOUNT"
        value = google_service_account.worker.email
      }
    }
  }
  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_service" "worker" {
  name     = "hiring-worker"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  template {
    service_account = google_service_account.worker.email
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.worker_image
      ports {
        container_port = 8080
      }
      env {
        name  = "ENV"
        value = "cloud"
      }
      env {
        name  = "PORT"
        value = "8080"
      }
      env {
        name  = "AGENTS_URL"
        value = google_cloud_run_v2_service.agents.uri
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "PUBSUB_SUBSCRIPTION"
        value = google_pubsub_subscription.cv.id
      }
    }
  }
  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_service_iam_member" "api_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "agents_workflow" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.agents.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.workflow.email}"
}

resource "google_cloud_run_v2_service_iam_member" "agents_worker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.agents.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_cloud_run_v2_service_iam_member" "agents_api" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.agents.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_callbacks" {
  project = var.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "killswitch_run" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.killswitch.email}"
}

resource "google_project_iam_member" "agents_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agents.email}"
}

resource "google_project_iam_member" "agents_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.agents.email}"
}

resource "google_project_iam_member" "worker_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_pubsub_topic_iam_member" "billing_publisher" {
  topic  = google_pubsub_topic.budget.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${var.project_number}@gcp-sa-billing.iam.gserviceaccount.com"
}

resource "google_pubsub_topic_iam_member" "dead_letter_publisher" {
  topic  = google_pubsub_topic.cv_dead.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${var.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "dead_letter_subscriber" {
  subscription = google_pubsub_subscription.cv.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${var.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_artifact_registry_repository" "hiring" {
  location      = var.region
  repository_id = "hiring"
  format        = "DOCKER"
  depends_on    = [google_project_service.required]
}

resource "google_firestore_database" "hiring" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
  depends_on  = [google_project_service.required]
}

resource "google_firebaserules_ruleset" "firestore" {
  source {
    files {
      name    = "firestore.rules"
      content = file("${path.module}/../firestore.rules")
    }
  }
  depends_on = [google_firestore_database.hiring, google_project_service.required]
}

resource "google_firebaserules_release" "firestore" {
  name         = "cloud.firestore"
  ruleset_name = google_firebaserules_ruleset.firestore.name
  depends_on   = [google_firebaserules_ruleset.firestore]
}

resource "google_storage_bucket" "cvs" {
  name                        = "${var.project_id}-hiring-cvs"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 30
    }
  }
}

resource "google_storage_bucket" "functions" {
  name                        = "${var.project_id}-hiring-functions"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
}

resource "google_pubsub_topic" "cv" {
  name = "cv-ingest"
}

resource "google_pubsub_topic" "cv_dead" {
  name = "cv-dead-letter"
}

resource "google_pubsub_topic" "budget" {
  name = "hiring-budget"
}

resource "google_pubsub_subscription" "cv" {
  name  = "cv-ingest"
  topic = google_pubsub_topic.cv.name
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.cv_dead.id
    max_delivery_attempts = 5
  }
}

resource "google_pubsub_subscription" "cv_dead" {
  name  = "cv-dead-letter"
  topic = google_pubsub_topic.cv_dead.name
}

resource "google_workflows_workflow" "hiring" {
  name            = "hiring"
  region          = var.region
  description     = "Hiring lifecycle. Step ids match the local runner."
  service_account = google_service_account.workflow.id
  source_contents = file("${path.module}/../../workflow/hiring.yaml")
  depends_on      = [google_project_service.required]
}

resource "google_identity_platform_config" "auth" {
  project = var.project_id
  sign_in {
    allow_duplicate_emails = false
  }
  depends_on = [google_project_service.required]
}

resource "google_identity_platform_default_supported_idp_config" "google" {
  enabled       = true
  idp_id        = "google.com"
  client_id     = var.google_oauth_client_id
  client_secret = var.google_oauth_client_secret
  project       = var.project_id
  depends_on    = [google_identity_platform_config.auth]
}

data "archive_file" "killswitch" {
  type        = "zip"
  source_dir  = "${path.module}/../killswitch"
  output_path = "${path.module}/.terraform/killswitch.zip"
}

resource "google_storage_bucket_object" "killswitch" {
  name   = "killswitch.zip"
  bucket = google_storage_bucket.functions.name
  source = data.archive_file.killswitch.output_path
}

resource "google_cloudfunctions2_function" "killswitch" {
  name     = "hiring-killswitch"
  location = var.region
  build_config {
    runtime     = "python311"
    entry_point = "on_budget"
    source {
      storage_source {
        bucket = google_storage_bucket.functions.name
        object = google_storage_bucket_object.killswitch.name
      }
    }
  }
  service_config {
    max_instance_count    = 1
    available_memory      = "256M"
    service_account_email = google_service_account.killswitch.email
    environment_variables = {
      REGION               = var.region
      SERVICES             = "hiring-api,hiring-agents,hiring-worker"
      GOOGLE_CLOUD_PROJECT = var.project_id
    }
  }
  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.budget.id
    retry_policy   = "RETRY_POLICY_DO_NOT_RETRY"
  }
  depends_on = [google_project_service.required]
}

resource "google_billing_budget" "demo" {
  billing_account = var.billing_account
  display_name    = "hiring-demo-aud-50"
  budget_filter {
    projects = ["projects/${var.project_number}"]
  }
  amount {
    specified_amount {
      currency_code = "AUD"
      units         = "50"
    }
  }
  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }
  all_updates_rule {
    pubsub_topic   = google_pubsub_topic.budget.id
    schema_version = "1.0"
  }
}

resource "google_logging_metric" "steps" {
  name   = "hiring_steps"
  filter = "jsonPayload.event=\"hiring_step\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    labels {
      key         = "outcome"
      value_type  = "STRING"
      description = "Step outcome"
    }
  }
  label_extractors = {
    outcome = "EXTRACT(jsonPayload.outcome)"
  }
}

resource "google_logging_metric" "kill_switch" {
  name   = "kill_switch_tripped"
  filter = "jsonPayload.event=\"kill_switch_tripped\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_notification_channel" "email" {
  display_name = "Hiring demo"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

resource "google_monitoring_alert_policy" "dead_letter" {
  display_name = "CV dead-letter depth is above zero"
  combiner     = "OR"
  conditions {
    display_name = "undelivered dead letters"
    condition_threshold {
      filter          = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" AND resource.labels.subscription_id=\"cv-dead-letter\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "60s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }
  notification_channels = [google_monitoring_notification_channel.email.id]
}

resource "google_monitoring_alert_policy" "kill_switch" {
  display_name = "Demo budget kill switch tripped"
  combiner     = "OR"
  conditions {
    display_name = "kill switch log"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/kill_switch_tripped\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "60s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
  notification_channels = [google_monitoring_notification_channel.email.id]
  depends_on            = [google_logging_metric.kill_switch]
}

resource "google_monitoring_alert_policy" "execute_failed" {
  display_name = "Approval execute failed"
  combiner     = "OR"
  conditions {
    display_name = "execute error log"
    condition_matched_log {
      filter = "jsonPayload.event=\"hiring_step\" AND jsonPayload.outcome=\"tool_error\""
    }
  }
  alert_strategy {
    notification_rate_limit {
      period = "300s"
    }
  }
  notification_channels = [google_monitoring_notification_channel.email.id]
}

resource "google_monitoring_custom_service" "hiring" {
  service_id   = "hiring-demo"
  display_name = "Hiring demo"
}

resource "google_monitoring_slo" "step_success" {
  service             = google_monitoring_custom_service.hiring.service_id
  slo_id              = "specialist-step-success"
  display_name        = "95 percent of specialist steps succeed over 7 days"
  goal                = 0.95
  rolling_period_days = 7
  request_based_sli {
    good_total_ratio {
      total_service_filter = "metric.type=\"logging.googleapis.com/user/hiring_steps\""
      good_service_filter  = "metric.type=\"logging.googleapis.com/user/hiring_steps\" AND metric.label.outcome=\"ok\""
    }
  }
  depends_on = [google_logging_metric.steps]
}

resource "google_monitoring_dashboard" "hiring" {
  dashboard_json = jsonencode({
    displayName = "Hiring demo"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          width  = 6
          height = 4
          widget = {
            title = "Dead-letter depth"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" resource.type=\"pubsub_subscription\" resource.label.subscription_id=\"cv-dead-letter\""
                  }
                }
              }]
            }
          }
        },
        {
          xPos   = 6
          width  = 6
          height = 4
          widget = {
            title = "Kill switch trips"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"logging.googleapis.com/user/kill_switch_tripped\""
                  }
                }
              }]
            }
          }
        }
      ]
    }
  })
}
