"""
Smoke tests: do the core modules even import without crashing?
No LLM calls, no assertions on behavior - purely "does this blow up."
Fast, free, first line of defense before anything deeper runs.
"""


def test_agent_imports():
    import kokki.agent


def test_tools_imports():
    import kokki.tools


def test_config_imports():
    import kokki.config


def test_prompts_imports():
    import kokki.prompts


def test_memory_imports():
    import kokki.memory


def test_observability_imports():
    import kokki.observability
