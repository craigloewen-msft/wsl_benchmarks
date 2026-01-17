FROM python:3.12

# Set environment variables for NVM
ENV NVM_DIR=/root/.nvm

# Install NVM and Node.js
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash && \
bash -c "source $NVM_DIR/nvm.sh && \
nvm install 24 && \
nvm alias default 24 && \
nvm use default"

# Add Node.js and npm to PATH
# Note: NVM installs with full version like v24.0.0, so we need to find it
RUN bash -c "source $NVM_DIR/nvm.sh && nvm use default && ln -sf \$(which node) /usr/local/bin/node && ln -sf \$(which npm) /usr/local/bin/npm"

# Verify installation
RUN node -v && npm -v

WORKDIR /app

# Copy cache configuration and setup files FIRST (these rarely change)
# This allows Docker to cache the expensive cache setup step
COPY cache_config.py .
COPY cache_utils.py .
COPY setup_caches.py .

# Setup caches (this layer gets cached as long as cache_config.py doesn't change)
RUN python setup_caches.py

# Copy remaining project files (these may change more frequently)
COPY pyproject.toml .

# Install Python dependencies from pyproject.toml
RUN pip install .

COPY file_io_benchmark.py .
COPY generate_plots.py .
COPY README.md .

# Run generate_plots.py
CMD ["python", "generate_plots.py"]