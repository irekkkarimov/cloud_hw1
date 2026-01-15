variable "cloud_id" {
  description = "Yandex Cloud id"
  type        = string
}

variable "folder_id" {
  description = "Yandex Cloud folder id"
  type        = string
}

variable "tg_bot_key" {
  description = "tg bot api key"
  type        = string
  sensitive   = true
}


