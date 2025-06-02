FROM alpine:3.22
ARG BUILD_IMAGE_VERSION
LABEL org.opencontainers.image.version=${BUILD_IMAGE_VERSION}
LABEL org.opencontainers.image.title="smfc"
LABEL org.opencontainers.image.authors="petersulyok"
LABEL org.opencontainers.image.desciption="Super Micro fan control for Linux (home) servers."
LABEL org.opencontainers.image.url="https://github.com/petersulyok/smfc"
RUN apk add --no-cache ipmitool python3 py3-udev smartmontools
RUN ln -s /usr/sbin/ipmitool /usr/bin/ipmitool
RUN apk add --no-cache --virtual .depends py3-pip
RUN pip install --prefix=/usr smfc==${BUILD_IMAGE_VERSION}
RUN rm -r /usr/share/man
RUN apk del .depends
ADD --chmod=755 docker/entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
