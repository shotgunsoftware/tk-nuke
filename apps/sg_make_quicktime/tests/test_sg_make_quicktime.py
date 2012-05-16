"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------
"""
from test_sg_nuke import *

class TestSgMakeQuicktime(NukeEngineTestBase):
    def setUp(self):
        super(TestSgMakeQuicktime, self).setUp()
        self.app_name = "sg_make_quicktime"
        self.app = self.engine.apps.get(self.app_name)

    def test_is_app(self):
        self.assertIsInstance(self.app, tank.system.application.Application)


