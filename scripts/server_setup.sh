#!/bin/bash
set -e  # 오류 발생시 즉시 종료

echo "=== 시스템 업데이트 ==="
sudo apt-get update
sudo apt-get upgrade -y

echo "=== Docker 공식 설치 ==="
# 기존 Docker 제거
sudo apt-get remove docker docker-engine docker.io containerd runc -y

# Docker GPG 키 + 저장소 추가
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y

echo "=== Docker 서비스 시작 ==="
sudo systemctl start docker
sudo systemctl enable docker

echo "=== 비-root 사용자 설정 ==="
sudo usermod -aG docker $USER
newgrp docker

echo "=== 애플리케이션 디렉토리 ==="
sudo mkdir -p /app/milkywayBot
sudo chown -R $(whoami):$(whoami) /app