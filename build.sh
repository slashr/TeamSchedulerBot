#!/bin/bash

# Check if an argument is provided
if [ -z "$1" ]; then
  echo "Please provide an image tag number as an argument."
  exit 1
fi

IMAGE_TAG=$1

docker build . -t slack-bot:latest --platform linux/amd64 && \
docker tag slack-bot:latest 641817342265.dkr.ecr.eu-central-1.amazonaws.com/team-scheduler-bot:v${IMAGE_TAG} && \
docker push 641817342265.dkr.ecr.eu-central-1.amazonaws.com/team-scheduler-bot:v${IMAGE_TAG}

