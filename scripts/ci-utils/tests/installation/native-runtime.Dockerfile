# Offline test image after the build. The older interpreters exercise rejection.
FROM debian:stretch-slim@sha256:abaa313c7e1dfe16069a1a42fa254014780f165d4fd084844602edbe29915e70 AS bash44
FROM debian:buster-slim@sha256:bb3dc79fddbca7e8903248ab916bb775c96ec61014b3d02b4f06043b604726dc AS bash50
FROM python:3.8-slim-bullseye@sha256:e191a71397fd61fbddb6712cd43ef9a2c17df0b5e7ba67607128554cd6bff267 AS python38
FROM docker:29.10.1-cli@sha256:4e60c31615e83523afbb59773b25d055c0da9edcd5f80a4c6a6eebad49de1a25 AS cli
FROM python:3.9-slim-bullseye@sha256:b9e06687fbfc57f6fe563e94e4c8751e39513dde89afc120dc6f56afe5ffc761 AS python39
FROM buildpack-deps:bullseye-curl@sha256:7c8d79c31eb106cca055357456a2fa89b10fa20f254da6fe3eca937439696c62 AS minimum

COPY --from=python39 /usr/local/ /usr/local/
COPY --from=bash50 /bin/bash /usr/local/bin/bash
COPY --from=bash44 /bin/bash /opt/below/bin/bash
COPY --from=bash44 /lib/*/libtinfo.so.5.* /usr/local/lib/
COPY --from=python38 /usr/local/bin/python3.8 /opt/below/bin/python3
COPY --from=python38 /usr/local/lib/python3.8/ /opt/below/lib/python3.8/
COPY --from=python38 /usr/local/lib/libpython3.8.so.1.0 /usr/local/lib/
COPY --from=cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=cli /usr/local/libexec/docker/cli-plugins/docker-buildx /usr/local/libexec/docker/cli-plugins/docker-buildx
COPY --from=cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
RUN ldconfig && bash --version && /opt/below/bin/bash --version && /opt/below/bin/python3 --version

# Both qualification controllers can be built without private registry access.
FROM python:3.13-trixie@sha256:f25cbd3f7c73c28bdcab476c93c93a2ec90970a8f5b8a7810533654207822390 AS current
COPY --from=cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=cli /usr/local/libexec/docker/cli-plugins/ /usr/local/libexec/docker/cli-plugins/
ADD --checksum=sha256:400d835466429a5fe6c77a62775a9173729d61dd43e05dfa893e8cf6cb511783 https://github.com/shellspec/shellspec/archive/refs/tags/0.28.1.tar.gz /tmp/shellspec.tar.gz
RUN apt-get update && apt-get install -y --no-install-recommends shellcheck shfmt && rm -rf /var/lib/apt/lists/* \
    && mkdir /opt/shellspec && tar -xzf /tmp/shellspec.tar.gz -C /opt/shellspec --strip-components=1 \
    && ln -s /opt/shellspec/shellspec /usr/local/bin/shellspec && rm /tmp/shellspec.tar.gz
