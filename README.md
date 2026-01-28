> [!WARNING]
> **ETHICAL USE ONLY**  
> This lab is for educational purposes in a controlled environment. These techniques should NEVER be used against systems you don't own or don't have explicit permission to test. Unauthorized access to computer systems is illegal and unethical.
>
> **USE PERSONAL ACCOUNTS ONLY**  
> All lab resources must be deployed exclusively on personal Azure subscriptions and test accounts. Never use company or production resources to avoid:
> - Violating organizational security policies and acceptable use agreements
> - Creating potential attack vectors or unauthorized access points
> - Exposing corporate infrastructure to vulnerabilities
> - Risk of compromising business-critical systems or data
>
> Ensure complete isolation from any production or corporate environments.

# Overview

"Be The Hacker" is a series of hands-on labs designed to provide you with insight into how an attacker could exploit improperly secured environments.

Through a series of scenarios, this lab series aims to teach the common mistakes made during cloud resource setup and software configuration, and demonstrate how they can be exploited by a bad actor.

By simulating real-world attacks on vulnerable systems, you'll gain practical experience in securing your own infrastructure and applications, and understand the importance of strong security practices.

# Prerequisites

## Presentation

Before starting these labs, please go through the accompanying PowerPoint [presentation](https://microsoft-my.sharepoint.com/:p:/p/zackaryafaci/ER5zu7QBPrVHvP54ScLMhGoB-tS4THMKDzGJn1-FT_g0uA?e=0ujWl0). It provides essential context and information that will be helpful as you work through the labs.

Refer back to the presentation as needed while completing the labs.

## Setup

Before starting these labs, please ensure you have the following:

- **Linux/Unix Environment**: These labs are designed to run on Linux, macOS, or Windows Subsystem for Linux (WSL). The setup scripts and labs use bash and Unix tools.

  - **(Alternative) Docker Environment**: Alternatively, a Dockerfile (Ubuntu image) is provided if you prefer to run the labs in a containerized environment. Ensure you have Docker installed on your machine. You can build the provided Dockerfile to create a containerized environment with all necessary tools pre-installed.
  - You can build the Docker image and run a container using the following commands:

     ```bash
      docker build -t sec-lab .

      docker run -it --rm sec-lab
    ```

- **Azure Subscription**: These labs will create resources in your Azure subscription. Make sure you have an active Azure subscription with appropriate permissions to create and manage resources.

- **Azure CLI Authentication**: You'll need to authenticate with Azure using the following commands:

  ```bash
  az login
  ```

  If not prompted to select a subscription, you may need to set the desired subscription using:

  ```bash
    az account set --subscription <subscription-id>
  ```

- **Script Dependencies**: Install the required tools for lab setup scripts:
  - **coreutils**:
    - Ubuntu/Debian: `sudo apt-get install coreutils`
    - CentOS/RHEL: `sudo yum install coreutils`
    - macOS: `brew install coreutils`

# Lab 01: Compromised VM

## Scenario

You are Mr.Ton, first name Plank, and you aspire to create a popular fast food restaurant. You found the public ip for a machine in your  rival's restaurant. Try to gain access to their company secret!

## Setup Lab

You should first go through the `Lab 01` section in the presentation. After doing so, run the `lab01_setup.sh` script.

>[!IMPORTANT]
The setup script is encoded to retain the challenge of the lab. You should not see how the resources are created.
>
>Do not look at the resources created in the Azure portal until **AFTER** you have completed the lab, as it may spoil the challenge.
>
>If you are curious, you may decode/read the setup script **AFTER** completing the lab.
>
>**Do not read `threat_model.md` until after completing the lab** - it contains detailed explanations of all vulnerabilities and the complete attack path, which will spoil the challenge.

```bash
cd Lab_01_Compromised_VM
./lab01_setup.sh
```

## Completing the Lab

### Option 1: Hard Mode (Recommended)

Go find the secret. Hopefully the powerpoint taught you something. Good luck.

### Option 2: Guided Mode

It is recommended to try the hard mode first, but if you get stuck, you can use the guide to help you through the steps.

The full step-by-step guide is available [here](./Lab%2001%20-%20Compromised%20VM/guided_mode.md).
