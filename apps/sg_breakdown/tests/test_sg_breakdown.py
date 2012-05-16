"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------
"""
from test_sg_nuke import *

class TestSgBreakdown(NukeEngineTestBase):
    def setUp(self):
        super(TestSgBreakdown, self).setUp()
        self.app_name = "sg_breakdown"
        self.app = self.engine.apps.get(self.app_name)

    def test_is_app(self):
        self.assertIsInstance(self.app, tank.system.application.Application)

