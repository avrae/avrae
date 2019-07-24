#!/bin/bash
clusterName=avrae
serviceName=avrae-bot
ecrRepo=avrae/$serviceName
awsAccountId=$AWS_ACCOUNT_ID
ecrRegion=$ECR_REGION
ecsRegion=$ECS_REGION
travisBuildNumber=$TRAVIS_BUILD_NUMBER
env=live
defaultEnvironmentTag=live

docker tag $serviceName $awsAccountId.dkr.ecr.$ecrRegion.amazonaws.com/$ecrRepo:travis-build-$travisBuildNumber
docker tag $serviceName $awsAccountId.dkr.ecr.$ecrRegion.amazonaws.com/$ecrRepo:$defaultEnvironmentTag
eval $(aws ecr get-login --region $ecrRegion --no-include-email)
docker push $awsAccountId.dkr.ecr.$ecrRegion.amazonaws.com/$ecrRepo
aws ecs update-service --cluster $clusterName-$env --service $serviceName --force-new-deployment --region $ecsRegion
