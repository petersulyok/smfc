FROM alpine:3.21.3
LABEL org.opencontainers.image.title="smfc"
LABEL org.opencontainers.image.authors="petersulyok"
LABEL org.opencontainers.image.desciption="Super Micro fan control for Linux (home) servers."
LABEL org.opencontainers.image.url="https://github.com/petersulyok/smfc"
RUN <<EOT
    set -xe
    apk add --no-cache ipmitool python3 py3-udev smartmontools
    ln -s /usr/sbin/ipmitool /usr/bin/ipmitool
    apk add --no-cache --virtual .depends py3-pip
    pip install --prefix=/usr smfc
    rm -r /usr/share/man
    apk del .depends
EOT
ADD --chmod=755 docker/entrypoint.sh /etc/smfc/entrypoint.sh
ENTRYPOINT ["/etc/smfc/entrypoint.sh"]
