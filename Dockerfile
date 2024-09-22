FROM alpine:3.20

LABEL org.opencontainers.image.title="smfc"
LABEL org.opencontainers.image.authors="petersulyok"
LABEL org.opencontainers.image.desciption="Super Micro fan control for Linux (home) servers."
LABEL org.opencontainers.image.url="https://github.com/petersulyok/smfc"

RUN <<EOT
    set -xe
    apk add --no-cache ipmitool python3 smartmontools py3-udev
    ln -s /usr/sbin/ipmitool /usr/bin/ipmitool
    apk add --no-cache --virtual .depends git build-base linux-headers automake autoconf gettext-dev
    mkdir /tmp/build/
    cd /tmp/build/
    wget -O hddtemp.db.1 http://download.savannah.nongnu.org/releases/hddtemp/hddtemp.db
    wget -O hddtemp.db.2 https://gitweb.gentoo.org/repo/gentoo.git/plain/app-admin/hddtemp/files/hddgentoo.db
    cat hddtemp.db.1 hddtemp.db.2 > /usr/share/misc/hddtemp.db
    wget "https://savannah.gnu.org/cgi-bin/viewcvs/*checkout*/config/config/config.guess"
    wget "https://savannah.gnu.org/cgi-bin/viewcvs/*checkout*/config/config/config.sub"
    git clone https://github.com/vitlav/hddtemp.git
    cd hddtemp/
    autoreconf -vif
    ./configure --prefix=/usr --disable-nls
    make
    make install
    cd /
    rm -r /usr/share/man
    rm -r /tmp/build
    apk del .depends
EOT

WORKDIR /opt/smfc
ADD --chmod=755 src/smfc.py smfc.py

CMD /opt/smfc/smfc.py -c /opt/smfc/smfc.conf $SMFC_ARGS
