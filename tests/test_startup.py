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
print "tk-nuke repoistory root found at %s." % repo_root


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
        "C:/": {
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

    def _recursive_split(self, path):
        """
        Splits a path into several tokens such as there is no / in the tokens and no empty
        strings.
        """
        if path == "/":
            return []
        elif path.endswith(":/"):
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
                "Nuke 10.0v5", "NukeX 10.0v5", "NukeStudio 10.0v5", "NukeAssist 10.0v5",
                "Nuke Non-commercial 10.0v5", "NukeX Non-commercial 10.0v5", "NukeStudio Non-commercial 10.0v5"
            ],
            "10.0v5"
        )

    def test_nuke9(self):
        """
        Ensures we are returning the right variants for Nuke 9.
        """
        self._test_nuke(
            [
                "Nuke 9.0v8", "NukeX 9.0v8", "NukeStudio 9.0v8", "NukeAssist 9.0v8",
                "Nuke Non-commercial 9.0v8", "NukeX Non-commercial 9.0v8", "NukeStudio Non-commercial 9.0v8"
            ],
            "9.0v8"
        )

    def test_nuke8(self):
        """
        Ensures we are returning the right variants for Nuke 8.
        """
        self._test_nuke(
            [
                "Nuke 8.0v4", "NukeX 8.0v4", "Nuke PLE 8.0v4", "NukeAssist 8.0v4"
            ],
            "8.0v4"
        )

    def test_nuke7(self):
        """
        Ensures we are returning the right variants for Nuke 7.
        """
        self._test_nuke(
            [
                "Nuke 7.0v10", "NukeX 7.0v10", "Nuke PLE 7.0v10", "NukeAssist 7.0v10"
            ],
            "7.0v10"
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

                if "Non-commercial" in version.display_name:
                    expected_arguments.append("--nc")

                if "PLE" in version.display_name:
                    expected_arguments.append("--ple")

                # And that they are the same.
                self.assertSetEqual(set(expected_arguments), set(version.arguments))
                # Ensure there are as many tokens.
                self.assertEqual(len(expected_arguments), len(version.arguments))
