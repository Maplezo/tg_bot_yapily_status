# Yapily Status Telegram Bot 🤖🚨

Красивый и функциональный Telegram-бот для мониторинга в реальном времени состояния платежных шлюзов **Yapily** (как самой платформы, так и всех подключенных банков по странам).

Бот отфильтровывает лишний шум и фокусируется исключительно на важных инцидентах — присылает уведомления только о **🔴 критических сбоях (Major Outage)** и **🟡 частичных неполадках (Partial Outage / Degraded Performance)**.

---

## 🌟 Основные возможности

* **🔄 Мониторинг 24/7:** Автоматический опрос официального JSON API каждые 60 секунд.
* **🛡️ Умный фильтр (Без спама):** Оповещения присылаются только в случае реальных сбоев. Зеленый (Operational) статус и успешные плановые работы игнорируются для минимизации шума.
* **🌍 Полный охват банков (480+ компонентов):** Проверяет **100%** всех доступных шлюзов и банков (в отличие от стандартного API, которое возвращает только первые 25 записей).
* **🗺️ Группировка по странам:** Банки автоматически связываются со своими странами (используя кэшируемый парсер структуры сайта) и выводятся с красивыми флагами (например, 🇩🇪 `Germany`, 🇫🇷 `France`).
* **🔔 Мгновенные уведомления:**
  * 🆕 Регистрация новых инцидентов.
  * 🔄 Изменение статуса текущих инцидентов.
  * ✅ Уведомление о разрешении проблемы.
* **💬 Команды пользователя:**
  * `/start` — быстрая подписка на рассылку.
  * `/status` — моментальный запрос актуальных проблем на текущий момент.
  * `/help` — краткая справка по работе бота.

---

## 🏗️ Структура проекта

```
tg_bot_yapily_status/
├── storage.py        # Локальное хранилище подписчиков и инцидентов (db.json)
├── parser.py         # Парсер статусов и генератор маппинга банк ➔ страна
├── main.py           # Точка входа: инициализация бота и фонового мониторинга
├── .env.example      # Шаблон переменных окружения
└── .gitignore        # Исключения для чистой работы с Git
```

---

## 🚀 Быстрый старт

### 1. Подготовка
Убедитесь, что у вас установлен **Python 3.10+** и инструмент **pip**.

### 2. Клонирование и установка зависимостей
```bash
git clone git@github.com:Maplezo/tg_bot_yapily_status.git
cd tg_bot_yapily_status

# Создание и активация виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка необходимых библиотек
pip install pyTelegramBotAPI python-dotenv requests beautifulsoup4
```

### 3. Настройка переменных окружения
Создайте файл `.env` в корне проекта (или скопируйте его из примера) и добавьте токен вашего Telegram-бота, полученный от [@BotFather](https://t.me/BotFather):

```bash
cp .env.example .env
```

Содержимое `.env`:
```env
TELEGRAM_BOT_TOKEN=ваш_токен_бота
```

### 4. Запуск бота
Запустите бота следующей командой:
```bash
python3 main.py
```

При первом запуске бот автоматически соберет актуальный маппинг банков и стран (`country_map.json`), а также пометит текущие инциденты как "просмотренные", чтобы не спамить новых подписчиков при старте.

---

## 🐧 Запуск как systemd-демон (Linux)

Чтобы бот запускался автоматически при старте сервера и перезапускался при сбоях, настройте его как systemd-сервис.

### 1. Создайте файл сервиса

```bash
sudo nano /etc/systemd/system/yapily-bot.service
```

Вставьте содержимое (замените `/root/Yapily_bot` на ваш реальный путь):

```ini
[Unit]
Description=Yapily Status Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/Yapily_bot
ExecStart=/root/Yapily_bot/venv/bin/python3 /root/Yapily_bot/main.py
Restart=always
RestartSec=10
EnvironmentFile=/root/Yapily_bot/.env

[Install]
WantedBy=multi-user.target
```

### 2. Активируйте и запустите сервис

```bash
# Перечитать конфигурацию systemd
sudo systemctl daemon-reload

# Включить автозапуск при старте системы
sudo systemctl enable yapily-bot

# Запустить сервис прямо сейчас
sudo systemctl start yapily-bot
```

### 3. Проверка статуса и логов

```bash
# Статус сервиса
sudo systemctl status yapily-bot

# Логи в реальном времени
sudo journalctl -u yapily-bot -f

# Последние 100 строк логов
sudo journalctl -u yapily-bot -n 100
```

### 4. Управление сервисом

```bash
sudo systemctl stop yapily-bot      # остановить
sudo systemctl restart yapily-bot   # перезапустить
sudo systemctl disable yapily-bot   # убрать из автозапуска
```

---

## 📋 Как это выглядит в Telegram

### Запрос `/status` при наличии проблем:
> 🚨 **Обнаружены проблемы:**
>
> ━━━ **Активные инциденты** ━━━
>
> 🔴 **SEPA Payment Service Disruption**
>    📍 Источник: Yapily Platform
>    📊 Статус: `investigating`
>    🕐 Обновлено: 2026-05-19 10:20
>
> ━━━ **Компоненты с проблемами** ━━━
>
> **Yapily Platform:**
>   🟡 Payments — Partial Outage
>
> **Yapily Institutions:**
>
>   🇩🇪 **Germany**
>     🟡 Sparkasse — Degraded Performance
>     🟡 ING — Degraded Performance
>
>   🇳🇱 **Netherlands**
>     🟡 ABN AMRO — Partial Outage
