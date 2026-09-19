"""The only package permitted to invoke an LLM.

The LLM touches only the edges: turning a user's sentence into a structured
tool call (``ai/intent_classifier.py``), and narrating already-computed
numbers into prose (via ``ai/llm_client.py``). It never computes a rupee
figure itself, and every number it displays is verified against real engine
output first (``ai/numeric_guard.py``). See repo-root ``CLAUDE.md``
principle 2.
"""
