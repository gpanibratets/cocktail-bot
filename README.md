# Cocktail Bot

Telegram-бот для получения рецептов коктейлей с изображениями из базы данных TheCocktailDB.

## Возможности

- `/start` — приветствие и описание бота
- `/random` — случайный коктейль с фото и рецептом
- `/search [название]` — поиск коктейля по названию
- `/ingredient [ингредиент]` — поиск по ингредиенту
- `/help` — справка по командам
- Inline-кнопки для удобной навигации

## Быстрый старт

### 1. Получение токена Telegram бота

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather)
2. Отправьте команду `/newbot`
3. Введите имя бота (например: `My Cocktail Bot`)
4. Введите username бота (например: `my_cocktail_bot`)
5. Скопируйте полученный токен

### 2. Установка

```bash
# Клонируйте репозиторий
git clone https://github.com/your-username/cocktail-bot.git
cd cocktail-bot

# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate  # Windows

# Установите зависимости
pip install -r requirements.txt
```

### 3. Настройка

```bash
# Создайте файл .env
cp .env.example .env

# Откройте .env и вставьте ваш токен
nano .env  # или любой редактор
```

Содержимое `.env`:
```
BOT_TOKEN=ваш_токен_от_botfather
```

### 4. Запуск

```bash
python bot.py
```

## Развёртывание на VPS (Timeweb)

### Подключение к серверу

```bash
ssh root@ваш_ip_адрес
```

### Установка необходимых пакетов

```bash
# Обновление системы
apt update && apt upgrade -y

# Установка Python 3.10+
apt install python3 python3-pip python3-venv git -y
```

### Клонирование и настройка проекта

```bash
# Переход в директорию
cd /opt

# Клонирование репозитория
git clone https://github.com/your-username/cocktail-bot.git
cd cocktail-bot

# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt

# Создание файла конфигурации
cp .env.example .env
nano .env  # вставьте ваш BOT_TOKEN
```

### Создание systemd service

```bash
# Создание файла сервиса
sudo nano /etc/systemd/system/cocktail-bot.service
```

Содержимое файла:

```ini
[Unit]
Description=Cocktail Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/cocktail-bot
Environment=PATH=/opt/cocktail-bot/venv/bin
ExecStart=/opt/cocktail-bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Запуск сервиса

```bash
# Перезагрузка конфигурации systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable cocktail-bot

# Запуск бота
sudo systemctl start cocktail-bot

# Проверка статуса
sudo systemctl status cocktail-bot
```

### Управление ботом

```bash
# Перезапуск
sudo systemctl restart cocktail-bot

# Остановка
sudo systemctl stop cocktail-bot

# Просмотр логов
sudo journalctl -u cocktail-bot -f

# Просмотр логов бота
tail -f /opt/cocktail-bot/bot.log
```

### Обновление бота

```bash
cd /opt/cocktail-bot
git pull
sudo systemctl restart cocktail-bot
```

## Структура проекта

```
cocktail-bot/
├── bot.py           # Главный файл бота
├── config.py        # Конфигурация
├── api_client.py    # Клиент TheCocktailDB API
├── handlers.py      # Обработчики команд
├── requirements.txt # Зависимости
├── .env             # Переменные окружения (не в git)
├── .env.example     # Пример .env файла
├── .gitignore       # Игнорируемые файлы
└── README.md        # Документация
```

## API

Бот использует бесплатное API [TheCocktailDB](https://www.thecocktaildb.com/api.php):

- Случайный коктейль: `random.php`
- Поиск по названию: `search.php?s={name}`
- Поиск по ингредиенту: `filter.php?i={ingredient}`
- Детали по ID: `lookup.php?i={id}`

## Лицензия

MIT License
