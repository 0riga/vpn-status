#!/usr/bin/env bash
set -euo pipefail

# ЗАМЕНИТЕ на адрес вашего репозитория после публикации на GitHub:
REPO_URL="https://github.com/YOUR_USERNAME/vpn-status.git"
INSTALL_DIR="/root/vpn-status"

command -v docker >/dev/null 2>&1 || { echo "Docker не найден. Установите Docker и повторите."; exit 1; }
command -v git >/dev/null 2>&1    || { echo "git не найден. Установите: apt install -y git"; exit 1; }

echo "== Установка vpn-status в $INSTALL_DIR =="

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Каталог уже существует, обновляю из репозитория..."
    git -C "$INSTALL_DIR" pull
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

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
