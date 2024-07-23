FROM --platform=linux/amd64 python:3.10

ARG DBOT_ARGS
ARG ENVIRONMENT=production
ARG COMMIT=""

RUN useradd --create-home avrae
USER avrae
WORKDIR /home/avrae

ENV GIT_COMMIT_SHA=${COMMIT}

COPY --chown=avrae:avrae requirements.txt .
RUN pip install --user --no-warn-script-location -r requirements.txt

COPY --chown=avrae:avrae . .

# Download AWS pubkey to connect to documentDB
RUN wget https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

ENTRYPOINT python dbot.py $DBOT_ARGS
