output "region" {
  value = var.region
}

output "workflow_name" {
  value = google_workflows_workflow.hiring.name
}

output "budget_topic" {
  value = google_pubsub_topic.budget.name
}
