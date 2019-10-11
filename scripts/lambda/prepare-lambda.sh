#!/usr/bin/env bash
cd venv/lib/python3.7/site-packages
curl https://s3.amazonaws.com/rds-downloads/rds-combined-ca-bundle.pem -o rds-combined-ca-bundle.pem
zip -r9 ${OLDPWD}/function.zip .
cd $OLDPWD
zip -g function.zip *.py
