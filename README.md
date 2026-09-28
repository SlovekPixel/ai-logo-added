# Logo Overlay Mini-Site

Мини-сервис для массовой наклейки логотипа на фото из папки.

## Возможности

- Вход по единому 30-значному коду
- Блокировка сайта после 5 неверных попыток за день (глобально)
- Логотип: PNG / JPEG / WEBP / SVG (SVG растеризуется перед наложением)
- Размещение на примере фото (превью 1:1): ширина и отступ сверху в px, логотип всегда справа
- Пакетная обработка всех фото из выбранной папки
- Скачивание ZIP; исходники удаляются сразу, архив — через 20 минут

## Локальный запуск

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # или cp .env.example .env
python -m app
```

Откройте http://127.0.0.1:8000

В `.env`:

- `ACCESS_CODE` — ровно **30** символов
- `SECRET_KEY` — длинная случайная строка

Разблокировка: `python -m app unlock`

### Docker локально

```bash
docker compose up --build
```

## Выложить в интернет

### Вариант A — Railway (рекомендую, ~10 минут)

1. Залейте проект на GitHub (без `.env`).
2. На [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
3. Railway подхватит `Dockerfile`.
4. В **Variables** добавьте:

| Variable | Пример |
|----------|--------|
| `ACCESS_CODE` | ваш 30-символьный код |
| `SECRET_KEY` | длинная случайная строка |
| `COOKIE_SECURE` | `true` |
| `MAX_FILES` | `200` |
| `MAX_FILE_MB` | `10` |
| `MAX_TOTAL_MB` | `300` |

5. **Settings → Networking → Generate Domain** — получите публичный URL.
6. Разблокировка при необходимости: в Railway → сервис → **Shell** / one-off:

```bash
python -m app unlock
```

### Вариант B — Render

1. [render.com](https://render.com) → **New → Web Service** → ваш GitHub-репозиторий.
2. Runtime: **Docker** (или используйте `render.yaml`).
3. Те же env-переменные, что выше (`COOKIE_SECURE=true`).
4. Free-план может «засыпать» без трафика — для 2–3 человек обычно ок.

### Вариант C — временно с вашего ПК (самый быстрый)

ПК должен быть включён:

```bash
python -m app
```

В другом терминале (после установки [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/)):

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Или [ngrok](https://ngrok.com/): `ngrok http 8000`

Получите временный HTTPS-URL. Для продакшена лучше Railway/Render.

### Вариант D — свой VPS

```bash
docker compose up -d --build
```

Поставьте nginx/Caddy с HTTPS перед контейнером и `COOKIE_SECURE=true`.

## Лимиты (по умолчанию)

| Параметр | Значение |
|----------|----------|
| Файлов за раз | 200 |
| Размер файла | 10 МБ |
| Суммарно | 300 МБ |
| TTL ZIP | 20 минут |

Одновременно выполняется только одна генерация.

## Важно перед деплоем

- Смените `ACCESS_CODE` и `SECRET_KEY` (не оставляйте демо-значения).
- На HTTPS обязательно `COOKIE_SECURE=true`.
- `.env` не коммитьте в git.
