# Crawl findings

**Status: NOT YET INSPECTED.**

This project was generated in a sandbox with no outbound access to piyushai.com or piyushwairale.com, so the
real structure of those sites (robots.txt rules, sitemap, static vs JavaScript-rendered content) could not be checked.
The crawler handles every case (robots.txt, sitemap, embedded-JSON / public-API / optional Playwright fallbacks);
tests exercise each path against simulated sites only.

Run this once on your machine to replace this file with real findings:

    cd backend
    python -m scripts.inspect_sites
