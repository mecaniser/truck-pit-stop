ARG BASE_IMAGE=python:3.12-alpine
FROM ${BASE_IMAGE}
WORKDIR /srv
COPY serve.py revision /srv/
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["python", "/srv/serve.py"]
