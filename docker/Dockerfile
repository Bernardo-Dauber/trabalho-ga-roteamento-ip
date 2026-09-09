FROM quay.io/frrouting/frr:9.1.0

RUN apk add --no-cache \
      python3 py3-pip iperf3 tcpdump traceroute iproute2 bind-tools \
 && pip3 install --break-system-packages pyroute2

COPY larpd.py /usr/local/bin/larpd
RUN chmod +x /usr/local/bin/larpd
