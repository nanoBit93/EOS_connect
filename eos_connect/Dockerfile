# Home Assistant add-on image for EOS Connect, built from the app source in
# this repository (the build workflow syncs ``src/`` into ``./src`` inside the
# staged add-on folder before building; see ha_addon_builder.yml).
ARG BUILD_FROM
FROM $BUILD_FROM

# Timing: Start build with GitHub Actions visibility
RUN echo "::group::Build Environment Setup" && \
    echo "=== BUILD STARTED: $(date) ===" && \
    echo "Architecture: $(uname -m)" && \
    echo "Memory: $(free -h | grep Mem:)" && \
    echo "::endgroup::"

# Install runtime dependencies efficiently
RUN echo "::group::Installing System Dependencies" && \
    echo "=== INSTALLING SYSTEM PACKAGES ===" && \
    apk add --no-cache python3 py3-pip curl gcc python3-dev musl-dev && \
    echo "=== SYSTEM PACKAGES INSTALLED ===" && \
    echo "::endgroup::"

# Create virtual environment
RUN echo "::group::Creating Python Environment" && \
    echo "=== CREATING VIRTUAL ENVIRONMENT ===" && \
    python3 -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip && \
    echo "Python version: $(python --version)" && \
    echo "Pip version: $(pip --version)" && \
    echo "=== VIRTUAL ENVIRONMENT READY ===" && \
    echo "::endgroup::"

# Install the application dependencies. Kept in one layer; the list mirrors
# requirements.txt at the repository root.
RUN echo "::group::Installing Python Dependencies" && \
    . /opt/venv/bin/activate && \
    pip install --no-cache-dir \
    Flask>=2.2.5 requests>=2.26.0 pandas>=2.2.3 numpy>=2.0.0 \
    waitress>=3.0.0 pyyaml>=6.0 pytz>=2025.1 ruamel.yaml==0.18.17 \
    paho-mqtt>=2.1.0 packaging>=23.2 \
    open-meteo-solar-forecast>=0.1.22 psutil>=7.0.0 \
    "pymodbus>=3.0.0,<3.16" "pulp>=2.7.0,<4" && \
    echo "=== ALL PACKAGES INSTALLED ===" && \
    echo "::endgroup::" && \
    apk del --purge gcc python3-dev musl-dev && \
    rm -rf /var/cache/apk/*

# PuLP's bundled x86_64 CBC is glibc-linked and cannot exec on Alpine/musl
# (execve -> ENOENT, surfaces as FileNotFoundError; EOS_connect #260 #264 #265 #273).
# The official COIN-OR build is a fully static ELF (no interpreter, no NEEDED)
# and is baseline x86-64 -- its only AVX code sits inside glibc's cpuid-dispatched
# IFUNC variants -- so it runs on musl and on kvm64/older CPUs alike.
# aarch64 needs nothing: pulp's bundled arm64 CBC is already static.
RUN if [ "$(uname -m)" = "x86_64" ]; then \
      echo "::group::Installing static CBC solver" && \
      curl -fsSL -o /tmp/cbc.tgz \
        "https://github.com/coin-or/Cbc/releases/download/releases%2F2.10.13/Cbc-releases.2.10.13-x86_64-ubuntu22-gcc1140-static.tar.gz" && \
      echo "86d52bb5634203826f213a09cba83394623a1c44eecc75caed2a553a9ac642fa  /tmp/cbc.tgz" | sha256sum -c - && \
      tar -xzf /tmp/cbc.tgz -C /usr/local ./bin/cbc && \
      rm /tmp/cbc.tgz && \
      /usr/local/bin/cbc -quit && \
      echo "::endgroup::" ; \
    fi

# Copy the application source and finalize
COPY ./src /app/src
WORKDIR /app/src
RUN echo "::group::Finalizing Application" && \
    echo "=== APPLICATION COPIED ===" && \
    echo "Virtual environment size: $(du -sh /opt/venv)" && \
    echo "=== BUILD COMPLETED: $(date) ===" && \
    echo "::endgroup::"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8081/ || exit 1

EXPOSE 8081
CMD ["/opt/venv/bin/python", "/app/src/eos_connect.py"]