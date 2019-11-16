#!/bin/bash
# Usage: bash scripts/ecr_push.sh [production|nightly]
environment=${1:-production}
clusterName=avrae
imageName=avrae-bot
ecrRepo=avrae/$imageName
awsAccountId=$AWS_ACCOUNT_ID
ecrRegion=$ECR_REGION
ecsRegion=$ECS_REGION
travisBuildNumber=$TRAVIS_BUILD_NUMBER
clusterEnv=live
if [[ "$environment" = "production" ]]; then
    environmentTag=live
    serviceName=avrae-bot
else
    environmentTag=nightly
    serviceName=avrae-bot-nightly
fi

docker tag $imageName $awsAccountId.dkr.ecr.$ecrRegion.amazonaws.com/$ecrRepo:travis-build-$travisBuildNumber
docker tag $imageName $awsAccountId.dkr.ecr.$ecrRegion.amazonaws.com/$ecrRepo:$environmentTag
eval $(aws ecr get-login --region $ecrRegion --no-include-email)
docker push $awsAccountId.dkr.ecr.$ecrRegion.amazonaws.com/$ecrRepo
aws ecs update-service --cluster $clusterName-$clusterEnv --service $serviceName --force-new-deployment --region $ecsRegion
