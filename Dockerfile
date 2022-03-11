FROM python:3.10

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
RUN if [ "$ENVIRONMENT" = "production" ]; then wget https://s3.amazonaws.com/rds-downloads/rds-combined-ca-bundle.pem; fi

ENTRYPOINT if [ "$ENVIRONMENT" = "production" ]; then .local/bin/ddtrace-run python dbot.py $DBOT_ARGS; else python dbot.py $DBOT_ARGS; fi
