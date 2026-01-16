1. Нужно создать файл terraform.tfvars в корневой директории проекта с текущим содержанием:
cloud_id          = "id облака"
folder_id         = "id папки"
tg_bot_key        = "id тг бота"

2. Создать сервисный аккаунт в yandex cloud, создать авторизованный ключ и в виде файла сохранить по пути: "~/.yc-keys/key.json"

3. Прописать по очереди:
   terraform init
   terraform plan
   terraform apply (yes)
