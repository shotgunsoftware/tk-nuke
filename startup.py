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

def template_to_variation_name(x):
    return x.replace("%s", "").replace("  ", " ").strip()


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
        "version": r"(?P<version>[\d.v]+)",
        "variant": r"(?P<variant>[\w\s]+)",
        "suffix": r"(?P<suffix> Non-commercial| PLE){0,1}",
        "same_version": r"(?P=version)",
        "major_minor_version": r"(?P<major_minor_version>[\d.]+)"
    }

    # Templates for all the display names of the variations supported by Nuke 7 and 8.
    NUKE_7_8_VARIATION_DISPLAY_NAME_TEMPLATES = [
        "Nuke %s",
        "NukeX %s",
        "Nuke %s PLE",
        "NukeAssist %s",
    ]

    # Name of all the variations supported by Nuke 7 and 8.
    NUKE_7_8_VARIATIONS = [
        template_to_variation_name(x) for x in NUKE_7_8_VARIATION_DISPLAY_NAME_TEMPLATES
    ]

    # Templates for all the display names of the variations supported by Nuke 9 and onward.
    NUKE_9_OR_HIGHER_VARIATION_DISPLAY_NAME_TEMPLATES = [
        "Nuke %s",
        "Nuke %s Non-commercial",
        "NukeAssist %s",
        "NukeStudio %s",
        "NukeStudio %s Non-commercial",
        "NukeX %s",
        "NukeX %s Non-commercial",
        "Hiero %s"
    ]

    # Name for all the variations supported by Nuke 9 and onward.
    NUKE_9_OR_HIGHER_VARIATIONS = [
        template_to_variation_name(x) for x in NUKE_9_OR_HIGHER_VARIATION_DISPLAY_NAME_TEMPLATES
    ]

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
            "C:/Program Files/Nuke{version}/Nuke{major_minor_version}.exe",
        ],
        "linux2": [
            # example path: /usr/local/Nuke10.0v5/Nuke10.0
            "/usr/local/Nuke{version}/Nuke{major_minor_version}",
        ]
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
        elif "nukex" in variant.lower():
            return os.path.join(
                self.disk_location,
                "icon_x_256.png"
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
                executable_matches[match_template] = [x.replace("\\", "/") for x in matching_paths]
                self.logger.debug(
                    "Found %s matches: %s" % (
                        len(matching_paths),
                        matching_paths
                    )
                )

        return executable_matches

    def _find_software_variations(self):
        executable_matches = self._find_executables(self.EXECUTABLE_MATCH_TEMPLATES[sys.platform])

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

                for variation in self._extract_variations_from_path(executable_path, match):
                    yield variation

    def _extract_variations_from_path(self, executable_path, match):
        # Extract the variation from the file path, as each variation of the product has an actual
        # executable associated to it.

        executable_version = match.groupdict().get("version")
        if sys.platform == "darwin":
            # extract the components (default to None if not included)
            executable_variant = match.groupdict().get("variant")
            # If there is no suffix (Non-commercial, we'll simply use an empty string).
            executable_suffix = match.groupdict().get("suffix") or ""

            # if we're here then we know the version is valid or there is
            # no version filter. we also know that the variant is a match.
            # we can safely create a software version instance to return
            display_name = "%s %s%s" % (executable_variant, executable_version, executable_suffix)

            # Either we don't have a version constraint list of this
            # version matches one of the constraints. Add this to the
            # list of SW versions to return.
            yield SoftwareVersion(
                executable_version,
                executable_variant,
                display_name,
                executable_path,
                self._get_icon_from_variant(executable_variant)
            )
        else:
            for variation_template in self._get_variation_templates_from_version(executable_version):

                # Figure out the arguments required for each variation.
                arguments = []
                if "Studio" in variation_template:
                    arguments.append("--studio")
                elif "Assist" in variation_template:
                    arguments.append("--nukeassit")
                elif "NukeX" in variation_template:
                    arguments.append("--nukex")
                elif "Hiero" in variation_template:
                    arguments.append("--hiero")
                elif "PLE" in variation_template:
                    arguments.append("--ple")

                # If this is a non-commercial build, we need to add the special argument.
                if "Non-commercial" in variation_template:
                    arguments.append("--nc")

                yield SoftwareVersion(
                    executable_version,
                    template_to_variation_name(variation_template),
                    variation_template % (executable_version,),
                    executable_path,
                    self._get_icon_from_variant(variation_template)
                )

    def _get_variation_templates_from_version(self, version):
        # As of Nuke 6, Nuke versions formatting is <Major>.<Minor>v<patch>.
        # This will grab the major version.
        if version.split(".", 1)[0] in ["7", "8"]:
            return self.NUKE_7_8_VARIATION_DISPLAY_NAME_TEMPLATES
        else:
            return self.NUKE_9_OR_HIGHER_VARIATION_DISPLAY_NAME_TEMPLATES

    def _get_variations_from_version(self, version):
        # As of Nuke 6, Nuke versions formatting is <Major>.<Minor>v<patch>.
        # This will grab the major version.
        if version.split(".", 1)[0] in ["7", "8"]:
            return self.NUKE_7_8_VARIATIONS
        else:
            return self.NUKE_9_OR_HIGHER_VARIATIONS

    def scan_software(self):
        """
        Performs a scan for software installations.

        :param list versions: List of strings representing versions to search
            for. If set to None, search for all versions.

        :returns: List of :class:`SoftwareVersion` instances
        """
        self.logger.debug("Scanning for Nuke versions...")

        if sys.platform not in ["darwin", "win32", "linux2"]:
            self.logger.debug("Nuke not supported on platform %s.", sys.platform)
            return []

        software_versions = []
        for software_version in self._find_software_variations():
            if self.is_version_supported(software_version):
                self.logger.debug("Accepting %s", software_version)
                software_versions.append(software_version)

        return software_versions

    def is_version_supported(self, version):
        return (
            # Make sure this is a product the software entity requested
            super(NukeLauncher, self).is_version_supported(version) and
            # And this is a product that Toolkit support. For example, HieroPlayer is not
            # supported.
            version.product in self._get_variations_from_version(version.version)
        )

    @property
    def minimum_supported_version(self):
        return "7.0v0"

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
