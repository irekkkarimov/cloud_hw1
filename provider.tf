terraform {
  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
      version = "~> 0.100"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
  required_version = ">= 1.0"
}

provider "yandex" {
  cloud_id                 = var.cloud_id
  folder_id               = var.folder_id
  zone                    = "ru-central1-d"
  service_account_key_file = pathexpand("~/.yc-keys/key.json")
}

