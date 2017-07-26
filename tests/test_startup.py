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

from tank_test.tank_test_base import TankTestBase
from tank_test.tank_test_base import setUpModule # noqa

import sgtk

import mock
import contextlib


repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
print "tk-nuke repository root found at %s." % repo_root


class TestStartup(TankTestBase):
    """
    Tests the startup logic for Nuke.
    """

    # Mocked folder hierarchy for OSX
    _mac_mock_hierarchy = {
        "Applications": {
            "Nuke10.0v5": [
                "Hiero10.0v5.app",
                "HieroPlayer10.0v5.app",
                "Nuke10.0v5 Non-commercial.app",
                "Nuke10.0v5.app",
                "NukeAssist10.0v5.app",
                "NukeStudio10.0v5 Non-commercial.app",
                "NukeStudio10.0v5.app",
                "NukeX10.0v5 Non-commercial.app",
                "NukeX10.0v5.app"
            ],
            "Nuke9.0v8": [
                "Hiero9.0v8.app",
                "HieroPlayer9.0v8.app",
                "Nuke9.0v8 Non-commercial.app",
                "Nuke9.0v8.app",
                "NukeAssist9.0v8.app",
                "NukeStudio9.0v8 Non-commercial.app",
                "NukeStudio9.0v8.app",
                "NukeX9.0v8 Non-commercial.app",
                "NukeX9.0v8.app"
            ],
            "Nuke8.0v4": [
                "Nuke8.0v4 PLE.app",
                "Nuke8.0v4.app",
                "NukeAssist8.0v4.app",
                "NukeX8.0v4.app"
            ],
            "Nuke7.0v10": [
                "Nuke7.0v10 PLE.app",
                "Nuke7.0v10.app",
                "NukeAssist7.0v10.app",
                "NukeX7.0v10.app"
            ],
            "Nuke7.0v9": [
                "Nuke7.0v9 PLE.app",
                "Nuke7.0v9.app",
                "NukeAssist7.0v9.app",
                "NukeX7.0v9.app"
            ],
            "Nuke6.3v6": [
                "Nuke6.3v6 PLE",
                "Nuke6.3v6.app",
                "NukeAssist6.3v6.app",
                "NukeX6.3v6.app"
            ]
        }
    }

    # Mocked folder hierarchy for Windows.
    _windows_mock_hiearchy = {
        "C:\\": {
            "Program Files": {
                "Nuke10.0v5": ["Nuke10.0.exe"],
                "Nuke9.0v8": ["Nuke9.0.exe"],
                "Nuke8.0v4": ["Nuke8.0.exe"],
                "Nuke7.0v10": ["Nuke7.0.exe"],
                "Nuke6.3v6": ["Nuke6.3.exe"]
            }
        }
    }

    # Mocked folder hierarchy for Linux.
    _linux_mock_hierarchy = {
        "usr": {
            "local": {
                "Nuke10.0v5": ["Nuke10.0"],
                "Nuke9.0v8": ["Nuke9.0"],
                "Nuke8.0v4": ["Nuke8.0"],
                "Nuke7.0v10": ["Nuke7.0"],
                "Nuke6.3v6": ["Nuke6.3"]
            }
        }
    }

    # This will be used to feed our mocked os.listdir so that we can unit tests the launcher
    # even if DCCs are not installed locally.
    _os_neutral_hierarchy = {
        "win32": _windows_mock_hiearchy,
        "linux2": _linux_mock_hierarchy,
        "darwin": _mac_mock_hierarchy
    }

    def setUp(self):
        """
        Prepares the environment for unit tests.
        """
        super(TestStartup, self).setUp()

        # Add an environment variable that will allow the Toolkit environment to pick up the
        # engine's code.
        patch = mock.patch.dict("os.environ", {"TK_NUKE_REPO_ROOT": repo_root})
        self.addCleanup(patch.stop)
        patch.start()

        # Setup the fixture. This will take the configuration at fixtures/config inside this
        # repo.
        self.setup_fixtures()

        # Update the mocked hierarchy to contain the user folder on Linux.
        if sys.platform == "linux2":
            full_path = os.path.expanduser("~")
            current_folder = self._linux_mock_hierarchy
            for t in self._recursive_split(full_path):
                current_folder[t] = {}
                current_folder = current_folder[t]
            current_folder.update(self._linux_mock_hierarchy["usr"]["local"])

        # clear any pre existing nuke startup environment variables
        os.environ.pop('NUKE_PATH', None)
        os.environ.pop('HIERO_PLUGIN_PATH', None)

    def _recursive_split(self, path):
        """
        Splits a path into several tokens such as there is no / in the tokens and no empty
        strings.
        """
        if path == "/":
            return []
        elif path.endswith(":\\"):
            return [path]
        else:
            directory, basename = os.path.split(path)
            return self._recursive_split(directory) + [basename]

    def _os_listdir_wrapper(self, directory):
        """
        Mocked implementation of list dir. It fakes a folder hierarchy.
        """
        tokens = self._recursive_split(directory)
        # Start at the root of the mocked file system
        current_depth = self._os_neutral_hierarchy[sys.platform]
        for t in tokens:
            # Unit test should not be asking for folders outside of the DCC hierarchy.
            self.assertIn(t, current_depth)
            # Remember where we are in the current hierarchy.
            current_depth = current_depth[t]

        # We've reached the folder we wanted, build a list.
        # We're using dicts for intemediary folders and lists for leaf folders so iterate
        # on the items to get all the names.
        return list(iter(current_depth))

    def test_nuke10(self):
        """
        Ensures we are returning the right variants for Nuke 10.
        """
        self._test_nuke(
            [
                "Nuke 10.0v5", "NukeX 10.0v5", "NukeStudio 10.0v5", "NukeAssist 10.0v5"
            ],
            "10.0v5"
        )

    def test_nuke9(self):
        """
        Ensures we are returning the right variants for Nuke 9.
        """
        self._test_nuke(
            [
                "Nuke 9.0v8", "NukeX 9.0v8", "NukeStudio 9.0v8", "NukeAssist 9.0v8"
            ],
            "9.0v8"
        )

    def test_nuke8(self):
        """
        Ensures we are returning the right variants for Nuke 8.
        """
        self._test_nuke(
            [
                "Nuke 8.0v4", "NukeX 8.0v4", "NukeAssist 8.0v4"
            ],
            "8.0v4"
        )

    def test_nuke7(self):
        """
        Ensures we are returning the right variants for Nuke 7.
        """
        self._test_nuke(
            [
                "Nuke 7.0v10", "NukeX 7.0v10", "NukeAssist 7.0v10"
            ],
            "7.0v10"
        )

    def test_nuke7_9(self):
        """
        Ensures we are returning the right variants for Nuke 7.
        """
        self._test_nuke(
            [],
            "7.0v9"
        )

    def test_nuke6(self):
        """
        Ensures that Nuke 6 or lower are not returned as they are not supported.
        """
        self._test_nuke([], "6.3v6")

    @contextlib.contextmanager
    def _mock_folder_listing(self):
        """
        Mocks folder listing so that the startup code can be unit tested even on machines that
        don't have Nuke installed.
        """
        # When this environment variable is set, do not mock folders and rely on the real
        # filesystem data. This is useful when adding support for a new version of Nuke.
        if "TK_NO_FOLDER_MOCKING" not in os.environ:
            with mock.patch("os.listdir", wraps=self._os_listdir_wrapper):
                yield
        else:
            yield

    def _get_plugin_environment(self, dcc_path, ):
        """
        Returns the expected environment variables dictionary for a plugin.
        """
        expected = {
            "SHOTGUN_ENGINE": "tk-nuke",
            "SHOTGUN_PIPELINE_CONFIGURATION_ID": str(self.sg_pc_entity["id"]),
            "SHOTGUN_SITE": sgtk.util.shotgun.get_associated_sg_base_url(),
            dcc_path: os.path.join(repo_root, "plugins", "basic"),
        }
        return expected

    def _get_classic_environment(self, dcc_path):
        """
        Returns the expected environment variables dictionary for a Toolkit classic launch.
        """
        expected = {
            "TANK_CONTEXT": sgtk.context.create_empty(self.tk).serialize(),
            "TANK_ENGINE": "tk-nuke-classic",
            dcc_path: os.path.join(repo_root, "classic_startup"),
        }
        return expected

    def _get_hiero_environment(self, is_classic=True):
        """
        Returns the expected environment variables dictionary for Hiero or Nuke Studio
        """
        if is_classic:
            env = self._get_classic_environment("HIERO_PLUGIN_PATH")
        else:
            env = self._get_plugin_environment("HIERO_PLUGIN_PATH")
        return env

    def _get_nuke_environment(self, is_classic=True):
        """
        Returns the expected environment variables dictionary for Nuke
        """
        if is_classic:
            env = self._get_classic_environment("NUKE_PATH")
        else:
            env = self._get_plugin_environment("NUKE_PATH")
        return env

    def _get_engine_configurations(self):
        """
        Returns the different engine instance name and whether they are using Toolkit Classic or not
        from the fixture.
        """
        return [("tk-nuke", False), ("tk-nuke-classic", True)]

    def test_nuke_studio(self):
        """
        Ensures Nuke Studio LaunchInformation is correct.
        """
        for engine_instance, is_classic in self._get_engine_configurations():
            self._test_launch_information(
                engine_instance, "NukeStudio.app", "", None,
                self._get_hiero_environment(is_classic=is_classic)
            )

            self._test_launch_information(
                engine_instance, "Nuke.exe", "--studio", None,
                self._get_hiero_environment(is_classic=is_classic)
            )

    def test_nuke(self):
        """
        Ensures Nuke LaunchInformation is correct.
        """
        for engine_instance, is_classic in self._get_engine_configurations():

            self._test_launch_information(
                engine_instance, "Nuke.app", "", "/file/to/open",
                self._get_nuke_environment(is_classic=is_classic)
            )

            self._test_launch_information(
                engine_instance, "Nuke.exe", "", "/file/to/open",
                self._get_nuke_environment(is_classic=is_classic)
            )

    def test_nukex(self):
        """
        Ensures NukeX LaunchInformation is correct.
        """
        for engine_instance, is_classic in self._get_engine_configurations():

            self._test_launch_information(
                engine_instance, "NukeX.app", "", "/file/to/open",
                self._get_nuke_environment(is_classic=is_classic)
            )

            self._test_launch_information(
                engine_instance, "Nuke.exe", "--nukex", "/file/to/open",
                self._get_nuke_environment(is_classic=is_classic)
            )

    def test_nukeassist(self):
        """
        Ensures Nuke Assist LaunchInformation is correct.
        """
        for engine_instance, is_classic in self._get_engine_configurations():

            self._test_launch_information(
                engine_instance, "NukeAssist.app", "", "/file/to/open",
                self._get_nuke_environment(is_classic=is_classic)
            )

            self._test_launch_information(
                engine_instance, "Nuke.exe", "--nukeassist", "/file/to/open",
                self._get_nuke_environment(is_classic=is_classic)
            )

    def test_hiero(self):
        """
        Ensures Hiero LaunchInformation is correct.
        """
        self._test_launch_information(
            "tk-nuke-classic", "Hiero.app", "", None,
            self._get_hiero_environment(is_classic=True)
        )

        self._test_launch_information(
            "tk-nuke-classic", "Nuke.exe", "--hiero", None,
            self._get_hiero_environment(is_classic=True)
        )

    def _test_launch_information(self, engine_name, dcc_path, args, file_to_open, expected_env):
        """
        Validates that a given DCC has the right LaunchInformation.

        :param str engine_name: Name of the engine instance name to create a launcher for.
        :param str dcc_path: Path to the DCC. Doesn't have to be a real one.
        :param str file_to_open: Path to a file to open.
        :param str expected_env: Expected environment variables.
        """
        nuke_launcher = sgtk.platform.create_engine_launcher(
            self.tk, sgtk.context.create_empty(self.tk), engine_name, ["10.0v5"]
        )

        launch_info = nuke_launcher.prepare_launch(dcc_path, args, file_to_open)

        self.assertEqual(
            # Maybe there's no args, in which case we need to strip.
            # Also, maybe there's no file to open, so substitute for an empty string.
            ("%s %s" % (file_to_open or "", args)).strip(),
            launch_info.args
        )

        # Ensure the environment variables from the LaunchInfo are the same as the expected ones.
        self.assertListEqual(sorted(expected_env.keys()), sorted(launch_info.environment.keys()))

        # Ensure each environment variable's value is the same as they expected ones.
        for key, value in expected_env.iteritems():
            self.assertIn(key, launch_info.environment)
            self.assertEqual(launch_info.environment[key], value)

    def _test_nuke(self, expected_variations, expected_version):
        """
        Ensures the right number of variations is returned, with the right names and the right icons.

        On Windows, it ensures that the right arguments are also specified.
        """
        self._nuke_launcher = sgtk.platform.create_engine_launcher(
            self.tk, sgtk.context.create_empty(self.tk), "tk-nuke", [expected_version]
        )

        # On linux, we are expecting twice as many hits since Nuke can be installed by default
        # at two different location, so expect twice as many results.
        platform_multiplier = 2 if sys.platform == "linux2" else 1

        with self._mock_folder_listing():
            # Ensure we are getting back the right variations.
            software_versions = self._nuke_launcher.scan_software()

        expected_variations = set(expected_variations)
        found_variations = set(x.display_name for x in software_versions)
        self.assertSetEqual(found_variations, expected_variations)
        # It is possible that due to a bug, the sets are the same, but the number of elements are not, so make sure
        # we built the set with the right number of arguments in the first place.
        self.assertEqual(len(software_versions), len(expected_variations) * platform_multiplier)

        # Ensure the icon is correct.
        for version in software_versions:
            self.assertEqual(os.path.exists(version.icon), True)
            file_name = os.path.basename(version.icon)
            if "studio" in version.display_name.lower():
                self.assertEqual(file_name, "icon_nukestudio_256.png")
            elif "hiero" in version.display_name.lower():
                self.assertEqual(file_name, "icon_hiero_256.png")
            elif "nukex" in version.display_name.lower():
                self.assertEqual(file_name, "icon_x_256.png")
            else:
                self.assertEqual(file_name, "icon_256.png")

        if sys.platform != "darwin":
            # Ensures that not only the expect arguments are present, but that there are no more of them.
            for version in software_versions:
                expected_arguments = []
                for token in ["studio", "nukeassist", "nukex", "hiero"]:
                    if token in version.display_name.lower():
                        expected_arguments.append("--%s" % token)

                # And that they are the same.
                self.assertSetEqual(set(expected_arguments), set(version.args))
                # Ensure there are as many tokens.
                self.assertEqual(len(expected_arguments), len(version.args))
