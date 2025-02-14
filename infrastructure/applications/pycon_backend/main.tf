locals {
  is_prod           = terraform.workspace == "production"
  admin_domain      = "admin"
  full_admin_domain = local.is_prod ? "${local.admin_domain}.pycon.it" : "${terraform.workspace}-${local.admin_domain}.pycon.it"
  db_connection     = var.enable_proxy ? "postgres://${data.aws_db_instance.database.master_username}:${module.common_secrets.value.database_password}@${data.aws_db_proxy.proxy[0].endpoint}:${data.aws_db_instance.database.port}/pycon" : "postgres://${data.aws_db_instance.database.master_username}:${module.common_secrets.value.database_password}@${data.aws_db_instance.database.address}:${data.aws_db_instance.database.port}/pycon"
  cdn_url           = local.is_prod ? "cdn.pycon.it" : "${terraform.workspace}-cdn.pycon.it"
}

data "aws_vpc" "default" {
  filter {
    name   = "tag:Name"
    values = ["pythonit-vpc"]
  }
}

data "aws_iam_role" "lambda" {
  name = "pythonit-lambda-role"
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  tags = {
    Type = "private"
  }
}

data "aws_security_group" "rds" {
  name = "pythonit-rds-security-group"
}

data "aws_security_group" "lambda" {
  name = "pythonit-lambda-security-group"
}

data "aws_db_instance" "database" {
  db_instance_identifier = "pythonit-${terraform.workspace}"
}

data "aws_db_proxy" "proxy" {
  count = var.enable_proxy ? 1 : 0
  name  = "pythonit-${terraform.workspace}-database-proxy"
}

data "aws_acm_certificate" "cert" {
  domain   = "*.pycon.it"
  statuses = ["ISSUED"]
  provider = aws.us
}

data "aws_elasticache_cluster" "redis" {
  cluster_id = "production-pretix"
}

data "aws_instance" "temporal_machine" {
  count = var.deploy_temporal ? 1 : 0

  filter {
    name   = "tag:Name"
    values = ["production-temporal-instance"]
  }
}

module "lambda" {
  source = "../../components/application_lambda"

  application        = local.application
  local_path         = local.local_path
  role_arn           = data.aws_iam_role.lambda.arn
  subnet_ids         = [for subnet in data.aws_subnets.private.ids : subnet]
  security_group_ids = [data.aws_security_group.rds.id, data.aws_security_group.lambda.id]
  env_vars = {
    DATABASE_URL                              = local.db_connection
    DEBUG                                     = "False"
    SECRET_KEY                                = module.secrets.value.secret_key
    MAPBOX_PUBLIC_API_KEY                     = module.secrets.value.mapbox_public_api_key
    SENTRY_DSN                                = module.secrets.value.sentry_dsn
    VOLUNTEERS_PUSH_NOTIFICATIONS_IOS_ARN     = module.secrets.value.volunteers_push_notifications_ios_arn
    VOLUNTEERS_PUSH_NOTIFICATIONS_ANDROID_ARN = module.secrets.value.volunteers_push_notifications_android_arn
    ALLOWED_HOSTS                             = "*"
    DJANGO_SETTINGS_MODULE                    = "pycon.settings.prod"
    ASSOCIATION_FRONTEND_URL                  = "https://associazione.python.it"
    AWS_MEDIA_BUCKET                          = aws_s3_bucket.backend_media.id
    AWS_REGION_NAME                           = aws_s3_bucket.backend_media.region
    SPEAKERS_EMAIL_ADDRESS                    = module.secrets.value.speakers_email_address
    EMAIL_BACKEND                             = "django_ses.SESBackend"
    PYTHONIT_EMAIL_BACKEND                    = "pythonit_toolkit.emails.backends.ses.SESEmailBackend"
    FRONTEND_URL                              = "https://pycon.it"
    PRETIX_API                                = "https://tickets.pycon.it/api/v1/"
    AWS_S3_CUSTOM_DOMAIN                      = local.cdn_url
    PRETIX_API_TOKEN                          = module.common_secrets.value.pretix_api_token
    PINPOINT_APPLICATION_ID                   = module.secrets.value.pinpoint_application_id
    FORCE_PYCON_HOST                          = local.is_prod
    SQS_QUEUE_URL                             = aws_sqs_queue.queue.id
    MAILCHIMP_SECRET_KEY                      = module.common_secrets.value.mailchimp_secret_key
    MAILCHIMP_DC                              = module.common_secrets.value.mailchimp_dc
    MAILCHIMP_LIST_ID                         = module.common_secrets.value.mailchimp_list_id
    USER_ID_HASH_SALT                         = module.secrets.value.userid_hash_salt
    AZURE_STORAGE_ACCOUNT_NAME                = module.secrets.value.azure_storage_account_name
    AZURE_STORAGE_ACCOUNT_KEY                 = module.secrets.value.azure_storage_account_key
    PLAIN_API                                 = "https://core-api.uk.plain.com/graphql/v1"
    PLAIN_API_TOKEN                           = module.secrets.value.plain_api_token
    CACHE_URL                                 = local.is_prod ? "redis://${data.aws_elasticache_cluster.redis.cache_nodes.0.address}/8" : "locmemcache://snowflake"
    TEMPORAL_ADDRESS                          = var.deploy_temporal ? "${data.aws_instance.temporal_machine[0].private_ip}:7233" : ""
    STRIPE_WEBHOOK_SIGNATURE_SECRET           = module.secrets.value.stripe_webhook_secret
    STRIPE_SUBSCRIPTION_PRICE_ID              = module.secrets.value.stripe_membership_price_id
    STRIPE_SECRET_API_KEY                     = module.secrets.value.stripe_secret_api_key
    PRETIX_WEBHOOK_SECRET                     = module.secrets.value.pretix_webhook_secret
    DEEPL_AUTH_KEY                            = module.secrets.value.deepl_auth_key
    FLODESK_API_KEY                           = module.secrets.value.flodesk_api_key
    FLODESK_SEGMENT_ID                        = module.secrets.value.flodesk_segment_id
    CELERY_BROKER_URL                         = "redis://${data.aws_elasticache_cluster.redis.cache_nodes.0.address}/5"
    CELERY_RESULT_BACKEND                     = "redis://${data.aws_elasticache_cluster.redis.cache_nodes.0.address}/6"
    PLAIN_INTEGRATION_TOKEN                   = module.secrets.value.plain_integration_token
    HASHID_DEFAULT_SECRET_SALT                = module.secrets.value.hashid_default_secret_salt
  }
}


module "api" {
  source = "../../components/http_api_gateway"

  application          = local.application
  use_domain           = false
  lambda_invoke_arn    = module.lambda.invoke_arn
  lambda_function_name = module.lambda.function_name
}


module "admin_distribution" {
  source = "../../components/cloudfront"

  application     = local.application
  zone_name       = "pycon.it"
  domain          = local.full_admin_domain
  certificate_arn = data.aws_acm_certificate.cert.arn
  origin_url      = module.api.cloudfront_friendly_endpoint
}
