# Build Stage
FROM python:3.11-slim-bookworm AS build
# FROM python:3.9-slim AS build

WORKDIR /opt/CTFd

# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        git \
        protobuf-compiler \
        python3-grpc-tools \
        python3-protobuf \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /opt/venv

# Set the virtual environment path
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH=/opt/CTFd

# Copy the application code into the container
COPY . .

<<<<<<< HEAD
# Install Python dependencies
=======
RUN pip install grpcio-tools==1.59.3 protobuf==4.25.1

# Install dependencies and grpc tools
>>>>>>> 48936674 (Adding otp routes)
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir grpcio-tools protobuf \
    && for d in CTFd/plugins/*; do \
        if [ -f "$d/requirements.txt" ]; then \
            pip install --no-cache-dir -r "$d/requirements.txt"; \
        fi; \
    done;

<<<<<<< HEAD
# # Generate gRPC code from .proto files
# RUN python -m grpc_tools.protoc -I./CTFd/protos --python_out=./CTFd --grpc_python_out=./CTFd ./CTFd/protos/authentication.proto
=======
# Generate gRPC proto files
RUN python -m grpc_tools.protoc \
    -I /usr/include \
    -I CTFd/utils/auth \
    --python_out=CTFd/utils/auth \
    --grpc_python_out=CTFd/utils/auth \
    CTFd/utils/auth/lynx_auth.proto \
    && touch CTFd/utils/auth/__init__.py \
    && chmod 644 CTFd/utils/auth/lynx_auth_pb2*.py
>>>>>>> 48936674 (Adding otp routes)

# Install grpcio and grpcio-tools for Python with specific versions
# RUN pip install grpcio==1.28.0 grpcio-tools==1.28.0

# Install grpcio-tools
RUN pip install grpcio grpcio-tools
# RUN pip install grpcio-tools

# Generate gRPC code from .proto files
RUN python -m grpc_tools.protoc -I./CTFd/protos --python_out=./CTFd --grpc_python_out=./CTFd ./CTFd/protos/authentication.proto

# Release Stage
FROM python:3.11-slim-bookworm AS release

WORKDIR /opt/CTFd

# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libffi8 \
        libssl3 \
        protobuf-compiler \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

<<<<<<< HEAD
# Copy application code and set permissions
COPY --chown=1001:1001 . .

# Create a non-root user and set up necessary directories
RUN useradd --no-log-init --shell /bin/bash -u 1001 CTFd \
=======
# Copy application files first
COPY --chown=1001:1001 . /opt/CTFd

# Copy virtual environment
COPY --chown=1001:1001 --from=build /opt/venv /opt/venv

# Create auth directory and copy proto files
RUN mkdir -p /opt/CTFd/CTFd/utils/auth
COPY --chown=1001:1001 --from=build /opt/CTFd/CTFd/utils/auth/lynx_auth_pb2*.py /opt/CTFd/CTFd/utils/auth/

RUN useradd \
    --no-log-init \
    --shell /bin/bash \
    -u 1001 \
    ctfd \
>>>>>>> 48936674 (Adding otp routes)
    && mkdir -p /var/log/CTFd /var/uploads \
    && chown -R 1001:1001 /var/log/CTFd /var/uploads /opt/CTFd \
    && chmod +x /opt/CTFd/docker-entrypoint.sh

<<<<<<< HEAD
# Copy the virtual environment from the build stage
COPY --chown=1001:1001 --from=build /opt/venv /opt/venv

# Set the PATH to include the virtual environment
=======
>>>>>>> 48936674 (Adding otp routes)
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/opt/CTFd:${PYTHONPATH}"

# Switch to non-root user
USER 1001

# Expose port 8000 for the application
EXPOSE 8000
<<<<<<< HEAD

# Set the entrypoint for the container
ENTRYPOINT ["/opt/CTFd/docker-entrypoint.sh"]
=======
ENTRYPOINT ["/opt/CTFd/docker-entrypoint.sh"]
>>>>>>> 48936674 (Adding otp routes)
