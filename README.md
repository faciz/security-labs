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

### Choose Your Environment

These labs require a Linux/Unix environment with bash and standard Unix tools. Pick **one** of the three options below — most users should start with Option 1.

| Option | Best for | Local install required? |
| --- | --- | --- |
| **1. GitHub Codespaces** _(recommended)_ | Getting started fastest, no local setup | No — runs in the browser |
| **2. Docker** | Running locally in an isolated container | Docker only |
| **3. Local machine** | Running directly on Linux, macOS, or WSL | Yes — bash + dependencies |

### Option 1: GitHub Codespaces (recommended)

Run the labs directly in your browser — no local setup required. From the repository on GitHub, click **Code → Codespaces → Create codespace on main**. The included dev container configuration ([`.devcontainer/devcontainer.json`](./.devcontainer/devcontainer.json)) automatically builds the environment with all necessary tools pre-installed.

### Option 2: Docker

Run the labs in a local container using the provided Dockerfile (Ubuntu image) with all necessary tools pre-installed. Requires [Docker](https://docs.docker.com/get-started/get-docker/) installed on your machine. Choose **either** of the approaches below.

**Build and run manually.** From the repository root, build the image and start a container:

```bash
docker build -t sec-lab .

docker run -it --rm sec-lab
```

**Or use the Dev Container in VS Code.** With the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) installed, open the repository in VS Code and run **Dev Containers: Reopen in Container** from the Command Palette. This builds the same Dockerfile via [`.devcontainer/devcontainer.json`](./.devcontainer/devcontainer.json) and drops you into the environment with all tools pre-installed.

### Option 3: Local machine

Run the labs directly on Linux, macOS, or Windows Subsystem for Linux (WSL). Unlike the Codespaces and Docker options, you'll need to install the setup script dependencies yourself:

- **coreutils**:
  - Ubuntu/Debian: `sudo apt-get install coreutils`
  - CentOS/RHEL: `sudo yum install coreutils`
  - macOS: `brew install coreutils`

### Additional Requirements

The following apply regardless of which environment option you chose above.

- **Azure Subscription**: These labs will create resources in your Azure subscription. Make sure you have an active Azure subscription with appropriate permissions to create and manage resources.

- **Azure CLI Authentication**: You'll need to authenticate with Azure using the following commands:

  ```bash
  az login
  ```

  If not prompted to select a subscription, you may need to set the desired subscription using:

  ```bash
    az account set --subscription <subscription-id>
  ```

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

# Lab 02: VaultBank AI Assistant

## Scenario

VaultBank just launched **VaultBot**, an AI customer-support assistant that can check balances, read customer records, and move money. You have a low-privilege Guest account. The bank believes a few well-worded instructions are enough to keep VaultBot in line. Prove them wrong: leak the assistant's hidden instructions, expose another customer's private data, steal the vault master code, and move money out of an account that isn't yours — using nothing but conversation.

This lab is a hands-on tour of the [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/): prompt injection (direct and indirect), system prompt leakage, sensitive information disclosure, insecure output handling, and excessive agency.

## Setup Lab

You should first go through the `Lab 02` section in the presentation. After doing so, run the `lab02_setup.sh` script.

This lab is **hybrid**: the vulnerable chatbot runs locally (in your Codespace/container), but it calls a real **Azure OpenAI** model that the setup script provisions in your subscription.

>[!IMPORTANT]
The setup script is encoded to retain the challenge of the lab. You should not see how the resources are created or where the secrets are hidden.
>
>Do not look at the resources created in the Azure portal, or the generated `.env` / `.secrets/` files, until **AFTER** you have completed the lab, as it may spoil the challenge.
>
>If you are curious, you may decode/read the setup script **AFTER** completing the lab.

```bash
cd "Lab 02 - VaultBank AI Assistant"
./lab02_setup.sh
```

>[!NOTE]
> The setup script deploys an Azure OpenAI resource and automatically selects a currently available chat model for the deployment (querying your region for a supported model). Make sure your subscription has access to Azure OpenAI and available quota in the target region. Provisioning may take a few minutes.

Once setup completes, start the chatbot and open it in your browser:

```bash
cd vaultbot
./run.sh
```

Then browse to <http://localhost:3000>.

## Completing the Lab

### Option 1: Hard Mode (Recommended)

Talk your way past VaultBot's guardrails and complete all four objectives. Hopefully the powerpoint taught you something. Good luck.

### Option 2: Guided Mode

It is recommended to try the hard mode first, but if you get stuck, you can use the guide to help you through the steps.

The full step-by-step guide is available [here](./Lab%2002%20-%20VaultBank%20AI%20Assistant/guided_mode.md).

## Part 2: Automated Red Teaming (Optional)

After attacking VaultBot by hand, see how the pros scale it. Part 2 points
Microsoft Foundry's **AI Red Teaming Agent (preview)** at VaultBot, generates and
mutates adversarial prompts automatically, and reports an Attack Success Rate
scorecard — reinforcing why the model's safety alignment held while the _app
layer_ did not.

The walkthrough is available [here](./Lab%2002%20-%20VaultBank%20AI%20Assistant/part2-red-teaming/guided_mode.md).
