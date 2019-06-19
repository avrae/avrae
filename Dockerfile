FROM python:3.6-stretch

ARG DBOT_ARGS
ARG ENVIRONMENT=production

RUN useradd --create-home avrae
USER avrae
WORKDIR /home/avrae

COPY --chown=avrae:avrae requirements.txt .
RUN pip install --user --no-warn-script-location -r requirements.txt

RUN mkdir temp

COPY --chown=avrae:avrae . .

COPY --chown=avrae:avrae docker/credentials-${ENVIRONMENT}.py credentials.py

# This is to disable Machine Learning spell search as per README.md
RUN if [ "$ENVIRONMENT" = "development" ] ; then sed -i '/from cogs5e.funcs.lookup_ml import ml_spell_search/d; s/, search_func=ml_spell_search//' cogs5e/lookup.py ; fi

ENTRYPOINT python dbot.py $DBOT_ARGS
