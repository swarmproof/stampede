"""Adversarial cohorts. The ``economic`` cohort embeds costbomb-core.

This is the embedded path of the "two launches, one codebase" plan (costbomb
ARCHITECTURE §6): costbomb ships first *inside* stampede as the
``adversarial:economic`` cohort, then extracts as a standalone CLI. Here costbomb-core
is an optional dependency (``pip install stampede[economic]``) — its attack library
becomes the cohort's playbook and its shared ``RunReport`` contract produces the
report's economic-findings section.
"""
