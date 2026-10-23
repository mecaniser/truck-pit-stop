ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
WORKDIR /usr/src/app
COPY transform.cjs /tmp/backup-transform.cjs
RUN node /tmp/backup-transform.cjs
COPY --chown=node:node rehearsal-web.cjs backup-seed.cjs ./
USER node
CMD ["node", "rehearsal-web.cjs"]
