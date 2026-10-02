variable "project_id" {
  type = string
}

variable "project_number" {
  type = string
}

variable "billing_account" {
  type = string
}

variable "region" {
  type    = string
  default = "australia-southeast1"
}

variable "alert_email" {
  type    = string
  default = "hirer@example.com"
}

variable "api_image" {
  type = string
}

variable "agents_image" {
  type = string
}

variable "worker_image" {
  type = string
}

variable "google_oauth_client_id" {
  type = string
}

variable "google_oauth_client_secret" {
  type      = string
  sensitive = true
}

variable "session_secret" {
  type      = string
  sensitive = true
}

variable "hirer_email" {
  type    = string
  default = "hirer@example.com"
}

variable "candidate_email" {
  type    = string
  default = "avery@example.com"
}
