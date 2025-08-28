# ---------- build stage ----------
FROM ubuntu:24.04 AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    build-essential gfortran gcc g++ make wget ca-certificates bzip2 perl \
    libblas-dev liblapack-dev libarpack2-dev \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt
RUN set -eux; \
  mkdir -p /usr/lang-4.0/bin && ln -sf /usr/bin/gcc /usr/lang-4.0/bin/cc; \
  wget -q https://www.netlib.org/linalg/spooles/spooles.2.2.tgz; \
  mkdir -p /opt/spooles; tar -xzf spooles.2.2.tgz -C /opt/spooles; \
  cd /opt/spooles; [ -f Make.inc ] && sed -i 's/^CC[[:space:]]*=.*/CC = gcc/' Make.inc || true; \
  make lib; cd MT/src; [ -f makefile ] && sed -i 's/^CC[[:space:]]*=.*/CC = gcc/' makefile || true; make
ARG CCX_VER=2.22
RUN set -eux; \
  wget -q http://www.dhondt.de/ccx_${CCX_VER}.src.tar.bz2; \
  bunzip2 ccx_${CCX_VER}.src.tar.bz2; tar -xf ccx_${CCX_VER}.src.tar; \
  CCX_SRC_DIR="CalculiX/ccx_${CCX_VER}/src"; [ -d "$CCX_SRC_DIR" ] || CCX_SRC_DIR="ccx_${CCX_VER}/src"; \
  cd "$CCX_SRC_DIR"; ln -sfn /opt/spooles ../SPOOLES.2.2; \
  mkdir -p ../ARPACK; printf 'INPUT(-larpack -llapack -lblas)\n' > ../ARPACK/libarpack_INTEL.a; \
  make -f Makefile_MT CC=gcc FFLAGS='-O3 -fopenmp' CFLAGS='-O3 -DARCH="Linux" -DARPACK -DMATRIXSTORAGE -DUSE_MT=1'; \
  install -m 0755 ccx_${CCX_VER}_MT /usr/local/bin/ccx

# ---------- runtime stage ----------
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    libgfortran5 libgomp1 libblas3 liblapack3 libarpack2 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/ccx /usr/local/bin/ccx
ENV OMP_NUM_THREADS=1
WORKDIR /data
CMD ["ccx","-v"]
