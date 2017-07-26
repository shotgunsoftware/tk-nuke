# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from __future__ import with_statement
import os
import sys

from tank_test.tank_test_base import TankTestBase, setUpModule, temp_env_var

import sgtk
import mock
import tempfile


repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
print "tk-nuke repository root found at %s." % repo_root

# setUpModule()


class TestEnvironmentPaths(TankTestBase):
    """
    Tests preservation of NUKEPATH at startup
    """

    def setUp(self):
        """
        Prepares the environment for unit tests.
        """
        super(TestEnvironmentPaths, self).setUp()

        # Add an environment variable that will allow the Toolkit environment to pick up the
        # engine's code.
        patch = mock.patch.dict("os.environ", {"TK_NUKE_REPO_ROOT": repo_root})
        self.addCleanup(patch.stop)
        patch.start()

        # Setup the fixture. This will take the configuration at fixtures/config inside this
        # repo.
        self.setup_fixtures()

        # clear any pre existing nuke startup environment variables
        os.environ.pop('NUKE_PATH',None)
        os.environ.pop('HIERO_PLUGIN_PATH',None)

    def test_nuke_path_append(self):
        """
        Tests the generation of NUKE_PATH environment variable , to make
        sure that the toolkit startup paths for Nuke are correctly appended to any pre-existing paths.
        Checks against pre-existing and non-existent scenarios.
        :return: None
        """
        nuke_path_1 = os.path.join(tempfile.gettempdir(), "gizmo_1")
        nuke_path_2 = os.path.join(tempfile.gettempdir(), "gizmo_1")
        plugin_path = os.path.join(repo_root, "plugins", "basic")

        # create a temp pre-existing NUKE_PATH to test preservation, when appending toolkit startup path
        nuke_path_env = {"NUKE_PATH":os.pathsep.join([nuke_path_1, nuke_path_2])}
        with temp_env_var(**nuke_path_env):

            # create launcher
            nuke_launcher = sgtk.platform.create_engine_launcher(
                self.tk,
                sgtk.context.create_empty(self.tk),
                "tk-nuke",
                ["10.0v5"]
            )

            # generate launch env
            launch_info = nuke_launcher.prepare_launch("/path/to/nuke", ["arg1", "arg2"], None)

            # ensure that the nuke path was preserved and placed first in the path
            self.assertEqual(
                launch_info.environment["NUKE_PATH"],
                os.pathsep.join([nuke_path_1, nuke_path_2, plugin_path])
            )

        # now test without stuff in the nuke path

        # generate launch env
        launch_info = nuke_launcher.prepare_launch("/path/to/nuke", ["arg1", "arg2"], None)

        # ensure that the nuke path was preserved and placed first in the path
        self.assertEqual(
            launch_info.environment["NUKE_PATH"],
            plugin_path
        )

    def test_hiero_path_append(self):
        """
        Tests the generation of HIERO_PLUGIN_PATH environment variable , to make
        sure that the toolkit startup paths for Hiero are correctly appended to any pre-existing paths.
        Checks against pre-existing and non-existent scenarios.
        :return: None
        """
        hiero_path_1 = os.path.join(tempfile.gettempdir(), "gizmo_1")
        hiero_path_2 = os.path.join(tempfile.gettempdir(), "gizmo_1")
        plugin_path = os.path.join(repo_root, "plugins", "basic")

        # create a temp pre-existing HIERO_PLUGIN_PATH to test preservation, when appending toolkit startup path
        hiero_path_env = {"HIERO_PLUGIN_PATH": os.pathsep.join([hiero_path_1, hiero_path_2])}
        with temp_env_var(**hiero_path_env):

            # create launcher
            nuke_launcher = sgtk.platform.create_engine_launcher(
                self.tk,
                sgtk.context.create_empty(self.tk),
                "tk-nuke",
                ["10.0v5"]
            )

            # generate launch env
            launch_info = nuke_launcher.prepare_launch("/path/to/nuke", ["--hiero"], None)

            # ensure that the hiero path was preserved and placed first in the path
            self.assertEqual(
                launch_info.environment["HIERO_PLUGIN_PATH"],
                os.pathsep.join([hiero_path_1, hiero_path_2, plugin_path])
            )

        # now test without stuff in the Hiero path

        # generate launch env
        launch_info = nuke_launcher.prepare_launch("/path/to/nuke", ["--hiero"], None)

        # ensure that the Hiero path was preserved and placed first in the path
        self.assertEqual(
            launch_info.environment["HIERO_PLUGIN_PATH"],
            plugin_path
        )

    def test_nuke_studio_path_append(self):
        """
        Tests the generation of HIERO_PLUGIN_PATH environment variable , to make
        sure that the toolkit startup paths for Nuke Studio are correctly appended to any pre-existing paths.
        Checks against pre-existing and non-existent scenarios.
        :return: None
        """
        hiero_path_1 = os.path.join(tempfile.gettempdir(), "gizmo_1")
        hiero_path_2 = os.path.join(tempfile.gettempdir(), "gizmo_1")
        plugin_path = os.path.join(repo_root, "plugins", "basic")

        # create a temp pre-existing HIERO_PLUGIN_PATH to test preservation, when appending toolkit startup path
        hiero_path_env = {"HIERO_PLUGIN_PATH": os.pathsep.join([hiero_path_1, hiero_path_2])}
        with temp_env_var(**hiero_path_env):

            # create launcher
            nuke_launcher = sgtk.platform.create_engine_launcher(
                self.tk,
                sgtk.context.create_empty(self.tk),
                "tk-nuke",
                ["10.0v5"]
            )

            # generate launch env
            launch_info = nuke_launcher.prepare_launch("/path/to/nuke", ["--studio"], None)

            # ensure that the nuke studio path was preserved and placed first in the path
            self.assertEqual(
                launch_info.environment["HIERO_PLUGIN_PATH"],
                os.pathsep.join([hiero_path_1, hiero_path_2, plugin_path])
            )


        # now test without stuff in the heiro path

        # generate launch env
        launch_info = nuke_launcher.prepare_launch("/path/to/nuke", ["--studio"], None)

        # ensure that the nuke studio path was preserved and placed first in the path
        self.assertEqual(
            launch_info.environment["HIERO_PLUGIN_PATH"],
            plugin_path
        )