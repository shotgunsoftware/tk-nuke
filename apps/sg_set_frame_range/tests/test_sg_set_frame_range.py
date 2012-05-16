"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------
"""
from test_sg_nuke import *

class TestSgSetFrameRange(NukeEngineTestBase):
    def setUp(self):
        super(TestSgSetFrameRange, self).setUp()
        self.app_name = "sg_set_frame_range"
        self.app = self.engine.apps.get(self.app_name)

    def test_is_app(self):
        self.assertIsInstance(self.app, tank.system.application.Application)


