"""The Knowledge Engine (v2.0 Step 4) — see docs/16_Knowledge_Engine.md.

The platform improves by accumulating evidence from every completed search; knowledge
grows, application code does not. This package only stores and summarizes observed
facts (`platform_performance_observations`, already-stored apartments/search history) —
no AI, no predictions, no automatic decision-making. Every public method returns a
plain count, average, or ratio computed from data that was already permanently
recorded elsewhere; nothing here infers or guesses anything about the future.
"""
