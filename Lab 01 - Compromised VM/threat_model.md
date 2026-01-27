# Lab 01: Compromised VM - Threat Model

## System Overview

This lab demonstrates a common cloud infrastructure vulnerability where a publicly accessible VM with weak credentials can be exploited to gain access to internal resources.

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Internet                                │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                │ SSH (Port 2222)
                                │ (Weak Password Auth)
                                │
     ╔══════════════════════════│══════════════════════════════╗
     ║ TRUST BOUNDARY           │                              ║
     ║                          ▼                              ║
     ║               ┌──────────────────────┐                  ║
     ║               │      Public VM       │                  ║
     ║               │                      │                  ║
     ║               │  - Public IP         │                  ║
     ║               │  - Password Auth     │                  ║
     ║               │  - SSH Key Storage   │                  ║
     ║               └──────────┬───────────┘                  ║
     ║                          │                              ║
     ║                          │ SSH (Private Network)        ║
     ║                          │ (SSH Key Auth)               ║
     ║                          │ 10.0.0.0/24                  ║
     ║                          ▼                              ║
     ║               ┌──────────────────────────────┐          ║
     ║               │         Private VM           │          ║
     ║               │                              │          ║
     ║               │  - No Public IP              │          ║
     ║               │  - SSH Key Only              │          ║
     ║               │  - Secret Data               │          ║
     ║               │  - Misconfigured Sudo Privs  │          ║
     ║               └──────────────────────────────┘          ║
     ╚═════════════════════════════════════════════════════════╝
```

## Components

### 1. Attacker (External)
- **Description**: Malicious actor from the internet
- **Capabilities**: Port scanning, password attacks, SSH access
- **Goal**: Gain unauthorized access to sensitive data

### 2. Public VM
- **Description**: Internet-facing virtual machine
- **Network**: Public IP + VNet (10.0.0.0/24)
- **Authentication**: Password-based SSH
- **Security Controls** (weak):
  - Non-standard SSH port (2222) - security through obscurity, easily defeated by port scanning
- **Vulnerabilities**:
  - Weak password susceptible to dictionary attacks
  - Stores private SSH keys for lateral movement
- **Trust Boundary**: Entry point from internet to internal network

### 3. Private VM
- **Description**: Internal virtual machine with sensitive data
- **Network**: Private IP only (10.0.0.99)
- **Authentication**: SSH key-based only
- **Vulnerabilities**:
  - Trusts SSH key from compromised public VM
  - Sudo privileges granted for vim (privilege escalation vector)
  - Root-owned files accessible via sudo
- **Assets**: Secret file (root-owned, 600 permissions)

### 4. Virtual Network (VNet)
- **Description**: Azure virtual network isolating VMs
- **Subnet**: 10.0.0.0/24
- **NSG Rules**:
  - Allow SSH (2222) - VULNERABLE
- **Isolation**: Private VM has no direct internet access

## Threat Analysis (STRIDE)

### Spoofing
- **Threat**: Attacker impersonates legitimate user
- **Attack Vector**: Password spraying attack against public VM
- **Impact**: HIGH - Full access to public VM
- **Mitigation**: 
  - Use SSH keys instead of passwords
  - Implement MFA
  - Use strong, unique passwords
  - Account lockout policies

### Tampering
- **Threat**: Modification of data or configuration
- **Attack Vector**: After gaining access, attacker modifies files or system config
- **Impact**: MEDIUM - Data integrity compromised
- **Mitigation**:
  - File integrity monitoring
  - Immutable infrastructure
  - Audit logging

### Repudiation
- **Threat**: Attacker actions cannot be traced
- **Attack Vector**: Lack of logging/monitoring on VMs
- **Impact**: LOW - Difficult to investigate incidents
- **Mitigation**:
  - Enable Azure Monitor
  - Configure syslog/audit logs
  - Centralized logging

### Information Disclosure
- **Threat**: Unauthorized access to sensitive data
- **Attack Vector**: 
  1. Gain access to public VM via weak password
  2. Find stored SSH key
  3. Use key to access private VM
  4. Exploit sudo vim to read root-owned files
- **Impact**: CRITICAL - Secret file exposed
- **Mitigation**:
  - Don't store SSH keys on VMs
  - Use Azure Key Vault or HSM
  - Implement least privilege
  - Restrict sudo commands
  - Use bastion hosts for access

### Denial of Service
- **Threat**: Service availability compromised
- **Attack Vector**: Attacker exhausts resources or crashes services
- **Impact**: MEDIUM - VMs become unavailable
- **Mitigation**:
  - Rate limiting
  - Resource quotas
  - DDoS protection
  - Redundancy

### Elevation of Privilege
- **Threat**: User gains unauthorized elevated permissions
- **Attack Vector**: 
  - Sudo vim privilege allows reading/writing any file
  - Can escape vim to get root shell
- **Impact**: CRITICAL - Full root access to private VM
- **Mitigation**:
  - Minimize sudo privileges
  - Use specific sudo commands only
  - Disable shell escape in vim for sudo
  - Regular privilege audits

## Attack Path

```
1. Reconnaissance
   ├─ nmap scan discovers port 2222 open
   └─ Identifies Azure hosting (suggests azureuser)

