# GitLab Continuous Integration

The only actually required file for GitLab CI is
[.gitlab-ci.yml](/.gitlab-ci.yml) in the root of this repository,
which includes files from [/.gitlab/workflows](./workflows/). These in turn
may make use of support scripts in [/.gitlab/scripts](./scripts/).

The image file [Dockerfile.lobo-runner](./Dockerfile.lobo-runner) is used to
build the `lobot-runner` image that our CI server uses.
