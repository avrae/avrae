FROM python:3.6-stretch

ARG DBOT_ARGS=
ARG ENVIRONMENT=production

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN mkdir temp

COPY . .
COPY docker/credentials-${ENVIRONMENT}.py credentials.py

ENTRYPOINT python dbot.py $DBOT_ARGS
