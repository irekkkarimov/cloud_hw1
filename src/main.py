import os
import json
import logging
import boto3
import base64
from botocore.client import Config
import requests
from typing import Dict, Any

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Константы для сообщений
START_MESSAGE = (
    "Я помогу ответить на экзаменационный вопрос по «Операционным системам».\n"
    "Присылайте вопрос — фото или текстом."
)
INCORRECT_QUESTION_MESSAGE = (
    "Я не могу понять вопрос.\n"
    "Пришлите экзаменационный вопрос по «Операционным системам» — фото или текстом."
)
CANT_PREPARE_ANSWER_MESSAGE = "Я не смог подготовить ответ на экзаменационный вопрос."
MULTIPLE_PHOTO_MESSAGE = "Я могу обработать только одну фотографию."
CANT_PROCESS_PHOTO_MESSAGE = "Я не могу обработать эту фотографию."
INCORRECT_CONTENT_MESSAGE = "Я могу обработать только текстовое сообщение или фотографию."


def get_env_var(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Environment variable {name} is not set")
    return value


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        if "body" in event:
            if isinstance(event["body"], str):
                body = json.loads(event["body"])
            else:
                body = event["body"]
        elif "httpMethod" in event:
            if "body" in event and event["body"]:
                body = json.loads(event["body"])
            else:
                return {
                    "statusCode": 200,
                    "body": json.dumps({"ok": True})
                }
        else:
            body = event

        result = handle_tg_update(body)

        return {
            "statusCode": result.get("statusCode", 200),
            "body": result.get("body", json.dumps({"ok": True})),
            "headers": {
                "Content-Type": "application/json"
            }
        }
    except Exception as e:
        logger.error(f"Handler error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
            "headers": {
                "Content-Type": "application/json"
            }
        }


def handle_tg_update(update: Dict[str, Any]) -> Dict[str, Any]:
    try:
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")

        if not chat_id:
            return {"statusCode": 200}

        # text message processing
        if "text" in message:
            text = message["text"]

            if text in ["/start", "/help"]:
                send_message(chat_id, START_MESSAGE)
                return {"statusCode": 200}

            try:
                prompt = get_prompt_for_yandexgpt()

                if not classify_question(text, prompt):
                    send_message(chat_id, INCORRECT_QUESTION_MESSAGE)
                    return {"statusCode": 200}

                answer = generate_answer(text, prompt)
                send_message(chat_id, answer)
                return {"statusCode": 200}
            except Exception as e:
                logger.error(f"Error processing text message: {e}")
                send_message(chat_id, CANT_PREPARE_ANSWER_MESSAGE)
                return {"statusCode": 200}

        # photo message processing
        elif "photo" in message:
            if "media_group_id" in message and message.get("media_group_id"):
                send_message(chat_id, MULTIPLE_PHOTO_MESSAGE)
                return {"statusCode": 200}

            photos = message["photo"]

            photo = photos[-1]
            file_id = photo.get("file_id")

            if not file_id:
                send_message(chat_id, CANT_PROCESS_PHOTO_MESSAGE)
                return {"statusCode": 200}

            try:
                recognized_text = process_photo(file_id)

                if not recognized_text.strip():
                    send_message(chat_id, CANT_PROCESS_PHOTO_MESSAGE)
                    return {"statusCode": 200}

                prompt = get_prompt_for_yandexgpt()

                if not classify_question(recognized_text, prompt):
                    send_message(chat_id, INCORRECT_QUESTION_MESSAGE)
                    return {"statusCode": 200}

                answer = generate_answer(recognized_text, prompt)
                send_message(chat_id, answer)
                return {"statusCode": 200}
            except Exception as e:
                logger.error(f"Error when processing photo: {e}")
                send_message(chat_id, CANT_PROCESS_PHOTO_MESSAGE)
                return {"statusCode": 200}

        # Обработка других типов сообщений
        else:
            send_message(chat_id, INCORRECT_CONTENT_MESSAGE)
            return {"statusCode": 200}

    except Exception as e:
        logger.error(f"Error handling telegram update: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def get_prompt_for_yandexgpt() -> str:
    bucket_name = get_env_var("BUCKET_NAME")
    object_key = get_env_var("OBJECT_KEY")
    access_key_id = get_env_var("AWS_ACCESS_KEY_ID")
    secret_access_key = get_env_var("AWS_SECRET_ACCESS_KEY")

    session = boto3.session.Session()
    s3 = session.client(
        service_name='s3',
        endpoint_url='https://storage.yandexcloud.net',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=Config(signature_version='s3v4')
    )
    
    try:
        response = s3.get_object(Bucket=bucket_name, Key=object_key)
        return response['Body'].read().decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to get prompt from Object Storage: {e}")
        raise


def classify_question(text: str, prompt: str) -> bool:
    """Классифицировать, является ли текст экзаменационным вопросом."""
    yandexgpt_api_key = get_env_var("YANDEXGPT_API_KEY")
    folder_id = get_env_var("YANDEX_FOLDER_ID")
    
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {yandexgpt_api_key}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""{prompt}

Задача: Определи, является ли следующий текст экзаменационным вопросом по операционным системам.

Текст: {text}

Ответь только "да" или "нет"."""
    
    payload = {
        "modelUri": f"gpt://{folder_id}/yandexgpt/latest",
        "completionOptions": {
            "stream": False,
            "temperature": 0.5,
            "maxTokens": 20
        },
        "messages": [
            {
                "role": "user",
                "text": prompt
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        answer = result.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text", "").strip().lower()
        return "да" in answer or "yes" in answer
    except Exception as e:
        logger.error(f"Error from Yandex GPT when classifing question: {e}")
        return False


def generate_answer(question: str, prompt: str) -> str:
    yandexgpt_api_key = get_env_var("YANDEXGPT_API_KEY")
    folder_id = get_env_var("YANDEX_FOLDER_ID")
    
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {yandexgpt_api_key}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""{prompt}

Вопрос: {question}

Подготовь развернутый ответ на этот экзаменационный вопрос."""
    
    payload = {
        "modelUri": f"gpt://{folder_id}/yandexgpt/latest",
        "completionOptions": {
            "stream": False,
            "temperature": 0.3,
            "maxTokens": 2000
        },
        "messages": [
            {
                "role": "user",
                "text": prompt
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        answer = result.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text", "")
        return answer.strip()
    except Exception as e:
        logger.error(f"Failed to get answer from YandexGPT: {e}")
        raise


def process_photo(file_id: str) -> str:
    tg_bot_token = get_env_var("TG_BOT_TOKEN")
    vision_api_key = get_env_var("VISION_API_KEY")

    file_url = f"https://api.telegram.org/bot{tg_bot_token}/getFile?file_id={file_id}"
    file_response = requests.get(file_url)
    file_response.raise_for_status()
    file_path = file_response.json()["result"]["file_path"]

    download_url = f"https://api.telegram.org/file/bot{tg_bot_token}/{file_path}"
    file_data = requests.get(download_url).content

    vision_url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
    headers = {
        "Authorization": f"Api-Key {vision_api_key}",
        "Content-Type": "application/json"
    }

    image_base64 = base64.b64encode(file_data).decode('utf-8')
    
    payload = {
        "folderId": get_env_var("YANDEX_FOLDER_ID"),
        "analyze_specs": [
            {
                "content": image_base64,
                "features": [
                    {
                        "type": "TEXT_DETECTION",
                        "text_detection_config": {
                            "language_codes": ["*"]
                        }
                    }
                ]
            }
        ]
    }
    
    try:
        response = requests.post(vision_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        text_blocks = []
        results = result.get("results", [])
        if results:
            text_detection = results[0].get("results", [{}])[0].get("textDetection", {})
            pages = text_detection.get("pages", [])
            for page in pages:
                blocks = page.get("blocks", [])
                for block in blocks:
                    lines = block.get("lines", [])
                    for line in lines:
                        words = line.get("words", [])
                        line_text = " ".join([word.get("text", "") for word in words])
                        if line_text:
                            text_blocks.append(line_text)
        
        return "\n".join(text_blocks)
    except Exception as e:
        logger.error(f"Failed to recognize text from photo: {e}")
        raise


def send_message(chat_id: int, text: str) -> None:
    tg_bot_token = get_env_var("TG_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{tg_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
