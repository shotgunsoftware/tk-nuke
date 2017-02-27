# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import glob
import os
import re
import sys

from sgtk.platform import SoftwareLauncher, SoftwareVersion, LaunchInformation


class NukeLauncher(SoftwareLauncher):
    """
    Handles launching Nuke executables. Automatically starts up a tk-nuke
    engine with the current context in the new session of Nuke.
    """

    # Glob strings to insert into the executable template paths when globbing
    # for executables and bundles on disk. Globbing is admittedly limited in
    # terms of specific match strings, but if we need to introduce more precise
    # match strings later, we can do it in one place rather than each of the
    # template paths defined below.
    COMPONENT_GLOB_LOOKUP = {
        "version": "*",
        "variant": "*",
        "suffix": "*",
        "same_version": "*",
        "major_minor_version": "*"
    }

    # Named regex strings to insert into the executable template paths when
    # matching against supplied versions and variants. Similar to the glob
    # strings, these allow us to alter the regex matching for any of the
    # variable components of the path in one place
    COMPONENT_REGEX_LOOKUP = {
        "version": "(?P<version>[\d.v]+)",
        "variant": "(?P<variant>[\w\s]+)",
        "suffix": "(?P<suffix> Non-commercial){0,1}",
        "same_version": "(?P=version)",
        "major_minor_version": "(?P<major_minor_version>[\d.]+)"
    }

    # This dictionary defines a list of executable template strings for each
    # of the supported operating systems. The templates can are used for both
    # globbing and regex matches by replacing the named format placeholders
    # with an appropriate glob or regex string. As Side FX adds modifies the
    # install path on a given OS for a new release, a new template will need
    # to be added here.
    EXECUTABLE_MATCH_TEMPLATES = {
        "darwin": [
            # /Applications/Nuke10.0v5/NukeStudio10.0v5.app
            "/Applications/Nuke{version}/{variant}{same_version}{suffix}.app",
        ],
        "win32": [
            # C:\Program Files\Nuke10.0v5\Nuke10.0.exe
            "C:\\Program Files\\Nuke{version}\\Nuke{major_minor_version}.exe",
        ],
        # "linux": [
        #     # example path: /opt/hfs14.0.444/bin/houdinifx
        #     "/opt/hfs{version}/bin/{executable}",
        # ]
    }

    def _get_icon_from_variant(self, variant):
        """
        Returns the icon based on the variant.
        """
        if "studio" in variant.lower():
            return os.path.join(
                self.disk_location,
                "icon_studio_256.png"
            )
        elif "hiero" in variant.lower():
            return os.path.join(
                self.disk_location,
                "icon_hiero_256.png"
            )
        else:
            return os.path.join(
                self.disk_location,
                "icon_256.png"
            )

    def _find_executables(self, match_templates):
        # build up a dictionary where the key is the match template and the
        # value is a list of matching executables. we'll need to keep the
        # association between template and matches for later when we extract
        # the components (version and variation)
        executable_matches = {}
        for match_template in match_templates:

            # build the glob pattern by formatting the template for globbing
            glob_pattern = match_template.format(**self.COMPONENT_GLOB_LOOKUP)
            self.logger.debug(
                "Globbing for executable matching: %s ..." % (glob_pattern,)
            )
            matching_paths = glob.glob(glob_pattern)
            if matching_paths:
                # found matches, remember this association (template: matches)
                executable_matches[match_template] = matching_paths
                self.logger.debug(
                    "Found %s matches: %s" % (
                        len(matching_paths),
                        matching_paths
                    )
                )

        return executable_matches

    def _find_software_variations(self, executable_matches, variations, versions):
        return self._find_software_variations_macOS(executable_matches, variations, versions)

    def _find_software_variations_macOS(self, executable_matches, variations, versions):
        software_versions = []

        # now that we have a list of matching executables on disk and the
        # corresponding template used to find them, we can extract the component
        # pieces to see if they match the supplied version/variant constraints
        for (match_template, executable_paths) in executable_matches.iteritems():

            # construct the regex string to extract the components
            regex_pattern = match_template.format(**self.COMPONENT_REGEX_LOOKUP)

            # TODO: account for \ on windows...

            # accumulate the software version objects to return. this will include
            # include the head/tail anchors in the regex
            regex_pattern = "^%s$" % (regex_pattern,)

            self.logger.debug(
                "Now matching components with regex: %s" % (regex_pattern,)
            )

            # compile the regex
            executable_regex = re.compile(regex_pattern, re.IGNORECASE)

            # iterate over each executable found for the glob pattern and find
            # matched components via the regex
            for executable_path in executable_paths:

                self.logger.debug("Processing path: %s" % (executable_path,))

                match = executable_regex.match(executable_path)

                if not match:
                    self.logger.debug("Path did not match regex.")
                    continue

                # extract the components (default to None if not included)
                executable_version = match.groupdict().get("version")
                executable_variant = match.groupdict().get("variant")
                executable_suffix = match.groupdict().get("suffix")

                # if we're here then we know the version is valid or there is
                # no version filter. we also know that the variant is a match.
                # we can safely create a software version instance to return

                if executable_suffix:
                    display_name = "%s %s%s" % (executable_variant, executable_version, executable_suffix)
                else:
                    display_name = "%s %s" % (executable_variant, executable_version)

                if not self._keep_software(
                    executable_variant, executable_version, variations, versions
                ):
                    continue

                # Either we don't have a version constraint list of this
                # version matches one of the constraints. Add this to the
                # list of SW versions to return.
                software_versions.append(
                    SoftwareVersion(
                        executable_version,
                        display_name,
                        executable_path,
                        self._get_icon_from_variant(executable_variant)
                    )
                )
                self.logger.debug("Filter match: %s" % (display_name,))

        return software_versions

    def scan_software(self, versions=None):
        """
        Performs a scan for software installations.

        :param list versions: List of strings representing versions to search
            for. If set to None, search for all versions.

        :returns: List of :class:`SoftwareVersion` instances
        """

        # TODO: tmp until available via args/settings
        VARIATIONS = ["Nuke", "NukeStudio", "NukeX", "NukeAssist", "Hiero"]

        self.logger.debug("Scanning for Nuke versions...")
        self.logger.debug("Version constraints: %s" % (versions,))
        self.logger.debug("Variation constraints: %s" % (VARIATIONS,))

        if sys.platform not in ["darwin", "win32", "linux"]:
            self.logger.debug("Nuke not supported on this platform.")
            return []

        # all the executable templates for the current OS
        executable_matches = self._find_executables(self.EXECUTABLE_MATCH_TEMPLATES[sys.platform])
        return self._find_software_variations(executable_matches, VARIATIONS, versions)

    def _keep_software(self, variant, version, variations, versions):
        if versions and version not in versions:
            return False

        if variations and variant not in variations:
            return False

        return True

    def prepare_launch(self, exec_path, args, file_to_open=None):
        """
        Prepares the given software for launch

        :param str exec_path: Path to DCC executable to launch

        :param str args: Command line arguments as strings

        :param str file_to_open: (optional) Full path name of a file to open on
            launch

        :returns: :class:`LaunchInformation` instance
        """

        tk_houdini_python_path = os.path.join(
            self.disk_location,
            "python",
        )

        sys.path.insert(0, tk_houdini_python_path)
        from tk_houdini import bootstrap

        # determine all environment variables
        required_env = bootstrap.compute_environment()

        # Add std context and site info to the env
        std_env = self.get_standard_plugin_environment()
        required_env.update(std_env)

        return LaunchInformation(exec_path, args, required_env)
