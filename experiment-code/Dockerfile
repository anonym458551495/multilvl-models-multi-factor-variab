# Use an official Python runtime as a parent image
FROM ubuntu:22.04

# Set noninteractive mode for apt-get
ENV DEBIAN_FRONTEND=noninteractive

# Install common software and necessary dependencies
RUN apt-get update && \
    apt-get install -y \
    git \
    pkg-config \
    curl \
    libhdf5-dev \
    software-properties-common

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Setting up environment
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.9 python3.9-dev python3-pip python3-wheel build-essential python3.9-distutils
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# Set python3 as the default python
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 1

# Install any needed packages specified in requirements.txt
RUN python3.9 -m pip install --no-cache-dir -r requirements.txt

# Reinstall jax with another version, doesn't work inside requirements.txt because of faulty pip version conflicts
#RUN python -m pip install jax==0.4.14 # && \
#    python -m pip install jaxlib==0.4.13

RUN python3.9 -m pip install jax[cpu]==0.4.18 jaxlib==0.4.18

# Change directory to wluncert/
WORKDIR /app/wluncert

# Create a "tmp" folder in the working directory
RUN mkdir /app/wluncert/tmp
RUN mkdir /app/wluncert/results
RUN mkdir /app/wluncert/results/localflow

# Expose necessary ports for the Streamlit dashboards
EXPOSE 8083 8084

# Command to run the entrypoint script
ENTRYPOINT ["python3.9", "/app/entrypoint.py"]