"""Discovery imports this first, so the other suites can use services without naming a user.

Real requests and jobs must always say who they act for; test_tenancy clears this to prove it.
"""

from app.core import tenancy

tenancy._test_user = tenancy.OWNER
