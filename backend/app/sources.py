"""Source reliability tiers.

A fixed, readable list instead of asking the LLM. The ranking is the same on
every run and anyone can check why a source got its rating. QC Layer 1 then
adds its own judgement of each source on top.
"""

from __future__ import annotations

from urllib.parse import urlparse

TIERS: dict[str, dict] = {
    "high": {
        "rank": 0,
        "label": "Standard or official documentation",
        "domains": [
            "rfc-editor.org", "ietf.org", "w3.org", "whatwg.org", "ecma-international.org",
            "developer.mozilla.org", "docs.python.org", "python.org", "learn.microsoft.com",
            "docs.oracle.com", "postgresql.org", "dev.mysql.com", "sqlite.org", "git-scm.com",
            "nodejs.org", "react.dev", "kubernetes.io", "docs.docker.com", "cloud.google.com",
            "docs.aws.amazon.com", "developer.apple.com", "developer.android.com", "owasp.org",
            "nist.gov", "iso.org", "ieee.org", "acm.org", "unicode.org", "iana.org",
            "docs.github.com", "go.dev", "rust-lang.org", "typescriptlang.org", "nature.com",
            "nih.gov", "who.int",
        ],
        "suffixes": [".gov", ".edu", ".ac.uk", ".ac.in"],
    },
    "good": {
        "rank": 1,
        "label": "Established reference or educational publisher",
        "domains": [
            "wikipedia.org", "britannica.com", "khanacademy.org", "freecodecamp.org", "web.dev",
            "cloudflare.com", "digitalocean.com", "ibm.com", "redhat.com", "oreilly.com",
            "realpython.com", "postman.com", "coursera.org", "atlassian.com", "jetbrains.com",
            "martinfowler.com", "openstax.org", "datacamp.com", "learn.microsoft.com",
            "developers.google.com", "httpwg.org", "akamai.com", "fastly.com",
        ],
        "suffixes": [],
    },
    "fair": {
        "rank": 2,
        "label": "Tutorial site or community Q&A",
        "domains": [
            "geeksforgeeks.org", "w3schools.com", "tutorialspoint.com", "stackoverflow.com",
            "programiz.com", "javatpoint.com", "baeldung.com", "restfulapi.net", "educative.io",
            "simplilearn.com", "guru99.com", "scaler.com", "codecademy.com", "sitepoint.com",
            "css-tricks.com", "smashingmagazine.com", "stackexchange.com",
        ],
        "suffixes": [],
    },
    "low": {
        "rank": 4,
        "label": "Personal blog or user-generated platform",
        "domains": [
            "medium.com", "dev.to", "hashnode.dev", "hashnode.com", "quora.com", "reddit.com",
            "blogspot.com", "wordpress.com", "substack.com", "linkedin.com", "facebook.com",
            "x.com", "twitter.com", "scribd.com", "slideshare.net", "pinterest.com",
        ],
        "suffixes": [],
    },
}

UNKNOWN = {"tier": "unknown", "rank": 3, "label": "Unrated publisher. Check before relying on it"}


def domain_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def rate(url: str) -> dict:
    host = domain_of(url)
    for tier, spec in TIERS.items():
        if any(_matches(host, d) for d in spec["domains"]) or any(host.endswith(s) for s in spec["suffixes"]):
            return {"tier": tier, "rank": spec["rank"], "label": spec["label"]}
    return dict(UNKNOWN)
