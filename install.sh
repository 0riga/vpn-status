#!/usr/bin/env bash
set -euo pipefail

# Прямые ссылки на файлы в репозитории (ветка main).
BASE_URL="https://raw.githubusercontent.com/0riga/vpn-status/main"
INSTALL_DIR="/root/vpn-status"

command -v docker >/dev/null 2>&1 || { echo "Docker не найден. Установите Docker и повторите."; exit 1; }

echo "== Установка vpn-status в $INSTALL_DIR =="
mkdir -p "$INSTALL_DIR"

for f in app.py Dockerfile docker-compose.yml; do
    curl -fsSL "$BASE_URL/$f" -o "$INSTALL_DIR/$f"
done

cd "$INSTALL_DIR"

read -r -s -p "Введите API-токен (Enter — сгенерировать случайный): " TOKEN
echo
if [ -z "$TOKEN" ]; then
    TOKEN=$(openssl rand -hex 32)
    echo "Сгенерирован токен: $TOKEN"
    echo "Сохраните его — он понадобится в клиентском приложении."
fi

# Подставляем токен в docker-compose.yml (плейсхолдер REPLACE_ME из репозитория)
sed -i "s/API_TOKEN=.*/API_TOKEN=${TOKEN}/" docker-compose.yml

echo "== Собираю и запускаю контейнер =="
docker compose up -d --build

echo
echo "Готово. Проверка:"
echo "curl -H \"X-API-Token: ${TOKEN}\" http://127.0.0.1:8080/status"
