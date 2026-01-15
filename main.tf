resource "yandex_iam_service_account" "bot_sa" {
  name        = "vvot24-tg-bot-sa"
  description = "vvot24-tg-bot-sa"
}

resource "yandex_resourcemanager_folder_iam_member" "bot_sa_roles" {
  folder_id = var.folder_id
  role      = "ai.languageModels.user"
  member    = "serviceAccount:${yandex_iam_service_account.bot_sa.id}"
}

resource "yandex_resourcemanager_folder_iam_member" "bot_sa_vision" {
  folder_id = var.folder_id
  role      = "ai.vision.user"
  member    = "serviceAccount:${yandex_iam_service_account.bot_sa.id}"
}

resource "yandex_resourcemanager_folder_iam_member" "bot_sa_storage" {
  folder_id = var.folder_id
  role      = "storage.editor"
  member    = "serviceAccount:${yandex_iam_service_account.bot_sa.id}"
}

resource "yandex_iam_service_account_static_access_key" "bot_sa_key" {
  service_account_id = yandex_iam_service_account.bot_sa.id
  description        = "vvot24-tg-bot-object-storage-key"
}

resource "yandex_iam_service_account_api_key" "bot_sa_api_key" {
  service_account_id = yandex_iam_service_account.bot_sa.id
  description        = "vvot24-tg-bot-gpt-vision-key"
}

resource "yandex_storage_bucket" "prompt_bucket" {
  bucket = "vvot24-tg-bot-prompts"
  
  depends_on = [yandex_iam_service_account_static_access_key.bot_sa_key]
}

resource "yandex_storage_object" "yandexgpt_prompt" {
  bucket     = yandex_storage_bucket.prompt_bucket.bucket
  key        = "yandexgpt_prompts.txt"
  source     = "${path.module}/prompts/yandexgpt_prompts.txt"
  access_key = yandex_iam_service_account_static_access_key.bot_sa_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.bot_sa_key.secret_key

  depends_on = [
    yandex_storage_bucket.prompt_bucket,
    yandex_resourcemanager_folder_iam_member.bot_sa_storage
  ]
}

data "archive_file" "function_zip" {
  type        = "zip"
  output_path = "${path.module}/src/function.zip"
  source {
    content  = file("${path.module}/src/main.py")
    filename = "main.py"
  }
  source {
    content  = file("${path.module}/src/requirements.txt")
    filename = "requirements.txt"
  }
}

resource "yandex_function" "telegram_bot" {
  name               = "vvot24-tg-bot-function"
  user_hash          = "vvot24-tg-bot"
  description        = "vvot24 Telegram bot"
  runtime            = "python311"
  entrypoint         = "main.handler"
  memory             = "128"
  execution_timeout  = "60"
  service_account_id = yandex_iam_service_account.bot_sa.id

  environment = {
    TG_BOT_TOKEN        = var.tg_bot_key
    BUCKET_NAME         = yandex_storage_bucket.prompt_bucket.bucket
    OBJECT_KEY          = yandex_storage_object.yandexgpt_prompt.key
    AWS_ACCESS_KEY_ID   = yandex_iam_service_account_static_access_key.bot_sa_key.access_key
    AWS_SECRET_ACCESS_KEY = yandex_iam_service_account_static_access_key.bot_sa_key.secret_key
    YANDEXGPT_API_KEY   = yandex_iam_service_account_api_key.bot_sa_api_key.secret_key
    VISION_API_KEY      = yandex_iam_service_account_api_key.bot_sa_api_key.secret_key
    YANDEX_FOLDER_ID    = var.folder_id
  }

  content {
    zip_filename = data.archive_file.function_zip.output_path
  }
}

# Создание публичного доступа к функции
resource "yandex_function_iam_binding" "telegram_bot_public" {
  function_id = yandex_function.telegram_bot.id
  role        = "serverless.functions.invoker"
  members     = ["system:allUsers"]
}

# Регистрация webhook при создании
resource "null_resource" "register_webhook" {
  triggers = {
    function_id = yandex_function.telegram_bot.id
    tg_bot_key  = var.tg_bot_key
  }

  provisioner "local-exec" {
    command = <<-EOT
      $url = "https://api.telegram.org/bot${var.tg_bot_key}/setWebhook"
      $body = '{"url": "https://functions.yandexcloud.net/${yandex_function.telegram_bot.id}"}'
      Invoke-RestMethod -Uri $url -Method Post -Body $body -ContentType "application/json"
    EOT
    interpreter = ["powershell", "-Command"]
  }

  depends_on = [yandex_function.telegram_bot, yandex_function_iam_binding.telegram_bot_public]
}

# Снятие webhook при уничтожении
resource "null_resource" "unregister_webhook" {
  triggers = {
    function_id = yandex_function.telegram_bot.id
    tg_bot_key = var.tg_bot_key
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      $url = "https://api.telegram.org/bot${self.triggers.tg_bot_key}/deleteWebhook"
      Invoke-RestMethod -Uri $url -Method Post
    EOT
    interpreter = ["powershell", "-Command"]
  }
}