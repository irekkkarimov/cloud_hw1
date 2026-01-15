output "function_id" {
  description = "Cloud function id"
  value       = yandex_function.telegram_bot.id
}

output "function_url" {
  description = "Cloud function url"
  value       = "https://functions.yandexcloud.net/${yandex_function.telegram_bot.id}"
}

output "bucket_name" {
  description = "Object storage bucket name"
  value       = yandex_storage_bucket.prompt_bucket.bucket
}


