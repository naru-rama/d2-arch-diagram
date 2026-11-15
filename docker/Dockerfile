# 同じ入力から同じ図を出すため、版をすべて固定する
FROM node:22-alpine@sha256:1314fb30ec37592d5845e5a160d522c0e680972aa534549940b8d73bde88481a

RUN apk add --no-cache chromium=156.0.8078.79-r0 python3 py3-fonttools=4.60.1-r1 curl unzip

WORKDIR /opt/aws-diagram
RUN npm init -y >/dev/null \
 && npm install --no-audit --no-fund libavoid-js@0.5.0-beta.5 puppeteer-core@25.17.0

ARG FONT_URL=https://raw.githubusercontent.com/google/fonts/7da950f21232dc96d330070ae4cd5b98f02026d3/ofl/bizudpgothic/BIZUDPGothic-Regular.ttf
RUN mkdir fonts && curl -fsSL -o fonts/BIZUDPGothic-Regular.ttf "$FONT_URL"

ARG ICONS_URL=https://d1.awsstatic.com/onedam/marketing-channels/website/public/shared/architecture-icon-release/Icon-package_07312026.5846e92413caa21490223536cc97f1269e44fa92.zip
RUN curl -fsSL -o /tmp/icons.zip "$ICONS_URL" \
 && unzip -q /tmp/icons.zip -d /tmp/icons \
 && mkdir icons \
 && find /tmp/icons -path '*__MACOSX*' -prune -o -type f \( -name '*_48.svg' -o -name '*_48_Light.svg' -o -path '*Group-Icons*_32.svg' \) -print \
    | grep -v '_Dark' | xargs -I{} cp {} icons/ \
 && rm -rf /tmp/icons /tmp/icons.zip
