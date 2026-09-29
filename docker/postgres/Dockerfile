# PostgreSQL with pgvector, on the same alpine base the volume was created with.
#
# Card F16-09. The official pgvector image is Debian (glibc); moving an existing volume from
# musl to glibc changes the text collation under indexes that were already built, which
# corrupts them without an error. So the extension is compiled here instead.
# OPTFLAGS="" keeps the binary portable (no -march=native from the build machine) and
# with_llvm=no skips the JIT bitcode, which the alpine image has no toolchain for.
FROM postgres:17.2-alpine

ARG PGVECTOR_VERSION=0.8.6

RUN apk add --no-cache --virtual .build-deps git build-base \
    && git clone --branch "v${PGVECTOR_VERSION}" --depth 1 \
        https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && make -C /tmp/pgvector OPTFLAGS="" with_llvm=no \
    && make -C /tmp/pgvector install with_llvm=no \
    && rm -rf /tmp/pgvector \
    && apk del .build-deps
