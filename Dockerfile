FROM ubuntu:22.04

# Set non-interactive frontend to avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    coreutils \
    sshpass \
    nmap \
    hydra \
    medusa \
    ssh \
    sudo \
    curl

RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash

# Enable colored terminal output
RUN echo 'export PS1="\[\e[01;32m\]\u@\h\[\e[00m\]:\[\e[01;34m\]\w\[\e[00m\]\$ "' >> /root/.bashrc && \
    echo 'alias ls="ls --color=auto"' >> /root/.bashrc && \
    echo 'alias grep="grep --color=auto"' >> /root/.bashrc && \
    echo 'export TERM=xterm-256color' >> /root/.bashrc

WORKDIR /lab

COPY . /lab/

CMD ["/bin/bash"]