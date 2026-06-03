FROM ubuntu:22.04

# Set non-interactive frontend to avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    coreutils \
    ssh \
    sudo \
    curl \
    nmap \
    medusa \
    hydra

RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash

# Install Node.js and GitHub Copilot CLI
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @github/copilot

# Enable colored terminal output
RUN echo 'export PS1="\[\e[01;32m\]\u@\h\[\e[00m\]:\[\e[01;34m\]\w\[\e[00m\]\$ "' >> /root/.bashrc && \
    echo 'alias ls="ls --color=auto"' >> /root/.bashrc && \
    echo 'alias grep="grep --color=auto"' >> /root/.bashrc && \
    echo 'export TERM=xterm-256color' >> /root/.bashrc

WORKDIR /lab

COPY . /lab/

CMD ["/bin/bash"]