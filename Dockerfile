FROM python:3.10-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    git \
    libgl1 \
    libglib2.0-0 \
    unzip \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dcm2niix
RUN wget https://github.com/rordenlab/dcm2niix/releases/latest/download/dcm2niix_lnx.zip \
    && unzip dcm2niix_lnx.zip && mv dcm2niix /usr/local/bin/ && rm dcm2niix_lnx.zip

# Upgrade pip and install core scientific stack
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        typer \
        rich \
        pandas \
        openpyxl \
        pydicom \
        pybids \
        pyyaml \
        nilearn \
        scikit-learn \
        scipy \
        nibabel \
        matplotlib \
        seaborn

# Create workspace structure
RUN mkdir -p /raw /sourcedata /derivatives /work /configs /scripts

# Set default command
ENTRYPOINT ["python", "-m", "neuro_mod.cli"]
