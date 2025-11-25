import re
from typing import List, Tuple

BANNED = {"how to hack", "crack", "ddos", "payload", "exploit", "rat", "keylogger", "bypass paywall"}

# Whitelist split by categories for clarity/maintenance
CYBER_TOPICS_CATEGORIES = {
    "awareness": {
        "phishing","phishing awareness","social media safety","digital footprint",
        "cyber hygiene","online privacy","identity theft","personal data protection",
        "safe browsing","fake websites","deepfake","ai scams","smishing","vishing",
        "privacy","breach","scam","malware","virus","ransomware",
        "update","patch","backup","encryption","social engineering",
        "email security","password manager","hacking prevention"
    },
    "auth_access": {
        "password","passphrase","2fa","two-factor","multi-factor","mfa","otp","authenticator",
        "biometric authentication","passwordless login","single sign-on",
        "identity and access management","privileged access management","iam","pam",
        "account","login","sign-in"
    },
    "network_internet": {
        "wifi","router","network","vpn","dns security","ip spoofing","man-in-the-middle attack",
        "ssl","tls","https","secure connection"
    },
    "endpoint_os": {
        "patch management","device hardening","operating system security",
        "mobile security","byod security","endpoint protection","anti-malware","antivirus","zero trust"
    },
    "org_process": {
        "security policy","risk management","incident management plan",
        "business continuity","disaster recovery","incident response"
    },
    "cloud_api": {
        "cloud security","data residency","shared responsibility model","api security",
        "xdr","extended detection and response","edr","endpoint detection and response",
        "mxdr","managed xdr","soar","security orchestration automation and response"
    },
    "threats": {
        "botnet","spyware","keylogger","trojan","adware","ddos","denial of service",
        "zero-day exploit","insider threat","threat detection","threat actor",
        "cyber attack","cyber threat"
    },
    "frameworks": {
        "iso 27001","gdpr","pdpa","information security","cybersecurity","infosec"
    },
    "education": {
        "cyber ethics","digital citizenship","safe online behavior",
        "security training","cyberbullying prevention","security awareness"
    },
    "common_typos": {
        # Phishing variations
        "phising", "pishing", "fishing", "phish",
        # Password variations
        "pasword", "passwrd", "pass word", "pasphrase",
        # Malware/Ransomware variations
        "malwear", "malwar", "ransomwear", "randsomware", "addware", "spy ware",
        # Cybersecurity variations
        "cyber security", "cibersecurity", "ciber", "cybersec", "infosecurity",
        # General variations
        "wi-fi", "wi fi", "fire wall", "anti virus", "anti-virus",
        "authentification", "authenication", "priviledge", "hygene" 
    }
}
# Flattened set used by the filter logic
CYBER_TOPICS = set().union(*CYBER_TOPICS_CATEGORIES.values())

def guardrails_or_offtopic(user_text: str, history: List[Tuple[str, str]]) -> str | None:
    q = user_text.lower()
    if any(re.search(rf"\b{re.escape(k)}\b", q) for k in BANNED):
        return ("I can't help with offensive or illegal hacking. "
                "Let's focus on defensive skills like phishing detection, strong passwords, and 2FA.")
    if len(history) > 0:
        return None
    if not any(k in q for k in CYBER_TOPICS):
        return (
            "This is a **Cybersecurity Education Bot**. Kindly ask questions related to cybersecurity.\n\n"
            "**You can ask about:**\n"
            "• Spotting phishing emails/messages\n"
            "• Creating strong passwords & using password managers\n"
            "• Two-factor authentication (2FA)\n"
            "• Privacy settings for phone/social media\n"
            "• Securing your home Wi-Fi/router\n"
            "• Recognising scams, malware & safe downloading\n"
            "• Updates, backups, and account recovery"
        )
    return None
