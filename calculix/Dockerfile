# ---------- build stage ----------
FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90 AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN sed -ri \
      's#https?://(archive|security)\.ubuntu\.com/ubuntu/?#https://snapshot.ubuntu.com/ubuntu/20260714T000000Z/#g' \
      /etc/apt/sources.list.d/ubuntu.sources \
 && printf '%s\n' 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99snapshot \
 && grep -q 'snapshot.ubuntu.com/ubuntu/20260714T000000Z' /etc/apt/sources.list.d/ubuntu.sources \
 && apt-get update && apt-get install -y --no-install-recommends \
    build-essential gfortran gcc g++ make wget ca-certificates bzip2 perl \
    libblas-dev liblapack-dev libarpack2-dev \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt
RUN set -eux; \
  mkdir -p /usr/lang-4.0/bin && ln -sf /usr/bin/gcc /usr/lang-4.0/bin/cc; \
  wget -q https://www.netlib.org/linalg/spooles/spooles.2.2.tgz -O spooles.2.2.tgz; \
  printf '%s  %s\n' 'a84559a0e987a1e423055ef4fdf3035d55b65bbe4bf915efaa1a35bef7f8c5dd' spooles.2.2.tgz | sha256sum -c -; \
  mkdir -p /opt/spooles; tar -xzf spooles.2.2.tgz -C /opt/spooles; \
  cd /opt/spooles; [ -f Make.inc ] && sed -i 's/^CC[[:space:]]*=.*/CC = gcc/' Make.inc || true; \
  make lib; cd MT/src; [ -f makefile ] && sed -i 's/^CC[[:space:]]*=.*/CC = gcc/' makefile || true; make
RUN set -eux; \
  wget -q https://www.dhondt.de/ccx_2.23.src.tar.bz2 -O ccx_2.23.src.tar.bz2; \
  printf '%s  %s\n' '9c88385c10fb04f5dc6c4e98027a51bebdd8aee3920e05190d6c1dd08357d6e7' ccx_2.23.src.tar.bz2 | sha256sum -c -; \
  bunzip2 ccx_2.23.src.tar.bz2; tar -xf ccx_2.23.src.tar; \
  CCX_SRC_DIR="CalculiX/ccx_2.23/src"; [ -d "$CCX_SRC_DIR" ] || CCX_SRC_DIR="ccx_2.23/src"; \
  cd "$CCX_SRC_DIR"; ln -sfn /opt/spooles ../SPOOLES.2.2; \
  mkdir -p ../ARPACK; printf 'INPUT(-larpack -llapack -lblas)\n' > ../ARPACK/libarpack_INTEL.a; \
  make -f Makefile_MT CC=gcc FFLAGS='-O3 -fopenmp -cpp -D__GFORTRAN__' CFLAGS='-O3 -DARCH="Linux" -DARPACK -DMATRIXSTORAGE -DUSE_MT=1'; \
  install -m 0755 ccx_2.23_MT /usr/local/bin/ccx

# ---------- runtime stage ----------
FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90
ENV DEBIAN_FRONTEND=noninteractive
RUN sed -ri \
      's#https?://(archive|security)\.ubuntu\.com/ubuntu/?#https://snapshot.ubuntu.com/ubuntu/20260714T000000Z/#g' \
      /etc/apt/sources.list.d/ubuntu.sources \
 && printf '%s\n' 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99snapshot \
 && grep -q 'snapshot.ubuntu.com/ubuntu/20260714T000000Z' /etc/apt/sources.list.d/ubuntu.sources \
 && apt-get update && apt-get install -y --no-install-recommends \
    libgfortran5 libgomp1 libblas3 liblapack3 libarpack2 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/ccx /usr/local/bin/ccx
ENV OMP_NUM_THREADS=1
WORKDIR /data
CMD ["ccx","-v"]
