import os

from hypothesis import settings

settings.register_profile("default", max_examples=30, deadline=None)
settings.register_profile("deep", max_examples=1000, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
