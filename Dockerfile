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

# Copy project files
COPY *.py .
COPY pyproject.toml .
COPY README.md .

# Install Python dependencies from pyproject.toml
RUN pip install .

# Setup caches
RUN python setup_caches.py

# Run generate_plots.py
CMD ["python", "generate_plots.py"]