2. Initial Access
   ├─ Password spray attack with common passwords
   └─ Successful login

3. Discovery
   ├─ Enumerate SSH keys in ~/.ssh/
   └─ Find key_to_the_boss_vm

4. Lateral Movement
   ├─ Use discovered SSH key
   └─ Access private VM

5. Privilege Escalation
   ├─ Check sudo privileges
   ├─ Find: azureuser ALL=(ALL) NOPASSWD: /usr/bin/vim
   └─ Use sudo vim to read root-owned files

6. Exfiltration
   └─ Read secret file
```

## Risk Assessment

| Vulnerability | Likelihood | Impact | Risk Level | Priority |
|--------------|------------|---------|------------|----------|
| Weak password on public VM | High | High | **CRITICAL** | P0 |
| SSH key storage on public VM | High | High | **CRITICAL** | P0 |
| Unrestricted sudo vim access | Medium | Critical | **HIGH** | P1 |
| Public SSH exposure | High | Medium | **HIGH** | P1 |

## Security Recommendations

### Immediate Actions (Critical)
1. **Replace password authentication with SSH keys** on all VMs
2. **Never store private SSH keys on VMs** - use Azure Bastion, jump boxes, or hardware-backed keys
3. **Remove or severely restrict sudo privileges**
   - Instead of `ALL=(ALL)`, specify exact commands
   - Remove vim from sudo-allowed commands
4. **Rotate all SSH keys and passwords**

### Short-term (High Priority)
1. **Implement Azure Bastion** for secure VM access without public IPs
2. **Enable MFA** for all administrative access
3. **Configure NSG rules** to restrict SSH access to specific IP ranges
4. **Enable Azure Security Center** for threat detection
5. **Implement Just-In-Time (JIT) access** for VMs

### Long-term (Medium Priority)
1. **Use Azure Key Vault** for secret management
2. **Implement network segmentation** with multiple subnets
3. **Enable Azure Monitor and log analytics**
4. **Regular security audits** and penetration testing
5. **Implement Azure Firewall** for centralized network security
6. **Use Azure AD for identity management**
7. **Enable disk encryption** for all VMs

### Best Practices
- **Principle of Least Privilege**: Grant minimum necessary permissions
- **Defense in Depth**: Multiple layers of security controls
- **Zero Trust**: Never trust, always verify
- **Monitoring and Alerting**: Detect and respond to threats quickly
- **Regular Updates**: Keep systems patched and updated

## Lessons Learned

1. **Public exposure is dangerous** - Even non-standard ports can be discovered
2. **Weak passwords are easily cracked** - Use strong, unique passwords or keys
3. **SSH keys are credentials** - Treat them as securely as passwords
4. **Sudo is powerful** - Unrestricted sudo can lead to full compromise
5. **Network segmentation helps** - But doesn't prevent lateral movement if credentials are compromised
6. **Security through obscurity fails** - Non-standard ports don't provide real security
