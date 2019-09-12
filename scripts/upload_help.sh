#!/bin/bash
fileName=shared/commands.json
bucketName=s3://media.avrae.io/
s3Region=us-east-1

aws s3 cp $fileName $bucketName --grants read=uri=http://acs.amazonaws.com/groups/global/AllUsers --region $s3Region
