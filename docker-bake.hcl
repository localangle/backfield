variable "APP_VERSION" {
  default = "0.0.0-dev"
}

variable "GIT_SHA" {
  default = "unknown"
}

variable "BUILD_TIME" {
  default = "unknown"
}

variable "IMAGE_PREFIX" {
  # Empty for local builds; CI sets "<account>.dkr.ecr.<region>.amazonaws.com/".
  default = ""
}

variable "IMAGE_TAG" {
  default = "prod"
}

group "default" {
  targets = ["agate-api", "core-api", "stylebook-api", "worker"]
}

target "_common" {
  context   = "."
  platforms = ["linux/amd64"]
  pull      = true
  args = {
    APP_VERSION = APP_VERSION
    GIT_SHA      = GIT_SHA
    BUILD_TIME   = BUILD_TIME
  }
}

target "agate-api" {
  inherits   = ["_common"]
  dockerfile = "apps/agate-api/Dockerfile"
  target     = "prod"
  tags       = ["${IMAGE_PREFIX}backfield-agate-api:${IMAGE_TAG}"]
}

target "core-api" {
  inherits   = ["_common"]
  dockerfile = "apps/core-api/Dockerfile"
  target     = "prod"
  tags       = ["${IMAGE_PREFIX}backfield-core-api:${IMAGE_TAG}"]
}

target "stylebook-api" {
  inherits   = ["_common"]
  dockerfile = "apps/stylebook-api/Dockerfile"
  target     = "prod"
  tags       = ["${IMAGE_PREFIX}backfield-stylebook-api:${IMAGE_TAG}"]
}

target "worker" {
  inherits   = ["_common"]
  dockerfile = "apps/worker/Dockerfile"
  target     = "prod"
  tags       = ["${IMAGE_PREFIX}backfield-worker:${IMAGE_TAG}"]
}
